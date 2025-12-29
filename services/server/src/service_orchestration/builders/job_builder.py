"""
Job Builder for Service Orchestrator.
Handles config merging and SLURM payload generation from Recipe objects.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any

from service_orchestration.recipe_builders import BuilderRegistry, ScriptPaths
from service_orchestration.recipes import Recipe, InferenceRecipe

logger = logging.getLogger(__name__)


class JobBuilder:
    """Builds SLURM job payloads and scripts from Recipe objects."""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.recipes_dir = self.base_path / "src" / "recipes"
        self.logs_dir = self.base_path / "logs"
        self.env_module = os.getenv("MELUXINA_ENV_MODULE", "env/release/2023.1")
        self.apptainer_module = os.getenv("APPTAINER_MODULE", "Apptainer/1.2.4-GCCcore-12.3.0")

    def build_job(self, recipe: Recipe, config: Dict[str, Any], account: str) -> Dict[str, Any]:
        """Build SLURM job payload and script from a Recipe object.
        
        Args:
            recipe: Validated Recipe object
            config: User-provided configuration overrides
            account: SLURM account to use
            
        Returns:
            Dict with 'script' (bash script) and 'job' (SLURM job description)
        """
        # Merge config into recipe
        merged_recipe = recipe.merge_config(config)
        resources = merged_recipe.resources
        
        # Inject HF_TOKEN from server environment if present
        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
        if hf_token:
            merged_recipe.environment["HF_TOKEN"] = hf_token
            # Also set legacy var for compatibility
            merged_recipe.environment["HUGGINGFACEHUB_API_TOKEN"] = hf_token
        
        # Calculate tasks/gpus for replica groups
        if isinstance(merged_recipe, InferenceRecipe) and merged_recipe.is_replica_group:
            ntasks = merged_recipe.replicas_per_node
            gpus_per_task = merged_recipe.gpu_per_replica
        else:
            ntasks = 1
            gpus_per_task = resources.gpu if resources.gpu else 0
            
        # Generate script
        script = self._create_script(merged_recipe, config)
        
        # Build environment as object/dict (required by Slurm REST API v0.0.40)
        env_dict = {
            "PATH": "/bin:/usr/bin:/usr/local/bin",
            "USER": os.getenv('USER', 'unknown'),
            "BASH_ENV": "/etc/profile"
        }
        env_dict.update(merged_recipe.environment)
        
        # Build job description for Slurm REST API v0.0.40
        job_name = merged_recipe.name
        job_desc = {
            "account": account,
            "qos": "short",
            "time_limit": {
                "number": resources.time_limit,
                "set": True
            },
            "current_working_directory": str(self.logs_dir),
            "environment": env_dict,
            "standard_output": f"{self.logs_dir}/{job_name}_%j.out",
            "standard_error": f"{self.logs_dir}/{job_name}_%j.err"
        }
        
        # Add resource specifications
        job_desc["partition"] = "gpu" if resources.gpu else "cpu"
        job_desc["name"] = job_name
        
        # Add node allocation
        job_desc["nodes"] = str(resources.nodes)
        
        # Add task allocation (for multi-replica jobs)
        if ntasks > 1:
            job_desc["tasks"] = ntasks
            job_desc["tasks_per_node"] = ntasks
        
        # Add GPU allocation if requested
        if resources.gpu and resources.gpu > 0:
            if gpus_per_task > 0:
                job_desc["gres"] = f"gpu:{gpus_per_task}"
            else:
                job_desc["gres"] = f"gpu:{resources.gpu}"
        
        logger.info(
            f"Building job with nodes={resources.nodes}, "
            f"GPU config: gpu_count={resources.gpu}, gpus_per_task={gpus_per_task}, "
            f"ntasks={ntasks}, gres={job_desc.get('gres')}"
        )
        
        return {
            "script": script,
            "job": job_desc
        }

    def _create_script(self, recipe: Recipe, config: Dict[str, Any]) -> str:
        """Create the SLURM job script from a Recipe object.
        
        Args:
            recipe: Merged Recipe object with all configuration applied
            config: Original user config (for recipe builder compatibility)
            
        Returns:
            Complete bash script as string
        """
        # Get container paths from recipe
        container_paths = recipe.get_container_paths(str(self.recipes_dir))
        
        paths = ScriptPaths(
            def_path=container_paths["def_path"],
            sif_path=container_paths["sif_path"],
            log_dir=str(self.logs_dir),
            remote_base_path=str(self.base_path)
        )
        
        # Get the appropriate builder
        category = recipe.category.value
        try:
            builder = BuilderRegistry.create_builder(
                category, 
                recipe_name=recipe.name,
                remote_base_path=str(self.base_path)
            )
        except ValueError:
            builder = BuilderRegistry.create_builder('inference', remote_base_path=str(self.base_path))
            
        # Build sections
        env_section = builder.build_environment_section(recipe.environment)
        build_block = builder.build_container_build_block(paths)
        
        # Build merged config for replica group - user config overrides
        merged_config = {}
        if isinstance(recipe, InferenceRecipe):
            merged_config['gpu_per_replica'] = recipe.gpu_per_replica
            merged_config['base_port'] = recipe.base_port
            if recipe.nproc_per_node:
                merged_config['nproc_per_node'] = recipe.nproc_per_node
            if recipe.master_port:
                merged_config['master_port'] = recipe.master_port
        merged_config.update(config or {})
        
        # Pass Recipe and RecipeResources objects directly to builders
        if recipe.is_replica_group and builder.supports_distributed():
            run_block = builder.build_replica_group_run_block(paths, recipe.resources, recipe, merged_config)
        else:
            run_block = builder.build_run_block(paths, recipe.resources, recipe)
            
        return f"""#!/bin/bash -l

    module load {self.env_module}
    module load {self.apptainer_module}

{env_section}

mkdir -p {self.logs_dir}

{build_block}

{run_block}

exit $container_exit_code
"""

