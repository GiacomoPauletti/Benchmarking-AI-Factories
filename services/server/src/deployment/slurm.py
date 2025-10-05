"""
SLURM job submission and management logic.
Translates recipes into SLURM scripts and runs with Apptainer via SLURM REST API.
"""

import yaml
import requests
import json
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


class SlurmDeployer:
    """Handles SLURM job submission and management for Apptainer workloads via REST API."""
    
    def __init__(self, account: str = "p200981"):
        self.account = account
        self.username = os.getenv('USER', 'unknown')
        self.token = os.getenv('SLURM_JWT')
        if not self.token:
            raise RuntimeError("SLURM_JWT environment variable not set")
        
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
        job_payload = self._create_job_payload(recipe, config or {}, recipe_name)
        
        # Debug: print the payload
        print("Submitting job payload:")
        print(json.dumps(job_payload, indent=2))
        
        response = requests.post(
            f"{self.base_url}/job/submit", 
            headers=self.headers, 
            json=job_payload
        )
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
            # If REST API fails, throw an error - don't guess!
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
        """Get logs from SLURM job via slurmdb API for completed jobs."""
        try:
            # Try slurmdb API first for completed/historical jobs
            slurmdb_url = "http://slurmrestd.meluxina.lxp.lu:6820/slurmdb/v0.0.40"
            response = requests.get(
                f"{slurmdb_url}/job/{job_id}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                jobs = result.get('jobs', [])
                
                if jobs:
                    job = jobs[0]  # Take the first job match
                    
                    logs = []
                    
                    # Get stdout content
                    stdout = job.get('stdout', '')
                    stdout_expanded = job.get('stdout_expanded', '')
                    if stdout_expanded or stdout:
                        logs.append("=== STDOUT ===")
                        logs.append(stdout_expanded or stdout or "No stdout content")
                        logs.append("")
                    
                    # Get stderr content  
                    stderr = job.get('stderr', '')
                    stderr_expanded = job.get('stderr_expanded', '')
                    if stderr_expanded or stderr:
                        logs.append("=== STDERR ===")
                        logs.append(stderr_expanded or stderr or "No stderr content")
                        logs.append("")
                    
                    if logs:
                        return "\n".join(logs)
                    else:
                        # No direct log content, but job exists
                        job_state = job.get('state', {}).get('current', ['unknown'])
                        state = job_state[0] if isinstance(job_state, list) else str(job_state)
                        return f"Job {job_id} found but no log content available. Job state: {state}"
                else:
                    return f"Job {job_id} not found in slurmdb"
            
            elif response.status_code == 404:
                # Job not in slurmdb, try active slurm API
                active_response = requests.get(
                    f"{self.base_url}/job/{job_id}",
                    headers=self.headers,
                    timeout=10
                )
                
                if active_response.status_code == 200:
                    return f"Job {job_id} is still active - logs not available until completion"
                else:
                    return f"Job {job_id} not found in either slurmdb or active jobs"
            
            else:
                return f"Failed to get job info from slurmdb: HTTP {response.status_code}"
                
        except Exception as e:
            return f"Error retrieving job logs via SLURM API: {str(e)}"
    
    def _find_recipe(self, recipe_name: str) -> Path:
        """Find recipe file by name."""
        recipes_dir = Path(__file__).parent.parent / "recipes"
        
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
    
    def _create_job_payload(self, recipe: Dict[str, Any], config: Dict[str, Any], recipe_name: str) -> Dict[str, Any]:
        """Create SLURM job payload according to official API schema."""
        resources = recipe.get("resources", {})
        logs_dir = Path(__file__).parent.parent / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        # Build the job description according to v0.0.40 schema
        job_desc = {
            "account": self.account,
            "qos": "short",
            "time_limit": 10,  # 10 minutes (simple integer)
            "current_working_directory": str(logs_dir.parent),
            "name": recipe['name'],
            "nodes": config.get("nodes", 1),
            "cpus_per_task": int(resources.get("cpu", 4)),  # Simple integer
            "memory_per_cpu": resources.get("memory", "8G"),  # Use as-is, should already be in MB
            "partition": "gpu" if resources.get("gpu") else "cpu",
            "standard_output": f"{logs_dir}/{recipe['name']}_%j.out",
            "standard_error": f"{logs_dir}/{recipe['name']}_%j.err",
            "environment": self._format_environment(recipe.get("environment", {}))  # Array of KEY=VALUE
        }
        
        # The official API expects the job description under 'job' key with script
        return {
            "script": self._create_script(recipe, recipe_name),
            "job": job_desc
        }
    
    def _create_script(self, recipe: Dict[str, Any], recipe_name: str) -> str:
        """Generate the SLURM job script."""
        container_def = recipe.get("container_def", f"{recipe['name']}.def")
        image_name = recipe.get("image", f"{recipe['name']}.sif")
        
        # Get paths
        if "/" in recipe_name:
            category = recipe_name.split("/")[0]
        else:
            category = "simple"  # fallback
        
        base_path = "/home/users/u103056/Benchmarking-AI-Factories/services/server/src/recipes"
        def_path = f"{base_path}/{category}/{container_def}"
        sif_path = f"{base_path}/{category}/{image_name}"
        
        # Environment variables
        env_vars = []
        for key, value in recipe.get("environment", {}).items():
            env_vars.append(f"export {key}={value}")
        env_section = "\n".join(env_vars) if env_vars else "# No environment variables"
        
        # Simple script
        script = f"""#!/bin/bash -l

# Load required modules
module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0

# Set environment variables
{env_section}

# Build container if needed
if [ ! -f {sif_path} ]; then
    echo 'Building Apptainer image: {sif_path}'
    apptainer build {sif_path} {def_path}
fi

# Run container
apptainer run {sif_path}
"""
        return script
    
    def _format_environment(self, env_dict: Dict[str, str]) -> List[str]:
        """Format environment variables as array of KEY=VALUE strings for SLURM v0.0.40."""
        env_list = [f"USER={self.username}"]  # Always include USER
        for key, value in env_dict.items():
            env_list.append(f"{key}={value}")
        return env_list
    
    