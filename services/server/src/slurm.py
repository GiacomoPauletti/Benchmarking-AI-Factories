"""
SLURM job submission and management via SSH tunnel to MeluXina.
Designed for local Docker development with remote job submission.
"""

import yaml
import os
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List
from utils import parse_time_limit
from datetime import datetime


class SlurmDeployer:
    """Handles SLURM job submission and management via SSH tunnel to MeluXina.
    
    Designed for local development: runs in Docker container on laptop and submits
    jobs to MeluXina cluster via SSH.
    """
    
    def __init__(self, account: str = "p200981"):
        self.logger = logging.getLogger(__name__)
        self.account = account
        self.username = os.getenv('USER', 'unknown')
        
        # SSH configuration for MeluXina access
        self.ssh_host = os.getenv('SSH_TUNNEL_HOST', 'login.lxp.lu')
        self.ssh_user = os.getenv('SSH_TUNNEL_USER')
        if not self.ssh_user:
            raise ValueError("SSH_TUNNEL_USER must be set. Check your .env.local file.")
        
        self.logger.info(f"Initializing SLURM deployer with SSH tunnel to {self.ssh_user}@{self.ssh_host}")
        self._setup_ssh_tunnel()
        
        # Base path configuration
        env_base_path = os.getenv('SERVER_BASE_PATH')
        self.base_path = Path(env_base_path)
        print(f"Using SERVER_BASE_PATH from environment: {self.base_path}")
        self.logger.debug(f"Using SERVER_BASE_PATH from environment: {self.base_path}")
        # Load SLURM state normalization mapping from YAML file in server folder
        try:
            map_path = self.base_path / 'src' / 'mappings' / 'slurm_state_map.yaml'
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
    
    def _setup_ssh_tunnel(self):
        """Establish and test SSH connection to MeluXina for tunnel mode."""
        try:
            result = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 f"{self.ssh_user}@{self.ssh_host}", "echo", "SSH connection test"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.logger.info(f"SSH connection to {self.ssh_user}@{self.ssh_host} established successfully")
            else:
                raise ConnectionError(f"SSH connection failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise ConnectionError(f"SSH connection to {self.ssh_host} timed out")
        except Exception as e:
            self.logger.error(f"Failed to establish SSH tunnel: {e}")
            raise
    
    def _execute_remote_command(self, command: str, timeout: int = 30) -> str:
        """Execute command on MeluXina via SSH.
        
        Args:
            command: Shell command to execute on MeluXina
            timeout: Command timeout in seconds
            
        Returns:
            Command stdout output
            
        Raises:
            RuntimeError: If command execution fails
        """
        ssh_command = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            f"{self.ssh_user}@{self.ssh_host}",
            command
        ]
        try:
            result = subprocess.run(
                ssh_command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode != 0:
                raise RuntimeError(f"Remote command failed: {result.stderr}")
            return result.stdout
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Remote command timed out after {timeout}s")
    
    def _submit_job_via_ssh(self, job_script: str) -> str:
        """Submit SLURM job via SSH by writing script to remote temp file and calling sbatch.
        
        Args:
            job_script: Complete SLURM batch script content
            
        Returns:
            SLURM job ID
        """
        try:
            # Create temp file for job script
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as tmp:
                tmp.write(job_script)
                local_script = tmp.name
            
            # Generate remote temp path
            remote_script = f"/tmp/slurm_job_{os.path.basename(local_script)}"
            
            # Copy script to remote
            scp_command = [
                "scp",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=10",
                local_script,
                f"{self.ssh_user}@{self.ssh_host}:{remote_script}"
            ]
            
            result = subprocess.run(scp_command, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(f"Failed to copy script to remote: {result.stderr}")
            
            # Submit job via sbatch
            output = self._execute_remote_command(f"sbatch {remote_script}", timeout=30)
            
            # Clean up remote script
            try:
                self._execute_remote_command(f"rm -f {remote_script}", timeout=10)
            except:
                pass  # Best effort cleanup
            
            # Clean up local temp file
            try:
                os.unlink(local_script)
            except:
                pass
            
            # Parse job ID from sbatch output (format: "Submitted batch job 12345")
            if "Submitted batch job" in output:
                job_id = output.strip().split()[-1]
                self.logger.info(f"Job submitted via SSH tunnel: {job_id}")
                return job_id
            else:
                raise RuntimeError(f"Unexpected sbatch output: {output}")
                
        except Exception as e:
            self.logger.error(f"Failed to submit job via SSH: {e}")
            raise RuntimeError(f"SSH job submission failed: {str(e)}")
    
    def submit_job(self, recipe_name: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Submit a job to MeluXina SLURM cluster via SSH.
        
        Generates a complete SLURM batch script and submits it via sbatch over SSH.
        """
        # Load recipe
        recipe_path = self._find_recipe(recipe_name)
        with open(recipe_path, 'r') as f:
            recipe = yaml.safe_load(f)
        
        # Generate job payload and script
        job_payload = self._create_job_payload(recipe, config or {}, recipe_name, recipe_path)
        job_script = self._create_standalone_script(job_payload, recipe)
        
        # Submit job via SSH
        self.logger.info(f"Submitting job '{recipe['name']}' to MeluXina via SSH")
        job_id = self._submit_job_via_ssh(job_script)
        
        return {
            "id": str(job_id),
            "name": f"{recipe['name']}-{job_id}",
            "recipe_name": recipe_name,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "config": config or {}
        }
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running SLURM job by job ID via SSH."""
        try:
            self._execute_remote_command(f"scancel {job_id}", timeout=10)
            self.logger.info(f"Cancelled job {job_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel job {job_id}: {e}")
            return False
    
    def get_job_status(self, job_id: str) -> str:
        """Get the status of a SLURM job by job ID via SSH, with detailed status from logs if running."""
        try:
            # Use squeue to get job state
            output = self._execute_remote_command(
                f"squeue -j {job_id} -h -o '%T'",
                timeout=10
            )
            
            if output.strip():
                # Job found in queue
                status = output.strip().lower()
                basic_status = self._normalize_slurm_state(status)
                
                if basic_status != 'running':
                    return basic_status
                    
                # If running, check logs for more detail
                try:
                    return self._get_detailed_status_from_logs(job_id)
                except Exception as e:
                    self.logger.error(f"Error parsing logs for detailed status of job {job_id}: {e}")
                    return 'running'
            else:
                # Job not in queue - check if it completed or failed
                # Use sacct to check job history
                try:
                    output = self._execute_remote_command(
                        f"sacct -j {job_id} -n -o state -X",
                        timeout=10
                    )
                    if output.strip():
                        status = output.strip().lower()
                        return self._normalize_slurm_state(status)
                except:
                    pass
                
                return "completed"
                
        except Exception as e:
            self.logger.error(f"Failed to get job status for {job_id}: {e}")
            raise RuntimeError(f"Failed to get job status: {str(e)}")
    
    def _get_detailed_status_from_logs(self, job_id: str) -> str:
        """Parse job logs to determine detailed status for running jobs.
        
        Returns one of: 'building', 'starting', 'running', 'completed'
        """
        logs = self.get_job_logs(job_id)
        
        # Check if log files don't exist yet or are empty
        # This typically means the job just started running
        if 'File not found' in logs and logs.count('File not found') >= 2:
            # Both stdout and stderr don't exist yet
            return 'starting'
        
        # Check if container exited
        if 'Container exited' in logs:
            return 'completed'
        
        # Check for building phase
        if 'Building Apptainer image' in logs or 'apptainer build' in logs.lower():
            if 'Container build successful' in logs or 'Starting container' in logs:
                # Build finished, move to next check
                pass
            else:
                return 'building'
        
        # Check if application is fully ready
        if 'Application startup complete' in logs or 'Uvicorn running on' in logs:
            return 'running'
        
        # Check for starting phase (container started but app not ready yet)
        if 'Starting container' in logs or 'Running vLLM container' in logs or 'Starting vLLM' in logs:
            return 'starting'
        
        # Default to starting for very new jobs, not running
        # This handles the case where logs exist but don't have clear indicators yet
        return 'starting'
    
    def list_jobs(self, user_filter: str = None) -> list:
        """List all jobs from SLURM cluster via SSH, optionally filtered by user."""
        try:
            # Use squeue to get all jobs for the user
            user = user_filter or self.ssh_user
            output = self._execute_remote_command(
                f"squeue -u {user} -h -o '%i|%j|%T|%a|%P|%D|%u'",
                timeout=15
            )
            
            user_jobs = []
            if output.strip():
                for line in output.strip().split('\n'):
                    parts = line.split('|')
                    if len(parts) >= 7:
                        job_id, name, state, account, partition, nodes, job_user = parts
                        user_jobs.append({
                            "id": job_id.strip(),
                            "name": name.strip(),
                            "status": self._normalize_slurm_state(state.strip()),
                            "account": account.strip(),
                            "partition": partition.strip(),
                            "nodes": int(nodes.strip()) if nodes.strip().isdigit() else 0,
                            "user": job_user.strip(),
                            "recipe_name": "unknown",  # Could parse from job name
                            "config": {},
                            "created_at": "unknown"
                        })
            
            return user_jobs
            
        except Exception as e:
            self.logger.error(f"Failed to list jobs: {e}")
            raise RuntimeError(f"Failed to list jobs: {str(e)}")

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
        """Get detailed information about a SLURM job including allocated nodes via SSH."""
        try:
            # Use squeue to get detailed job information
            output = self._execute_remote_command(
                f"squeue -j {job_id} -h -o '%i|%j|%T|%a|%P|%D|%N'",
                timeout=10
            )
            
            if output.strip():
                parts = output.strip().split('|')
                if len(parts) >= 7:
                    job_id, name, state, account, partition, node_count, node_list = parts
                    
                    # Parse node list
                    allocated_nodes = []
                    if node_list.strip():
                        try:
                            allocated_nodes = self._parse_node_list(node_list.strip())
                        except Exception:
                            allocated_nodes = [node_list.strip()]
                    
                    return {
                        "id": job_id.strip(),
                        "name": name.strip(),
                        "state": state.strip(),
                        "nodes": allocated_nodes,
                        "node_count": int(node_count.strip()) if node_count.strip().isdigit() else 0,
                        "partition": partition.strip(),
                        "account": account.strip()
                    }
            
            # Job not in queue, try sacct
            try:
                output = self._execute_remote_command(
                    f"sacct -j {job_id} -n -o jobid,jobname,state,account,partition,nnodes,nodelist -X",
                    timeout=10
                )
                if output.strip():
                    parts = output.strip().split()
                    if len(parts) >= 7:
                        return {
                            "id": parts[0],
                            "name": parts[1],
                            "state": parts[2],
                            "account": parts[3],
                            "partition": parts[4],
                            "node_count": int(parts[5]) if parts[5].isdigit() else 0,
                            "nodes": self._parse_node_list(parts[6]) if len(parts) > 6 else []
                        }
            except:
                pass
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Failed to get job details for {job_id}: {e}")
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
        # Merge resources: recipe defaults + config overrides
        resources = recipe.get("resources", {}).copy()
        if "resources" in config:
            resources.update(config["resources"])
        
        # Determine time_limit (in minutes) from merged resources using utility
        time_limit_minutes = parse_time_limit(resources.get("time_limit"))

        # Merge environment variables: recipe defaults + config overrides
        merged_env = recipe.get("environment", {}).copy()
        if "environment" in config:
            merged_env.update(config["environment"])

        # Build the job description according to v0.0.40 schema
        job_desc = {
            "account": self.account,
            "qos": "short",
            "time_limit": time_limit_minutes,  
            "current_working_directory": str(self.base_path / "logs"),
            "name": recipe['name'],
            "nodes": int(resources.get("nodes", 1)),
            "cpus_per_task": int(resources.get("cpu", 4)), 
            "memory_per_cpu": resources.get("memory", "8G"),  
            "partition": "gpu" if resources.get("gpu") else "cpu",
            "standard_output": f"{recipe['name']}_%j.out",
            "standard_error": f"{recipe['name']}_%j.err",
            "environment": self._format_environment(merged_env)  # Array of KEY=VALUE with merged environment
        }        # The official API expects the job description under 'job' key with script
        
        log_dir = self.base_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        return {
            "script": self._create_script(recipe, recipe_path, merged_env, resources),
            #"script": "#!/bin/bash\necho Hello World",
            "job": job_desc
        }
    
    def _create_standalone_script(self, job_payload: Dict[str, Any], recipe: Dict[str, Any]) -> str:
        """Create a complete SLURM batch script from job payload for SSH submission.
        
        Combines SLURM directives from job_payload['job'] with the script content.
        """
        job_desc = job_payload['job']
        script_content = job_payload['script']
        
        # Build SLURM directives
        directives = [
            "#!/bin/bash -l",
            f"#SBATCH --account={job_desc['account']}",
            f"#SBATCH --qos={job_desc.get('qos', 'short')}",
            f"#SBATCH --time={job_desc['time_limit']}",
            f"#SBATCH --job-name={job_desc['name']}",
            f"#SBATCH --nodes={job_desc['nodes']}",
            f"#SBATCH --cpus-per-task={job_desc['cpus_per_task']}",
            f"#SBATCH --mem-per-cpu={job_desc['memory_per_cpu']}",
            f"#SBATCH --partition={job_desc['partition']}",
            f"#SBATCH --output={job_desc['standard_output']}",
            f"#SBATCH --error={job_desc['standard_error']}",
        ]
        
        # Add working directory if specified
        if 'current_working_directory' in job_desc:
            directives.append(f"#SBATCH --chdir={job_desc['current_working_directory']}")
        
        # Combine directives with script content
        full_script = "\n".join(directives) + "\n\n" + script_content
        return full_script
    
    def _create_script(self, recipe: Dict[str, Any], recipe_path: Path, merged_env: Dict[str, str] = None, merged_resources: Dict[str, Any] = None) -> str:
        """Generate the SLURM job script by composing smaller parts."""
        # Use merged resources or fall back to recipe resources
        resources = merged_resources if merged_resources is not None else recipe.get("resources", {})

        # Use merged environment or fall back to recipe environment
        environment = merged_env if merged_env is not None else recipe.get("environment", {})

        # Resolve paths and names
        category = recipe_path.parent.name
        recipes_path = self.base_path / "src" / "recipes"
        container_def = recipe.get("container_def", f"{recipe['name']}.def")
        image_name = recipe.get("image", f"{recipe['name']}.sif")
        def_path, sif_path = self._resolve_container_paths(recipes_path, category, container_def, image_name)

        # Build environment and sections
        env_section = self._build_env_section(environment)
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

        # Add APPTAINERENV_ prefixed versions for Apptainer to pick up
        # Apptainer automatically imports APPTAINERENV_* variables
        for key, value in (recipe_env or {}).items():
            env_vars.append(f"export APPTAINERENV_{key}='{value}'")

        if 'VLLM_WORKDIR' not in (recipe_env or {}):
            env_vars.append("export VLLM_WORKDIR='/workspace' || true")
            env_vars.append("export APPTAINERENV_VLLM_WORKDIR='/workspace' || true")
        if 'HF_HOME' not in (recipe_env or {}):
            env_vars.append("export HF_HOME='/workspace/huggingface_cache' || true")
            env_vars.append("export APPTAINERENV_HF_HOME='/workspace/huggingface_cache' || true")
        if 'VLLM_LOGGING_LEVEL' not in (recipe_env or {}):
            env_vars.append("export VLLM_LOGGING_LEVEL='INFO' || true")
            env_vars.append("export APPTAINERENV_VLLM_LOGGING_LEVEL='INFO' || true")

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

# Debug: Print environment variables that should be passed to container
echo "Environment variables for container:"
env | grep -E '^VLLM_|^HF_|^CUDA_' || echo "No VLLM/HF/CUDA vars found"

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
    
    