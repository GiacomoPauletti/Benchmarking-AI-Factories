"""
SLURM job submission and management logic.
Translates recipes into SLURM scripts and runs with Apptainer via SLURM REST API.
"""

import yaml
import requests
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, List
from utils import parse_time_limit
from datetime import datetime


class SlurmDeployer:
    """Handles SLURM job submission and management for Apptainer workloads via REST API."""
    
    def __init__(self, account: str = "p200981"):
        self.logger = logging.getLogger(__name__)
        self.account = account
        self.username = os.getenv('USER', 'unknown')
        self.token = os.getenv('SLURM_JWT')
        if not self.token:
            raise RuntimeError("SLURM_JWT environment variable not set")
        
        env_base_path = os.getenv('SERVER_BASE_PATH')
        self.base_path = Path(env_base_path)
        print(f"Using SERVER_BASE_PATH from environment: {self.base_path}")
        self.logger.debug(f"Using SERVER_BASE_PATH from environment: {self.base_path}")

        
        self.base_url = "http://slurmrestd.meluxina.lxp.lu:6820/slurm/v0.0.40"
        self.headers = {
            'X-SLURM-USER-NAME': self.username,
            'X-SLURM-USER-TOKEN': self.token,
            'Content-Type': 'application/json'
        }
    
    def submit_job(self, recipe_name: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Submit a job to SLURM cluster using recipe configuration."""
        # Load recipe
        recipe_path = self._find_recipe(recipe_name)
        with open(recipe_path, 'r') as f:
            recipe = yaml.safe_load(f)
        
        # Generate and submit job
        job_payload = self._create_job_payload(recipe, config or {}, recipe_name, recipe_path)
        
        # Debug: print the payload
        print("Submitting job payload:")
        print(json.dumps(job_payload, indent=2))
        
        response = requests.post(
            f"{self.base_url}/job/submit", 
            headers=self.headers, 
            json=job_payload
        )
        
        # Debug: print the response for troubleshooting
        print(f"SLURM API Response Status: {response.status_code}")
        print(f"SLURM API Response Body: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        if result.get('errors'):
            raise RuntimeError(f"SLURM API errors: {result['errors']}")
        
        # Return job information directly from SLURM response
        job_id = result.get('job_id', 0)
        
        # Validate that we got a valid job ID
        if job_id == 0:
            raise RuntimeError(f"SLURM job submission failed: received job_id=0. Response: {result}")
        
        return {
            "id": str(job_id),  # Use SLURM job ID directly as service ID
            "name": f"{recipe['name']}-{job_id}",
            "recipe_name": recipe_name,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "nodes": config.get("nodes", 1),
            "config": config or {}
        }
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running SLURM job by job ID."""
        try:
            response = requests.delete(
                f"{self.base_url}/job/{job_id}", 
                headers=self.headers
            )
            response.raise_for_status()
            return True
        except:
            return False
    
    def get_job_status(self, job_id: str) -> str:
        """Get the status of a SLURM job by job ID."""
        try:
            response = requests.get(
                f"{self.base_url}/job/{job_id}", 
                headers=self.headers,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                jobs = result.get('jobs', [])
                if jobs:
                    job = jobs[0]
                    job_state = job.get('job_state', '')
                    
                    # Handle case where job_state might be a list or other type
                    if isinstance(job_state, list):
                        status = job_state[0].lower() if job_state else 'unknown'
                    elif isinstance(job_state, str):
                        status = job_state.lower()
                    else:
                        status = str(job_state).lower()
                    
                    status_map = {
                        'pending': 'pending',
                        'running': 'running',
                        'completed': 'completed',
                        'failed': 'failed',
                        'cancelled': 'cancelled'
                    }
                    return status_map.get(status, 'unknown')
            
            # If job not found in REST API, it likely completed
            return "completed"
            
        except Exception as e:
            raise RuntimeError(f"Failed to get job status from SLURM API: {str(e)}")
    
    def list_jobs(self, user_filter: str = None) -> list:
        """List all jobs from SLURM cluster, optionally filtered by user."""
        try:
            # Use the /jobs endpoint to get all jobs
            params = {}
            if user_filter:
                # Note: The official API may not support user filtering directly
                # but we can filter the results after getting them
                pass
            
            response = requests.get(
                f"{self.base_url}/jobs", 
                headers=self.headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            result = response.json()
            jobs = result.get('jobs', [])
            
            # Filter to current user's jobs and convert to our format
            user_jobs = []
            for job in jobs:
                # Only include jobs belonging to the current user
                job_user = job.get('user_name', '')
                if not user_filter or job_user == self.username:
                    
                    job_state = job.get('job_state', ['unknown'])
                    if isinstance(job_state, list):
                        status = job_state[0].lower() if job_state else 'unknown'
                    else:
                        status = str(job_state).lower()
                    
                    status_map = {
                        'pending': 'pending', 
                        'running': 'running',
                        'completed': 'completed',
                        'failed': 'failed',
                        'cancelled': 'cancelled'
                    }
                    
                    user_jobs.append({
                        "id": str(job.get('job_id', 0)),  # Use SLURM job ID directly as service ID
                        "name": job.get('name', 'unnamed'),
                        "status": status_map.get(status, 'unknown'),
                        "account": job.get('account', ''),
                        "partition": job.get('partition', ''),
                        "nodes": job.get('node_count', {}).get('number', 0) if isinstance(job.get('node_count'), dict) else job.get('node_count', 0),
                        "user": job_user,
                        "recipe_name": "unknown",  # SLURM doesn't store this, could be extracted from job name
                        "config": {},  # SLURM doesn't store this
                        "created_at": "unknown"  # Could be extracted from submit_time if available
                    })
            
            return user_jobs
            
        except Exception as e:
            raise RuntimeError(f"Failed to list jobs from SLURM API: {str(e)}")
    
    def get_job_logs(self, job_id: str) -> str:
        """Get logs from SLURM job."""
        try:
            log_dir = self.base_path / "logs"
            
            if not log_dir.exists():
                return f"Log directory {log_dir} not found"

            # Get job details to find the job name
            job_details = self.get_job_details(job_id)
            job_name = job_details.get('name', 'unknown') if job_details else 'unknown'
            
            # Look for SLURM stdout and stderr files
            stdout_file = log_dir / f"{job_name}_{job_id}.out"
            stderr_file = log_dir / f"{job_name}_{job_id}.err"
            
            logs = []
            
            # Read stdout
            if stdout_file.exists():
                try:
                    content = stdout_file.read_text()
                    logs.append(f"=== SLURM STDOUT ({stdout_file.name}) ===\n{content}")
                except Exception as e:
                    logs.append(f"=== SLURM STDOUT ===\nError reading {stdout_file.name}: {e}")
            else:
                logs.append(f"=== SLURM STDOUT ===\nFile not found: {stdout_file.name}")
            
            # Read stderr
            if stderr_file.exists():
                try:
                    content = stderr_file.read_text()
                    logs.append(f"=== SLURM STDERR ({stderr_file.name}) ===\n{content}")
                except Exception as e:
                    logs.append(f"=== SLURM STDERR ===\nError reading {stderr_file.name}: {e}")
            else:
                logs.append(f"=== SLURM STDERR ===\nFile not found: {stderr_file.name}")
            
            return "\n\n".join(logs)
            
        except Exception as e:
            return f"Error retrieving logs for job {job_id}: {str(e)}"

    
    def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """Get detailed information about a SLURM job including allocated nodes."""
        try:
            response = requests.get(
                f"{self.base_url}/job/{job_id}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                # DEBUG: emit raw job JSON for troubleshooting allocated node fields
                try:
                    import logging
                    logging.getLogger(__name__).debug("SLURM raw job response for %s: %s", job_id, json.dumps(result))
                except Exception:
                    pass
                jobs = result.get('jobs', [])
                if jobs:
                    job = jobs[0]
                    # Extract node information. Different Slurm deployments expose
                    # allocated node names in different fields. Prefer the top-level
                    # 'nodes' field (string), then job_resources.nodes, then the
                    # job_resources.allocated_nodes list (which contains dicts with
                    # a 'nodename' key). As a last resort use 'allocating_node'.
                    allocated_nodes: List[str] = []

                    # Candidate string fields that may contain compact node lists
                    node_str = job.get('nodes') or job.get('node_list')
                    if not node_str:
                        jr = job.get('job_resources', {}) if isinstance(job.get('job_resources', {}), dict) else job.get('job_resources')
                        if isinstance(jr, dict):
                            node_str = jr.get('nodes') or jr.get('node_list')

                    if node_str:
                        # Parse compact string formats like 'mel2141' or 'mel[2001-2003]'
                        try:
                            allocated_nodes = self._parse_node_list(str(node_str))
                        except Exception:
                            allocated_nodes = [str(node_str)]
                    else:
                        # Try allocated_nodes structure under job_resources
                        jr = job.get('job_resources', {}) or {}
                        alloc_list = jr.get('allocated_nodes') or jr.get('allocated_hosts')
                        if isinstance(alloc_list, list) and alloc_list:
                            for item in alloc_list:
                                if isinstance(item, dict):
                                    # Common key is 'nodename' in this cluster
                                    nodename = item.get('nodename') or item.get('nodename')
                                    if nodename:
                                        allocated_nodes.append(str(nodename))
                                elif isinstance(item, str):
                                    allocated_nodes.append(item)

                    # Final fallback: allocating_node or batch_host may contain a node name
                    if not allocated_nodes:
                        allocating = job.get('allocating_node') or job.get('batch_host')
                        if allocating:
                            allocated_nodes = [str(allocating)]

                    return {
                        "id": str(job.get('job_id', 0)),
                        "name": job.get('name', ''),
                        "state": job.get('job_state', 'unknown'),
                        "nodes": allocated_nodes,
                        "node_count": job.get('node_count', 0),
                        "partition": job.get('partition', ''),
                        "account": job.get('account', '')
                    }
            
            return {}
            
        except Exception as e:
            raise RuntimeError(f"Failed to get job details: {str(e)}")
    
    def _parse_node_list(self, node_list: str) -> List[str]:
        """Parse SLURM node list format (e.g., 'mel2001,mel2002' or 'mel[2001-2003]')."""
        if not node_list:
            return []
        
        nodes = []
        
        # Handle comma-separated nodes
        for part in node_list.split(','):
            part = part.strip()
            
            # Handle range format like mel[2001-2003]
            if '[' in part and ']' in part:
                prefix = part.split('[')[0]
                range_part = part.split('[')[1].split(']')[0]
                
                if '-' in range_part:
                    start, end = map(int, range_part.split('-'))
                    for i in range(start, end + 1):
                        nodes.append(f"{prefix}{i:04d}")
                else:
                    nodes.append(f"{prefix}{range_part}")
            else:
                # Simple node name
                nodes.append(part)
        
        return nodes
    
    def _find_recipe(self, recipe_name: str) -> Path:
        """Find recipe file by name."""
        recipes_dir = self.base_path / "src" / "recipes"
        
        if "/" in recipe_name:
            category, name = recipe_name.split("/", 1)
            recipe_path = recipes_dir / category / f"{name}.yaml"
        else:
            # Search all categories
            for yaml_file in recipes_dir.rglob(f"{recipe_name}.yaml"):
                return yaml_file
            recipe_path = None
        
        if not recipe_path or not recipe_path.exists():
            raise FileNotFoundError(f"Recipe '{recipe_name}' not found")
        return recipe_path
    
    def _create_job_payload(self, recipe: Dict[str, Any], config: Dict[str, Any], recipe_name: str, recipe_path: Path) -> Dict[str, Any]:
        """Create SLURM job payload according to official API schema."""
        resources = recipe.get("resources", {})
        # Determine time_limit (in minutes) from recipe resources using utility
        time_limit_minutes = parse_time_limit(resources.get("time_limit"))

        # Build the job description according to v0.0.40 schema
        job_desc = {
            "account": self.account,
            "qos": "short",
            "time_limit": time_limit_minutes,  
            "current_working_directory": str(self.base_path / "logs"),
            "name": recipe['name'],
            "nodes": config.get("nodes", 1),
            "cpus_per_task": int(resources.get("cpu", 4)), 
            "memory_per_cpu": resources.get("memory", "8G"),  
            "partition": "gpu" if resources.get("gpu") else "cpu",
            "standard_output": f"{recipe['name']}_%j.out",
            "standard_error": f"{recipe['name']}_%j.err",
            "environment": self._format_environment(recipe.get("environment", {}))  # Array of KEY=VALUE
        }        # The official API expects the job description under 'job' key with script
        
        log_dir = self.base_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        return {
            "script": self._create_script(recipe, recipe_path),
            #"script": "#!/bin/bash\necho Hello World",
            "job": job_desc
        }
    
    def _create_script(self, recipe: Dict[str, Any], recipe_path: Path) -> str:
        """Generate the SLURM job script by composing smaller parts."""
        resources = recipe.get("resources", {})

        # Resolve paths and names
        category = recipe_path.parent.name
        recipes_path = self.base_path / "src" / "recipes"
        container_def = recipe.get("container_def", f"{recipe['name']}.def")
        image_name = recipe.get("image", f"{recipe['name']}.sif")
        def_path, sif_path = self._resolve_container_paths(recipes_path, category, container_def, image_name)

        # Build environment and sections
        env_section = self._build_env_section(recipe.get("environment", {}))
        log_dir = str(self.base_path / "logs")

        build_block = self._build_build_block(sif_path, def_path)
        run_block = self._build_run_block(sif_path, log_dir, resources)

        script = f"""#!/bin/bash -l

# Load required modules
module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0

# Set environment variables
{env_section}

# Debug: Print environment info
echo "=== SLURM Job Debug Info ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Working directory: $(pwd)"
echo "Log directory: {log_dir}"
echo "Container def: {def_path}"
echo "Container sif: {sif_path}"
echo "==========================="

{build_block}

# Ensure log directory exists
mkdir -p {log_dir}

{run_block}

exit $container_exit_code
"""
        return script

    def _resolve_container_paths(self, recipes_path: Path, category: str, container_def: str, image_name: str):
        """Return absolute paths for container def and sif file."""
        def_path = str(recipes_path / category / container_def)
        sif_path = str(recipes_path / category / image_name)
        return def_path, sif_path

    def _build_env_section(self, recipe_env: Dict[str, str]) -> str:
        """Construct the environment export section for the script."""
        env_vars = []
        
        # Always export SERVER_BASE_PATH so it's available inside the container
        env_vars.append(f"export SERVER_BASE_PATH='{self.base_path}'")
        
        for key, value in (recipe_env or {}).items():
            env_vars.append(f"export {key}='{value}'")

        if 'VLLM_WORKDIR' not in (recipe_env or {}):
            env_vars.append("export VLLM_WORKDIR='/workspace' || true")
        if 'HF_HOME' not in (recipe_env or {}):
            env_vars.append("export HF_HOME='/workspace/huggingface_cache' || true")
        if 'VLLM_LOGGING_LEVEL' not in (recipe_env or {}):
            env_vars.append("export VLLM_LOGGING_LEVEL='INFO' || true")

        return "\n".join(env_vars) if env_vars else "# No environment variables"

    def _build_build_block(self, sif_path: str, def_path: str) -> str:
        """Return the bash block that ensures the SIF image exists (and builds it if not)."""
        return f"""
# Build container if needed
if [ ! -f {sif_path} ]; then
    echo 'Building Apptainer image: {sif_path}'
    
    # Set up user-writable directories to avoid permission issues
    export APPTAINER_TMPDIR=/tmp/apptainer-$USER-$$
    export APPTAINER_CACHEDIR=/tmp/apptainer-cache-$USER
    export HOME=/tmp/fake-home-$USER
    
    mkdir -p $APPTAINER_TMPDIR $APPTAINER_CACHEDIR $HOME/.apptainer
    
    # Create empty docker config to bypass authentication
    echo '{{}}' > $HOME/.apptainer/docker-config.json
    
    # Build container
    apptainer build --disable-cache --no-https {sif_path} {def_path}
    build_result=$?
    
    # Clean up
    rm -rf $APPTAINER_TMPDIR $APPTAINER_CACHEDIR $HOME
    
    if [ $build_result -ne 0 ]; then
        echo "ERROR: Failed to build container (exit code: $build_result)"
        exit 1
    fi
    
    echo "Container build successful!"
fi
"""

    def _build_run_block(self, sif_path: str, log_dir: str, resources: Dict[str, Any]) -> str:
        """Return the bash block that runs the container with proper binds and flags."""
        # Project workspace binding
        project_ws = str(self.base_path)
        nv_flag = "--nv" if resources.get('gpu') else ""
        return f"""
echo "Starting container..."
echo "Running vLLM container (no network binding, unprivileged user)..."
echo "Binding project workspace: {project_ws} -> /workspace"

# Determine apptainer flags (e.g. use --nv when GPUs are requested)
APPTAINER_FLAGS="{nv_flag}"
echo "Apptainer flags: $APPTAINER_FLAGS"

apptainer run $APPTAINER_FLAGS --bind {log_dir}:/app/logs,{project_ws}:/workspace {sif_path} 2>&1
container_exit_code=$?

echo "Container exited with code: $container_exit_code"
if [ $container_exit_code -ne 0 ]; then
    echo "ERROR: Container failed to run properly"
fi
"""
    
    def _format_environment(self, env_dict: Dict[str, str]) -> List[str]:
        """Format environment variables as array of KEY=VALUE strings"""
        env_list = [
            f"USER={self.username}",
            f"SERVER_BASE_PATH={self.base_path}"  # Pass base path to job environment
        ]
        for key, value in env_dict.items():
            env_list.append(f"{key}={value}")
        return env_list
    
    