import requests
import json
import os
import logging
import subprocess
from pathlib import Path

from ssh_manager import SSHManager

# Use the logger configured by main.py instead of basic config
logger = logging.getLogger(__name__)

class AbstractClientDispatcher:
    def dispatch(self, group_id: int, time_limit: int):
        pass

class SlurmClientDispatcher(AbstractClientDispatcher):
    """
    SLURM client dispatcher for MeluXina HPC cluster.
    Deploys load generator jobs to test vLLM services.
    """

    def __init__(self, load_config: dict, account: str = "p200981", use_container: bool = False):
        """Initialize SLURM client dispatcher.
        
        Args:
            load_config: Dictionary with load test configuration
            account: SLURM account for job submission (default: p200981)
            use_container: Whether to use containerized client execution
        """
        self._load_config = load_config
        self._use_container = use_container
        self._account = account
        
        # Initialize SSH manager for all remote operations
        self._ssh_manager = SSHManager()
        self._username = self._ssh_manager.ssh_user
        
        # Set up remote base path from environment or use default
        # IMPORTANT: SLURM REST API daemon runs as root and cannot handle ~ paths
        # Must expand ~ to absolute path that SLURM daemon can write to
        remote_base_path_template = os.environ.get(
            'REMOTE_BASE_PATH', 
            '~/ai-factory-benchmarks'
        )
        
        # Expand ~ to /home/users/$USER (NOT tier2 - SLURM daemon can't write there)
        if remote_base_path_template.startswith('~'):
            # Use standard home path /home/users/$USER
            self._remote_base_path = remote_base_path_template.replace('~', f'/home/users/{self._username}', 1)
            logger.info(f"Expanded remote path: {remote_base_path_template} -> {self._remote_base_path}")
        else:
            self._remote_base_path = remote_base_path_template
            logger.info(f"Remote base path: {self._remote_base_path}")
        
        self._remote_logs_dir = str(Path(self._remote_base_path) / "logs")
        
        # Use shared SSH tunnel for SLURM REST API (created at service startup on port 6821)
        # Server uses 6820, client uses 6821 to avoid conflicts
        self._rest_api_port = 6821
        self._base_url = f"http://localhost:{self._rest_api_port}/slurm/v0.0.40"
        
        logger.info(f"SLURM REST API available at: {self._base_url}")
        logger.info(f"Authenticating as user: {self._username}, account: {self._account}")
        logger.info(f"Remote base path: {self._remote_base_path}")
        
        # Ensure remote directories exist
        self._ensure_remote_directories()


    def _ensure_remote_directories(self):
        """Create remote base path and logs directory if they don't exist."""
        logger.info("Ensuring remote directories exist...")
        
        # Create base path and logs directory
        cmd = f"mkdir -p {self._remote_base_path} {self._remote_logs_dir}"
        success, stdout, stderr = self._ssh_manager.execute_remote_command(cmd, timeout=10)
        
        if success:
            logger.info(f"Remote directories ready: {self._remote_base_path}")
        else:
            logger.warning(f"Failed to create remote directories: {stderr}")
            # Don't fail - directories might already exist or permissions might be OK


    def _ensure_loadgen_container(self):
        """Ensure the load generator Apptainer container is built on the remote system.
        
        This method checks if the container exists, and if not, uploads the definition
        file and builds it. Container is cached after first build.
        """
        container_dir = f"{self._remote_base_path}/containers"
        container_def_path = f"{container_dir}/loadgen.def"
        container_sif_path = f"{container_dir}/loadgen.sif"
        
        # Check if container already exists
        check_cmd = f"test -f {container_sif_path} && echo 'exists' || echo 'missing'"
        success, stdout, stderr = self._ssh_manager.execute_remote_command(check_cmd, timeout=5)
        
        if success and 'exists' in stdout:
            logger.info(f"Load generator container already exists: {container_sif_path}")
            return
        
        logger.info("Building load generator container (first time setup, ~30-60s)...")
        
        # Create container directory
        mkdir_cmd = f"mkdir -p {container_dir}"
        self._ssh_manager.execute_remote_command(mkdir_cmd, timeout=10)
        
        # Read local container definition
        # The container definition is in services/client/src/client/client_container.def
        local_def_path = Path(__file__).parent.parent / "client" / "client_container.def"
        
        if not local_def_path.exists():
            raise FileNotFoundError(f"Container definition not found: {local_def_path}")
        
        with open(local_def_path, 'r') as f:
            def_content = f.read()
        
        # Upload definition file
        logger.info(f"Uploading container definition to {container_def_path}")
        upload_cmd = f"cat > {container_def_path} << 'CONTAINER_DEF_EOF'\n{def_content}\nCONTAINER_DEF_EOF"
        success, stdout, stderr = self._ssh_manager.execute_remote_command(upload_cmd, timeout=10)
        
        if not success:
            raise RuntimeError(f"Failed to upload container definition: {stderr}")
        
        # Build container using Apptainer
        logger.info("Building Apptainer container (this may take 30-60 seconds)...")
        build_cmd = f"cd {container_dir} && apptainer build {container_sif_path} {container_def_path}"
        success, stdout, stderr = self._ssh_manager.execute_remote_command(build_cmd, timeout=180)
        
        if success:
            logger.info(f"Container built successfully: {container_sif_path}")
        else:
            logger.error(f"Container build failed: {stderr}")
            raise RuntimeError(f"Failed to build load generator container: {stderr}")


    def get_job_logs(self, job_id: str, group_id: int) -> str:
        """Get logs from a SLURM job via SSH.
        
        Args:
            job_id: SLURM job ID
            group_id: Client group ID
            
        Returns:
            Formatted log content or error message
        """
        if not job_id:
            return "=== NO JOB ID ===\nJob ID not available"
        
        stdout_remote = f"{self._remote_logs_dir}/loadgen-{group_id}-{job_id}.out"
        stderr_remote = f"{self._remote_logs_dir}/loadgen-{group_id}-{job_id}.err"
        
        # Fetch stdout using tail for last 200 lines
        stdout_cmd = f"tail -n 200 {stdout_remote} 2>/dev/null || echo 'Log not yet available'"
        success_out, stdout_content, _ = self._ssh_manager.execute_remote_command(stdout_cmd, timeout=10)
        
        # Fetch stderr using tail for last 100 lines
        stderr_cmd = f"tail -n 100 {stderr_remote} 2>/dev/null || echo 'No errors logged'"
        success_err, stderr_content, _ = self._ssh_manager.execute_remote_command(stderr_cmd, timeout=10)
        
        # Format combined output
        log_output = f"=== SLURM STDOUT (last 200 lines) ===\n"
        if success_out:
            log_output += stdout_content if stdout_content else "Log not yet available"
        else:
            log_output += "Failed to fetch stdout"
        
        log_output += f"\n\n=== SLURM STDERR (last 100 lines) ===\n"
        if success_err:
            log_output += stderr_content if stderr_content else "No errors logged"
        else:
            log_output += "Failed to fetch stderr"
        
        return log_output

    def sync_logs_from_remote(self, local_logs_dir: str = "./logs", pattern: str = None, group_id: int = None):
        """Sync SLURM logs from remote MeluXina to local directory.
        
        Args:
            local_logs_dir: Local directory to sync logs to
            pattern: Glob pattern for log files to sync (deprecated, use group_id)
            group_id: Specific group ID to sync logs for (syncs .out, .err, and .json files)
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        logger.info(f"Syncing logs from {self._remote_logs_dir} to {local_logs_dir}...")
        
        # Ensure local logs directory exists with proper permissions
        os.makedirs(local_logs_dir, exist_ok=True)
        
        # Build rsync command based on parameters
        rsync_cmd = [
            "rsync", "-avz",
        ]
        
        if group_id is not None:
            # Sync specific group files only
            rsync_cmd.extend([
                "--include", f"loadgen-{group_id}-*.out",        # SLURM stdout
                "--include", f"loadgen-{group_id}-*.err",        # SLURM stderr
                "--include", f"loadgen-{group_id}-container.log", # Container logs
                "--include", f"loadgen-results-{group_id}.json",  # Results
                "--include", "*/",  # Include directories for recursive search
                "--exclude", "*",   # Exclude everything else
            ])
            logger.debug(f"Syncing logs for group {group_id}")
        elif pattern:
            # Legacy: use pattern (for backwards compatibility)
            rsync_cmd.extend([
                "--include", pattern,
                "--include", pattern.replace('.out', '.err'),
                "--include", "loadgen-results-*.json",
                "--include", "*/",
                "--exclude", "*",
            ])
            logger.debug(f"Syncing logs with pattern {pattern}")
        else:
            # Sync all loadgen logs
            rsync_cmd.extend([
                "--include", "loadgen-*.out",
                "--include", "loadgen-*.err",
                "--include", "loadgen-*-container.log",
                "--include", "loadgen-results-*.json",
                "--include", "*/",
                "--exclude", "*",
            ])
            logger.debug("Syncing all loadgen logs")
        
        # Add source and destination
        rsync_cmd.extend([
            f"{self._ssh_manager.ssh_user}@{self._ssh_manager.ssh_host}:{self._remote_logs_dir}/",
            f"{local_logs_dir}/"
        ])
        
        # Add SSH port option
        rsync_cmd.insert(2, "-e")
        rsync_cmd.insert(3, f"ssh -p {self._ssh_manager.ssh_port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null")
        
        logger.debug(f"Running rsync command: {' '.join(rsync_cmd)}")
        
        try:
            import subprocess
            result = subprocess.run(
                rsync_cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env=os.environ.copy()
            )
            
            if result.returncode == 0:
                logger.info(f"Logs synced successfully")
                logger.debug(f"Rsync stdout: {result.stdout}")
                if result.stderr:
                    logger.debug(f"Rsync stderr: {result.stderr}")
                
                # Fix permissions on synced files so they're readable by the user
                try:
                    import glob
                    for pattern in ["loadgen-*.out", "loadgen-*.err", "loadgen-*.json", "loadgen-*-container.log"]:
                        for file in glob.glob(os.path.join(local_logs_dir, pattern)):
                            try:
                                os.chmod(file, 0o644)
                                logger.debug(f"Fixed permissions for {file}")
                            except Exception as e:
                                logger.warning(f"Could not fix permissions for {file}: {e}")
                except Exception as e:
                    logger.warning(f"Error fixing file permissions: {e}")
                
                return True, "Logs synced successfully"
            else:
                logger.error(f"Rsync failed with return code {result.returncode}")
                logger.error(f"Rsync stderr: {result.stderr}")
                logger.debug(f"Rsync stdout: {result.stdout}")
                return False, f"Rsync failed: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            logger.error("Rsync timeout")
            return False, "Rsync timeout after 60 seconds"
        except Exception as e:
            logger.exception(f"Error syncing logs: {e}")
            return False, f"Error: {str(e)}"



    def dispatch(self, group_id: int, time_limit: int):
        """
        Dispatch load generator job using SLURM.
        Runs via SSH from local client_service to MeluXina.
        
        Args:
            group_id: Group ID to associate with the job
            time_limit: Time limit for the SLURM job in minutes
        """
        logger.info(f"Dispatching load generator for group {group_id}")
        logger.info(f"Config: {json.dumps(self._load_config, indent=2)}")
        
        
        # Build the complete bash script for the load generator
        script_content = self._build_load_generator_script(group_id)
        
        # Prepare job configuration matching server pattern and MeluXina requirements
        # Per https://docs.lxp.lu/web_services/slurmrestd/: these fields are mandatory:
        # - qos, time_limit, account, environment, current_working_directory
        job_config = {
            'account': self._account,
            'qos': 'short', 
            'time_limit': {
                'number': time_limit,
                'set': True
            },
            'name': f'ai-factory-loadgen-{group_id}',
            'partition': 'cpu',
            'nodes': '1',
            'tasks': 1,
            'cpus_per_task': 2,  # Async I/O workload only needs 2 CPUs regardless of client count
            'current_working_directory': self._remote_logs_dir,
            'standard_output': f'{self._remote_logs_dir}/loadgen-{group_id}-%j.out',
            'standard_error': f'{self._remote_logs_dir}/loadgen-{group_id}-%j.err',
            'environment': [f'USER={self._username}'],  # Mandatory per MeluXina docs
        }
        
        # Submit job via SSH
        success, response_data = self._submit_slurm_job_via_ssh(
            script_content=script_content,
            job_config=job_config
        )

        if success:
            # Extract job ID from response
            job_id = None
            if 'job_id' in response_data:
                job_id = str(response_data['job_id'])
            elif 'jobs' in response_data and len(response_data['jobs']) > 0:
                job_id = str(response_data['jobs'][0].get('job_id'))
            
            if job_id:
                logger.info(f"Load generator job submitted successfully! Job ID: {job_id}")
                return job_id
            else:
                logger.warning("Job submitted but no job_id in response")
                logger.debug(json.dumps(response_data, indent=2))
                return None
        else:
            logger.error(f"Job submission failed: {response_data}")
            return None
    
    def _build_load_generator_script(self, group_id: int) -> str:
        """Build the complete bash script to run the load generator on the compute node.
        
        This script:
        1. Loads required modules (env, Apptainer)
        2. Builds the container if it doesn't exist
        3. Runs the load test inside the container with configuration
        """
        # Build the JSON configuration for the load test. Include `prompt_url`
        # when available so the in-container load generator can call the
        # orchestrator data-plane directly.
        load_config = {
            "prompt_url": self._load_config.get('prompt_url'),
            "service_id": self._load_config.get('service_id'),
            "num_clients": self._load_config.get('num_clients'),
            "requests_per_second": self._load_config.get('requests_per_second'),
            "duration_seconds": self._load_config.get('duration_seconds'),
            "prompts": self._load_config.get('prompts'),
            "max_tokens": self._load_config.get('max_tokens', 100),
            "temperature": self._load_config.get('temperature', 0.7),
            "results_file": f"/app/logs/loadgen-results-{group_id}.json"
        }
        prompts_json_config = json.dumps(load_config, indent=2)
        
        log_dir = self._remote_base_path.rstrip("/") + "/logs"
        sif_path = self._remote_base_path.rstrip("/") + "/containers/client.sif"

        script = f"""#!/bin/bash -l

# Load Generator Job for Group {group_id}

echo "Starting load test at $(date)"
echo "Configuration:"
echo "  Prompt URL: {self._load_config.get('prompt_url')}"
echo "  Service ID: {self._load_config.get('service_id')}"
echo "  Clients: {self._load_config.get('num_clients')}"
echo "  RPS: {self._load_config.get('requests_per_second')}"
echo "  Duration: {self._load_config.get('duration_seconds')}s"
echo "  Container: {sif_path}"
echo ""

# Load required modules
echo "Loading modules..."
module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0

# Ensure HOME is set (SLURM sometimes clears it)
if [ -z "$HOME" ]; then
    export HOME=/home/users/$USER
fi

# Debug: Print environment info
echo "=== SLURM Job Debug Info ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Working directory: $(pwd)"
echo "HOME: $HOME"
echo "USER: $USER"
echo "Log directory: {log_dir}"
echo "Container sif: {sif_path}"
echo "==========================="

# Generate the JSON config file for this load test
echo "Generating load test configuration..."
cat > {log_dir}/loadgen-config-{group_id}.json << 'CONFIG_EOF'
{prompts_json_config}
CONFIG_EOF

echo "Configuration file created: {log_dir}/loadgen-config-{group_id}.json"

# Build container if needed
if [ ! -f {sif_path} ]; then
    echo 'Building Apptainer image: {sif_path}'
    
    # Create containers directory
    mkdir -p $(dirname {sif_path})
    
    # Set up user-writable directories for Apptainer
    export APPTAINER_TMPDIR=/tmp/apptainer-$USER-$$
    export APPTAINER_CACHEDIR=$HOME/.apptainer/cache
    
    mkdir -p $APPTAINER_TMPDIR $APPTAINER_CACHEDIR $HOME/.apptainer
    
    # Create empty docker config to avoid authentication issues
    echo '{{}}' > $HOME/.apptainer/docker-config.json
    
    # Change to the source directory where files are located
    cd {self._remote_base_path}/src/client
    
    # Build container from this directory
    apptainer build {sif_path} client_container.def
    build_result=$?
    
    # Clean up temp directories
    rm -rf $APPTAINER_TMPDIR
    
    if [ $build_result -ne 0 ]; then
        echo "ERROR: Failed to build container (exit code: $build_result)"
        exit 1
    fi
    
    echo "Container build successful!"
else
    echo "Container already exists: {sif_path}"
fi

# Ensure log directory exists
mkdir -p {log_dir}

# Do NOT copy the loadgen template to the logs directory. Copying the
# template into `logs/` caused it to be synced and appear among job logs.
# Instead bind the canonical template file from the deployed source tree
# directly into the container at `/app/main.py` (read-only).

# Run the load test inside the container
echo "Starting container..."
echo "Running load test container with config: loadgen-config-{group_id}.json"

# Mount the config file and Python script, then run
# Redirect container output to a log file
apptainer run \\
    --bind {log_dir}:/app/logs \\
    --bind {log_dir}/loadgen-config-{group_id}.json:/app/config.json:ro \\
     --bind {self._remote_base_path}/src/client/loadgen_template.py:/app/main.py:ro \\
    --env LOADGEN_CONFIG=/app/config.json \\
    {sif_path} > {log_dir}/loadgen-{group_id}-container.log 2>&1
container_exit_code=$?

echo ""
echo "Container exited with code: $container_exit_code"
echo "Container logs saved to: {log_dir}/loadgen-{group_id}-container.log"
echo "Load test completed at $(date)"

exit $container_exit_code
"""
        return script


    def _submit_slurm_job_via_ssh(self, script_content: str, job_config: dict, 
                                  slurm_rest_host: str = "slurmrestd.meluxina.lxp.lu",
                                  slurm_rest_port: int = 6820):
        """Submit a SLURM job via SSH using the REST API.
        
        Args:
            script_content: The bash script content to execute
            job_config: Job configuration dictionary
            slurm_rest_host: SLURM REST API hostname (unused, kept for compatibility)
            slurm_rest_port: SLURM REST API port (unused, kept for compatibility)
            
        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        try:
            # Get fresh SLURM token on each submission (tokens are cheap via SSH)
            logger.debug("Fetching fresh SLURM token...")
            token = self._ssh_manager.get_slurm_token()
            
            # Prepare the job submission payload
            payload = {
                'script': script_content,
                'job': job_config
            }
            
            # Build headers with fresh token
            headers = {
                'X-SLURM-USER-NAME': self._username,
                'X-SLURM-USER-TOKEN': token,
                'Content-Type': 'application/json'
            }
            
            # Submit via local tunnel (already set up in __init__)
            logger.info(f"Submitting job to {self._base_url}/job/submit")
            logger.info(f"Payload: {json.dumps(payload, indent=2)}")
            logger.info(f"Headers: X-SLURM-USER-NAME={headers['X-SLURM-USER-NAME']}, token length={len(headers['X-SLURM-USER-TOKEN'])}")
            response = requests.post(
                f"{self._base_url}/job/submit", 
                headers=headers, 
                json=payload,
                timeout=30
            )

            if not response.ok:
                logger.error(f"Failed to submit SLURM job: HTTP {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False, {"error": response.text, "status_code": response.status_code}
            
            # Parse JSON response
            response_data = response.json()
            logger.debug(f"SLURM job submission response: {json.dumps(response_data, indent=2)}")
            return True, response_data
                
        except Exception as e:
            logger.exception(f"Error submitting SLURM job via SSH tunnel: {e}")
            return False, {"error": str(e)} 