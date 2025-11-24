"""
Job Builder for Service Orchestrator.
Handles recipe loading, config merging, and SLURM payload generation.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, List
from service_orchestration.recipe_builders import BuilderRegistry, ScriptPaths

logger = logging.getLogger(__name__)

def parse_time_limit(time_str):
    """Parse time limit string to minutes."""
    if not time_str:
        return 60
    if isinstance(time_str, int):
        return time_str
    # Simple parser, can be expanded
    try:
        if ':' in time_str:
            parts = time_str.split(':')
            if len(parts) == 3: # HH:MM:SS
                return int(parts[0])*60 + int(parts[1])
            elif len(parts) == 2: # MM:SS
                return int(parts[0])
        return int(time_str)
    except:
        return 60

class JobBuilder:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.recipes_dir = self.base_path / "src" / "recipes"
        self.logs_dir = self.base_path / "logs"
        
    def _find_recipe(self, recipe_name: str) -> Path:
        """Find recipe file by name."""
        if "/" in recipe_name:
            category, name = recipe_name.split("/", 1)
            recipe_path = self.recipes_dir / category / f"{name}.yaml"
        else:
            # Search all categories
            for yaml_file in self.recipes_dir.rglob(f"{recipe_name}.yaml"):
                return yaml_file
            recipe_path = None
        
        if not recipe_path or not recipe_path.exists():
            raise FileNotFoundError(f"Recipe '{recipe_name}' not found in {self.recipes_dir}")
        return recipe_path

    def build_job(self, recipe_name: str, config: Dict[str, Any], account: str) -> Dict[str, Any]:
        """Build SLURM job payload and script."""
        # Load recipe
        recipe_path = self._find_recipe(recipe_name)
        with open(recipe_path, 'r') as f:
            recipe = yaml.safe_load(f)
            
        # Merge resources
        resources = recipe.get("resources", {}).copy()
        if "resources" in config:
            resources.update(config["resources"])
        for key in ['nodes', 'cpu', 'memory', 'gpu', 'time_limit']:
            if key in config:
                resources[key] = config[key]
                
        # Merge environment
        merged_env = recipe.get("environment", {}).copy()
        if "environment" in config:
            merged_env.update(config["environment"])
        if "replica_port" in config:
            merged_env["VLLM_PORT"] = str(config["replica_port"])
            
        # Calculate tasks/gpus
        gpu_per_replica = recipe.get("gpu_per_replica")
        total_gpus = resources.get("gpu")
        
        if gpu_per_replica and total_gpus:
            replicas_per_node = int(total_gpus) // int(gpu_per_replica)
            ntasks = replicas_per_node
            gpus_per_task = int(gpu_per_replica)
        else:
            ntasks = 1
            gpus_per_task = int(total_gpus) if total_gpus else 0
            
        # Generate script
        script = self._create_script(recipe, recipe_path, merged_env, resources, config)
        
        # Build job description
        time_limit = parse_time_limit(resources.get("time_limit"))
        
        # Build environment as object/dict (required by Slurm REST API v0.0.40)
        env_dict = {
            "PATH": "/bin:/usr/bin:/usr/local/bin",
            "USER": os.getenv('USER', 'unknown'),
            "BASH_ENV": "/etc/profile"
        }
        env_dict.update(merged_env)
        
        # Build job description for Slurm REST API v0.0.40
        # Start with absolute minimum, then add fields carefully
        job_name = recipe.get('name', recipe_name)
        job_desc = {
            "account": account,  # Use the account parameter passed in
            "qos": "short",
            "time_limit": {
                "number": int(time_limit),
                "set": True
            },
            "current_working_directory": str(self.logs_dir),
            "environment": env_dict,
            "standard_output": f"{self.logs_dir}/{job_name}_%j.out",
            "standard_error": f"{self.logs_dir}/{job_name}_%j.err"
        }
        
        # Add resource specifications
        job_desc["partition"] = "gpu" if resources.get("gpu") else "cpu"
        job_desc["name"] = job_name
        
        # Add GPU allocation if requested
        gpu_count = resources.get("gpu")
        if gpu_count and str(gpu_count) != "0":
            # GRES format for GPU allocation
            if gpus_per_task > 0:
                job_desc["gres"] = f"gpu:{gpus_per_task}"
            else:
                job_desc["gres"] = f"gpu:{gpu_count}"
        
        logger.info(f"Building job with GPU config: gpu_count={gpu_count}, gpus_per_task={gpus_per_task}, gres={job_desc.get('gres')}")
        
        return {
            "script": script,
            "job": job_desc
        }

    def _create_script(self, recipe, recipe_path, env, resources, config):
        category = recipe_path.parent.name
        recipe_name = recipe.get('name', '')
        
        # Paths
        container_def = recipe.get("container_def", f"{recipe_name}.def")
        image_name = recipe.get("image", f"{recipe_name}.sif")
        
        # Use absolute paths based on base_path
        def_path = str(self.recipes_dir / category / container_def)
        sif_path = str(self.recipes_dir / category / image_name)
        
        paths = ScriptPaths(
            def_path=def_path,
            sif_path=sif_path,
            log_dir=str(self.logs_dir),
            remote_base_path=str(self.base_path)
        )
        
        # Builder
        try:
            builder = BuilderRegistry.create_builder(
                category, 
                recipe_name=recipe_name,
                remote_base_path=str(self.base_path)
            )
        except ValueError:
            builder = BuilderRegistry.create_builder('inference', remote_base_path=str(self.base_path))
            
        # Build sections
        env_section = builder.build_environment_section(env)
        build_block = builder.build_container_build_block(paths)
        
        merged_config = {}
        for key in ['gpu_per_replica', 'base_port', 'nproc_per_node', 'master_port', 
                    'model', 'max_model_len', 'gpu_memory_utilization']:
            if key in recipe:
                merged_config[key] = recipe[key]
        merged_config.update(config or {})
        
        if merged_config and builder.supports_distributed():
            run_block = builder.build_replica_group_run_block(paths, resources, recipe, merged_config)
        else:
            run_block = builder.build_run_block(paths, resources, recipe)
            
        return f"""#!/bin/bash -l

module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0

{env_section}

mkdir -p {self.logs_dir}

{build_block}

{run_block}

exit $container_exit_code
"""
