"""
SLURM job submission and management via REST API with SSH tunnel to MeluXina.
Designed for local Docker development with remote job submission using SLURM REST API.
"""

import yaml
import requests
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from utils import parse_time_limit
from datetime import datetime
from ssh_manager import SSHManager
from recipe_builders import BuilderRegistry, ScriptPaths
from job_cache_manager import JobCacheManager


class SlurmDeployer:
    """Handles SLURM job submission and management via REST API over SSH tunnel.
    
    Designed for local development: runs in Docker container on laptop and submits
    jobs to MeluXina cluster via SLURM REST API through an SSH tunnel.
    """
    
    def __init__(self, account: str = "p200981"):
        self.logger = logging.getLogger(__name__)
        self.account = account
        
        # Initialize job cache manager
        self.cache_manager = JobCacheManager(cache_ttl=25, update_interval=6)
        
        # Initialize SSH manager for all remote operations
        self.ssh_manager = SSHManager()
        self.ssh_user = self.ssh_manager.ssh_user
        self.ssh_host = self.ssh_manager.ssh_host
        
        # Use SSH_USER as the username for SLURM operations
        self.username = self.ssh_user
        
        # Get or fetch SLURM JWT token
        self.token = os.getenv('SLURM_JWT')
        if not self.token:
            self.logger.info("SLURM_JWT not set, fetching fresh token from MeluXina...")
            try:
                self.token = self.ssh_manager.get_slurm_token()
            except Exception as e:
                raise RuntimeError(f"Failed to fetch SLURM token: {e}")
        else:
            self.logger.info("Using SLURM_JWT from environment")
        
        self.logger.info(f"Initializing SLURM deployer with REST API via SSH tunnel to {self.ssh_user}@{self.ssh_host}")
        
        # Setup SSH tunnel for SLURM REST API
        self.rest_api_port = self.ssh_manager.setup_slurm_rest_tunnel()
        
        # Base path configuration
        # LOCAL_BASE_PATH: Where recipes/configs are stored locally (in Docker container)
        # REMOTE_BASE_PATH: Where recipes/logs will be stored on MeluXina
        self.local_base_path = Path(os.getenv('LOCAL_BASE_PATH', '/app'))
        
        # Get remote base path from env (required)
        self.remote_base_path = os.getenv('REMOTE_BASE_PATH')
        if not self.remote_base_path:
            # REMOTE_BASE_PATH is required for remote operations; fail fast
            raise RuntimeError(
                "REMOTE_BASE_PATH environment variable is required but not set. "
                "Please set REMOTE_BASE_PATH to the remote base path on MeluXina."
            )
        else:
            self.logger.info(f"Using REMOTE_BASE_PATH: {self.remote_base_path}")
        
        # Ensure remote directories exist
        try:
            self.ssh_manager.ensure_remote_directories(self.remote_base_path)
        except Exception as e:
            self.logger.warning(f"Could not ensure remote directories: {e}")
            
        print(f"Local base path (for recipes): {self.local_base_path}")
        print(f"Remote base path (for SLURM jobs): {self.remote_base_path}")
        self.logger.debug(f"Local: {self.local_base_path}, Remote: {self.remote_base_path}")
        
        # SLURM REST API configuration (via SSH tunnel)
        self.base_url = f"http://localhost:{self.rest_api_port}/slurm/v0.0.40"
        self.headers = {
            'X-SLURM-USER-NAME': self.username,
            'X-SLURM-USER-TOKEN': self.token,
            'Content-Type': 'application/json'
        }
        
        self.logger.info(f"SLURM REST API: {self.base_url}")
        self.logger.info(f"Authenticating as user: {self.username}")
        
        # Load SLURM state normalization mapping from YAML file in server folder
        try:
            map_path = self.local_base_path / 'src' / 'mappings' / 'slurm_state_map.yaml'
            if map_path.exists():
                with open(map_path, 'r') as mf:
                    try:
                        self._state_map = yaml.safe_load(mf) or {}
                    except Exception:
                        self._state_map = {}
            else:
                self._state_map = {}
        except Exception:
            self._state_map = {}
        
        # Set up cache manager callbacks and start background updates
        self.cache_manager.set_fetch_callbacks(
            fetch_status=self._fetch_status_uncached,
            fetch_logs=self._fetch_job_logs_uncached,
            fetch_details=self._fetch_job_details_uncached
        )
        self.cache_manager.start_background_updates()
    
    def __del__(self):
        """Clean up background threads on deletion."""
        try:
            self.cache_manager.stop_background_updates()
        except Exception:
            pass
    
    def submit_job(self, recipe_name: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Submit a job to SLURM cluster using recipe configuration via REST API.
        
        Note: Recipes should be synced to MeluXina before starting the server
        (handled by launch_local.sh). This method assumes recipes are already present.
        """
        # Ensure logs directory exists on remote before submitting job
        # (SLURM needs this directory to exist BEFORE job starts)
        remote_log_dir = f"{self.remote_base_path}/logs"
        self.ssh_manager.create_remote_directory(remote_log_dir)
        
        # Ensure persistent HuggingFace cache directory exists
        # This allows model weights to persist across jobs and be shared across nodes
        remote_hf_cache = f"{self.remote_base_path}/huggingface_cache"
        self.ssh_manager.create_remote_directory(remote_hf_cache)
        
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
        
        # Track this job for background updates IMMEDIATELY
        self.cache_manager.track_job(str(job_id))
        
        # Pre-warm the cache by fetching initial status and details
        # This ensures the cache is hot when the first prompt arrives
        try:
            initial_status = self.get_job_status(str(job_id))
            self.get_job_details(str(job_id))
            self.logger.debug(f"Pre-warmed cache for new job {job_id} (status: {initial_status})")
        except Exception as e:
            self.logger.warning(f"Failed to pre-warm cache for job {job_id}: {e}")
            # Not critical - background updates will handle it
        
        return {
            "id": str(job_id),  # Use SLURM job ID directly as service ID
            "name": f"{recipe['name']}-{job_id}",
            "recipe_name": recipe_name,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "config": config or {}
        }
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running SLURM job by job ID via REST API."""
        try:
            response = requests.delete(
                f"{self.base_url}/job/{job_id}", 
                headers=self.headers
            )
            response.raise_for_status()
            
            # Stop tracking this job
            self.cache_manager.untrack_job(str(job_id))
            
            return True
        except:
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the caching system for debugging."""
        return self.cache_manager.get_stats()
    
    def get_job_status(self, job_id: str) -> str:
        """Get the status of a SLURM job by job ID via REST API.
        
        Uses cached status if available and fresh, otherwise fetches and caches.
        
        Args:
            job_id: The SLURM job ID
            
        Returns:
            Slurm Status string: 'pending', 'running', 'completed', 'failed', etc.
        """
        return self.cache_manager.get_status(str(job_id))
    
    def _fetch_status_uncached(self, job_id: str) -> str:
        """Fetch status from SLURM API without using cache.
        
        This is used as a callback by the cache manager.
        """
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
                    if isinstance(job_state, list):
                        status = job_state[0].lower() if job_state else 'unknown'
                    elif isinstance(job_state, str):
                        status = job_state.lower()
                    else:
                        status = str(job_state).lower()
                    return self._normalize_slurm_state(status)
            
            # Job not found - mark as completed
            return "completed"
            
        except Exception as e:
            self.logger.warning(f"Failed to fetch status for job {job_id}: {e}")
            return "unknown"
    
    def get_detailed_status_from_logs(self, job_id: str, ready_indicators: List[str] = None, 
                                       starting_indicators: List[str] = None) -> str:
        """Parse job logs to determine detailed status for running jobs.
        
        This is a helper method that services can use to implement their own
        service-specific readiness detection.
        
        Args:
            job_id: The SLURM job ID
            ready_indicators: List of strings that indicate service is fully ready
            starting_indicators: List of strings that indicate service is starting
            
        Returns:
            One of: 'building', 'starting', 'running', 'completed'
        """
        job_id = str(job_id)
        
        # Ensure this job is being tracked for background updates
        self.cache_manager.track_job(job_id)
        
        # Default indicators for backward compatibility (vLLM-specific)
        if ready_indicators is None:
            ready_indicators = ['Application startup complete', 'Uvicorn running on']
        if starting_indicators is None:
            starting_indicators = ['Starting container', 'Running vLLM container', 'Starting vLLM']
        
        logs = self.get_job_logs(job_id)
        
        # Check if log files don't exist yet or are empty
        if 'File not found' in logs and logs.count('File not found') >= 2:
            return 'starting'
        
        # Check if container exited
        if 'Container exited' in logs:
            # Job completed - stop tracking it
            self.cache_manager.untrack_job(job_id)
            return 'completed'
        
        # Check for building phase
        if 'Building Apptainer image' in logs or 'apptainer build' in logs.lower():
            if 'Container build successful' in logs or 'Starting container' in logs:
                pass  # Build finished, continue checking
            else:
                return 'building'
        
        # Check if application is fully ready (using provided indicators)
        found_ready = False
        for indicator in ready_indicators:
            if indicator in logs:
                found_ready = True
                break
        
        if found_ready:
            return 'running'
        
        # Debug: Log what we're actually seeing if no ready indicators match
        self.logger.debug(f"Job {job_id}: No ready indicators found. Checking starting indicators...")
        self.logger.debug(f"Ready indicators checked: {ready_indicators}")
        # Show a sample of the logs (last 500 chars)
        log_sample = logs[-500:] if len(logs) > 500 else logs
        self.logger.debug(f"Log sample (last 500 chars): {log_sample}")
        
        # Check for starting phase (using provided indicators)
        for indicator in starting_indicators:
            if indicator in logs:
                return 'starting'
        
        # Default to starting for jobs without clear indicators
        return 'starting'
    
    def list_jobs(self, user_filter: str = None) -> list:
        """List all jobs from SLURM cluster via REST API, optionally filtered by user."""
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
                    
                    user_jobs.append({
                        "id": str(job.get('job_id', 0)),  # Use SLURM job ID directly as service ID
                        "name": job.get('name', 'unnamed'),
                        "status": self._normalize_slurm_state(status),
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

    def _normalize_slurm_state(self, raw_state: str) -> str:
        """Normalize a raw SLURM state string using the loaded YAML mapping.

        Falls back to simple heuristics if mapping is unavailable.
        """
        if not raw_state:
            return 'unknown'
        s = str(raw_state).strip().lower()

        # Try to use mapping from YAML if present
        try:
            for canonical, aliases in (self._state_map or {}).items():
                if not aliases:
                    continue
                for a in aliases:
                    if not a:
                        continue
                    if s == str(a).strip().lower():
                        return canonical
                    # match prefix/similar
                    if str(a).strip().lower() in s:
                        return canonical
        except Exception:
            pass

        # Fallback heuristics
        if s in ("r", "running") or s.startswith("run"):
            return 'running'
        if s in ("pd", "pending") or s.startswith("pd") or s.startswith("pend"):
            return 'pending'
        if s.startswith("comp") or s in ("cd", "completed"):
            return 'completed'
        if s.startswith("fail") or s in ("f", "failed") or "node_fail" in s or "timeout" in s:
            return 'failed'
        if s.startswith("cancel") or s in ("ca", "cancelled", "canceled"):
            return 'cancelled'
        return 'unknown'
    
    def _fetch_remote_log_file(self, remote_path: str, local_path: Path) -> bool:
        """Fetch a log file from the remote MeluXina filesystem via SSH.
        
        Args:
            remote_path: Absolute path to the log file on MeluXina
            local_path: Local path where the file should be saved
            
        Returns:
            True if file was successfully fetched, False otherwise
        """
        return self.ssh_manager.fetch_remote_file(remote_path, local_path)
    
    def _fetch_remote_log_file_tail(self, remote_path: str, local_path: Path, lines: int = 200) -> bool:
        """Fetch only the last N lines of a log file from remote using tail.
        
        This is much faster than fetching the entire file, especially for large logs.
        
        Args:
            remote_path: Absolute path to the log file on MeluXina
            local_path: Local path where the file should be saved
            lines: Number of lines to fetch from the end of the file
            
        Returns:
            True if file was successfully fetched, False otherwise
        """
        import subprocess
        
        try:
            # Check if file exists on remote
            exists, _, _ = self.ssh_manager.execute_remote_command(
                f"test -f {remote_path}", 
                timeout=5
            )
            
            if not exists:
                self.logger.debug(f"Remote file does not exist: {remote_path}")
                return False
            
            # Use tail to fetch only the last N lines
            cmd = self.ssh_manager.ssh_base_cmd + [
                self.ssh_manager.ssh_target, 
                f"tail -n {lines} {remote_path}"
            ]
            
            env = os.environ.copy()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,  # Shorter timeout since we're fetching less data
                env=env
            )
            
            if result.returncode == 0:
                # Save the output to local file
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_text(result.stdout)
                self.logger.debug(f"Successfully fetched last {lines} lines from {remote_path}")
                return True
            else:
                self.logger.warning(f"Failed to fetch tail of {remote_path}: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Timeout fetching tail of remote file: {remote_path}")
            return False
        except Exception as e:
            self.logger.warning(f"Error fetching tail of remote file {remote_path}: {e}")
            return False

    def get_job_logs(self, job_id: str) -> str:
        """Get logs from SLURM job.
        
        Uses cached logs if available and fresh, otherwise fetches from remote.
        """
        return self.cache_manager.get_logs(str(job_id))
    
    def _fetch_job_logs_uncached(self, job_id: str) -> str:
        """Get logs from SLURM job, fetching from remote if needed.
        
        Optimized to fetch only the last 200 lines using tail for faster retrieval.
        Only fetches stdout since stderr rarely contains readiness indicators.
        """
        try:
            # Use local path for cached logs
            local_log_dir = self.local_base_path / "logs"
            local_log_dir.mkdir(parents=True, exist_ok=True)
            
            # Use remote path for the actual log location on MeluXina (as string)
            remote_log_dir = f"{self.remote_base_path}/logs"

            # Get job details to find the recipe name (which is used in SLURM log filenames)
            job_details = self.get_job_details(job_id)
            recipe_name = job_details.get('name', 'unknown') if job_details else 'unknown'
            
            # SLURM creates log files as: {recipe_name}_{job_id}.out
            # (using the 'name' field from job submission, which is the recipe name)
            stdout_local = local_log_dir / f"{recipe_name}_{job_id}.out"
            stdout_remote = f"{remote_log_dir}/{recipe_name}_{job_id}.out"
            
            logs = []
            
            # Fetch only the last 200 lines of stdout using tail for faster retrieval
            # (readiness indicators are typically near the end of logs)
            self._fetch_remote_log_file_tail(stdout_remote, stdout_local, lines=200)
            
            if stdout_local.exists():
                try:
                    content = stdout_local.read_text()
                    logs.append(f"=== SLURM STDOUT (last 200 lines) ({stdout_local.name}) ===\n{content}")
                except Exception as e:
                    logs.append(f"=== SLURM STDOUT ===\nError reading {stdout_local.name}: {e}")
            else:
                logs.append(f"=== SLURM STDOUT ===\nLog not yet available (job may not have started)")
            
            return "\n\n".join(logs)
            
        except Exception as e:
            return f"Error retrieving logs for job {job_id}: {str(e)}"
    
    def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """Get detailed information about a SLURM job including allocated nodes.
        
        Uses cached details if available and fresh, otherwise fetches from SLURM API.
        """
        return self.cache_manager.get_details(str(job_id))
    
    def _fetch_job_details_uncached(self, job_id: str) -> Dict[str, Any]:
        """Get detailed information about a SLURM job including allocated nodes via REST API."""
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
        """Parse SLURM node list format (e.g., 'mel2001,mel2002' or 'mel[2001-2003]' or 'mel[2001,2002]')."""
        if not node_list:
            return []
        
        nodes = []
        
        # Check if the entire string uses bracket notation (e.g., "mel[2001,2002]" or "mel[2001-2003]")
        # Must handle this BEFORE splitting on commas
        if '[' in node_list and ']' in node_list:
            # Find the bracket section
            bracket_start = node_list.index('[')
            bracket_end = node_list.index(']')
            prefix = node_list[:bracket_start]
            range_part = node_list[bracket_start+1:bracket_end]
            
            # Check if it's a range (e.g., "2001-2003") or comma-separated list (e.g., "2001,2002")
            if '-' in range_part and ',' not in range_part:
                # Range format: mel[2001-2003]
                start, end = map(int, range_part.split('-'))
                for i in range(start, end + 1):
                    nodes.append(f"{prefix}{i}")
            else:
                # Comma-separated list inside brackets: mel[2001,2002,2003]
                for num in range_part.split(','):
                    nodes.append(f"{prefix}{num.strip()}")
        else:
            # Handle simple comma-separated nodes without brackets
            for part in node_list.split(','):
                part = part.strip()
                if part:
                    nodes.append(part)
        
        return nodes
    
    def _find_recipe(self, recipe_name: str) -> Path:
        """Find recipe file by name (searches locally)."""
        recipes_dir = self.local_base_path / "src" / "recipes"
        
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
        # Merge resources: recipe defaults + config overrides
        resources = recipe.get("resources", {}).copy()
        self.logger.debug(f"Recipe resources before merge: {resources}")
        self.logger.debug(f"Config for merge: {config}")
        
        if "resources" in config:
            resources.update(config["resources"])
        
        # Also handle top-level resource specifications (for backward compatibility)
        # Top-level keys like 'nodes', 'cpu', 'memory', 'gpu', 'time_limit' can override resources
        for key in ['nodes', 'cpu', 'memory', 'gpu', 'time_limit']:
            if key in config:
                resources[key] = config[key]
        
        self.logger.debug(f"Final merged resources: {resources}")
        
        # Determine time_limit (in minutes) from merged resources using utility
        time_limit_minutes = parse_time_limit(resources.get("time_limit"))

        # Merge environment variables: recipe defaults + config overrides
        merged_env = recipe.get("environment", {}).copy()
        if "environment" in config:
            merged_env.update(config["environment"])

        # Build the job description according to v0.0.40 schema
        # Use REMOTE path for SLURM job execution on MeluXina
        # Note: SLURM REST API v0.0.40 is strict about types - use strings for most fields
        log_dir_path = str(Path(self.remote_base_path) / "logs")
        
        job_desc = {
            "account": self.account,
            "qos": "short",
            "time_limit": {
                "number": int(time_limit_minutes),
                "set": True
            },
            "current_working_directory": log_dir_path,  # Required by SLURM
            "name": recipe['name'],
            "nodes": str(resources.get("nodes", 1)),  # Must be string
            "cpus_per_task": int(resources.get("cpu", 4)), 
            "memory_per_cpu": resources.get("memory", "8G"),  
            "partition": "gpu" if resources.get("gpu") else "cpu",
            "standard_output": f"{log_dir_path}/{recipe['name']}_%j.out",
            "standard_error": f"{log_dir_path}/{recipe['name']}_%j.err",
            "environment": self._format_environment(merged_env)  # Array of KEY=VALUE with merged environment
        }        # The official API expects the job description under 'job' key with script
        
        # Create local logs directory for any local logging needs
        local_log_dir = self.local_base_path / "logs"
        local_log_dir.mkdir(parents=True, exist_ok=True)

        # Generate the full script
        full_script = self._create_script(recipe, recipe_path, merged_env, resources)
        
        # Debug: Log script length
        self.logger.debug(f"Generated script length: {len(full_script)} bytes")
        
        return {
            "script": full_script,
            "job": job_desc
        }
    
    def _create_script(self, recipe: Dict[str, Any], recipe_path: Path, merged_env: Dict[str, str] = None, merged_resources: Dict[str, Any] = None) -> str:
        """Generate the SLURM job script using recipe builders."""
        # Use merged resources or fall back to recipe resources
        resources = merged_resources if merged_resources is not None else recipe.get("resources", {})

        # Use merged environment or fall back to recipe environment
        environment = merged_env if merged_env is not None else recipe.get("environment", {})

        # Resolve paths and names
        category = recipe_path.parent.name
        recipe_name = recipe.get('name', '')
        recipes_path = Path(self.remote_base_path) / "src" / "recipes"
        container_def = recipe.get("container_def", f"{recipe_name}.def")
        image_name = recipe.get("image", f"{recipe_name}.sif")
        def_path = str(recipes_path / category / container_def)
        sif_path = str(recipes_path / category / image_name)
        log_dir = str(Path(self.remote_base_path) / "logs")
        
        # Create paths object for builders
        paths = ScriptPaths(
            def_path=def_path,
            sif_path=sif_path,
            log_dir=log_dir,
            remote_base_path=self.remote_base_path
        )
        
        # Get the appropriate builder for this recipe
        # First try recipe-specific builder, then fall back to category builder
        try:
            builder = BuilderRegistry.create_builder(
                category, 
                recipe_name=recipe_name,
                remote_base_path=self.remote_base_path
            )
            self.logger.debug(f"Using builder {builder.__class__.__name__} for recipe {category}/{recipe_name}")
        except ValueError as e:
            self.logger.warning(f"No builder registered for '{category}/{recipe_name}', using inference builder as fallback")
            # Fallback to inference builder for unknown categories
            builder = BuilderRegistry.create_builder('inference', remote_base_path=self.remote_base_path)
        
        # Build script sections using the builder
        env_section = builder.build_environment_section(environment)
        build_block = builder.build_container_build_block(paths)
        
        # Check if recipe supports distributed execution
        distributed_cfg = recipe.get('distributed') if isinstance(recipe, dict) else None
        
        if distributed_cfg and builder.supports_distributed():
            run_block = builder.build_distributed_run_block(paths, resources, recipe, distributed_cfg)
        else:
            run_block = builder.build_run_block(paths, resources, recipe)

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
echo "Recipe category: {category}"
echo "Builder: {builder.__class__.__name__}"
echo "==========================="

{build_block}

# Ensure log directory exists
mkdir -p {log_dir}

{run_block}

exit $container_exit_code
"""
        return script

    def _format_environment(self, env_dict: Dict[str, str]) -> List[str]:
        """Format environment variables as array of KEY=VALUE strings"""
        env_list = [
            f"USER={self.username}"
        ]
        for key, value in env_dict.items():
            env_list.append(f"{key}={value}")
        return env_list
