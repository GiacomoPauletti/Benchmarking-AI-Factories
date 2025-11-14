import requests
import json
import os
import logging
from pathlib import Path

from client_service.ssh_manager import SSHManager

# Use the logger configured by main.py instead of basic config
logger = logging.getLogger(__name__)

class AbstractClientDispatcher:
    def dispatch(self, num_clients: int, benchmark_id: int, time: int = 5):
        pass

class SlurmClientDispatcher(AbstractClientDispatcher):
    """
    SLURM client dispatcher for MeluXina HPC cluster.
    Simplified to match server's SlurmDeployer architecture.
    """

    def __init__(self, server_addr: str, account: str = "p200981", use_container: bool = False):
        """Initialize SLURM client dispatcher.
        
        Args:
            server_addr: Address of the server to connect clients to
            account: SLURM account for job submission (default: p200981)
            use_container: Whether to use containerized client execution
        """
        self._server_addr = server_addr
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
        
        # Setup SSH tunnel for SLURM REST API on port 6821 (server uses 6820)
        logger.info(f"Setting up SLURM REST API tunnel via SSH to {self._ssh_manager.ssh_target}")
        self._rest_api_port = self._ssh_manager.setup_slurm_rest_tunnel(local_port=6821)
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


    def sync_logs_from_remote(self, local_logs_dir: str = "./logs", pattern: str = "slurm-*.out"):
        """Sync SLURM logs from remote MeluXina to local directory.
        
        Args:
            local_logs_dir: Local directory to sync logs to
            pattern: Glob pattern for log files to sync (default: slurm-*.out)
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        logger.info(f"Syncing logs from {self._remote_logs_dir} to {local_logs_dir}...")
        
        # Ensure local logs directory exists
        os.makedirs(local_logs_dir, exist_ok=True)
        
        # Use rsync via SSH to sync logs
        # -a: archive mode (preserves permissions, timestamps, etc.)
        # -v: verbose
        # -z: compress during transfer
        # --include: only sync matching files
        # --exclude: exclude everything else
        rsync_cmd = [
            "rsync", "-avz",
            "--include", pattern,
            "--include", "*/",  # Include directories for recursive search
            "--exclude", "*",   # Exclude everything else
            f"{self._ssh_manager.ssh_user}@{self._ssh_manager.ssh_host}:{self._remote_logs_dir}/",
            f"{local_logs_dir}/"
        ]
        
        # Add SSH port option
        rsync_cmd.insert(2, "-e")
        rsync_cmd.insert(3, f"ssh -p {self._ssh_manager.ssh_port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null")
        
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
                logger.debug(f"Rsync output: {result.stdout}")
                return True, "Logs synced successfully"
            else:
                logger.error(f"Rsync failed: {result.stderr}")
                return False, f"Rsync failed: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            logger.error("Rsync timeout")
            return False, "Rsync timeout after 60 seconds"
        except Exception as e:
            logger.exception(f"Error syncing logs: {e}")
            return False, f"Error: {str(e)}"



    def dispatch(self, num_clients: int, benchmark_id: int, time: int = 5):
        """
        Dispatch `num_clients` clients using SLURM to connect to server for `benchmark_id`.
        Runs via SSH from local client_service to MeluXina.
        
        Args:
            num_clients: Number of client processes to launch
            benchmark_id: Benchmark ID to associate with the clients
            time: Time limit for the SLURM job in minutes
        """
        logger.debug(f"Dispatching {num_clients} clients via SLURM for benchmark {benchmark_id}.")
        
        # Build script command based on container mode
        container_flag = " --container" if self._use_container else ""
        
        # Simple test command - writes to remote base path logs directory
        script_command = f"echo 'Client group {benchmark_id} started with {num_clients} clients at '$(date)"
        
        # Prepare job configuration matching server pattern and MeluXina requirements
        # Per https://docs.lxp.lu/web_services/slurmrestd/: these fields are mandatory:
        # - qos, time_limit, account, environment, current_working_directory
        job_config = {
            'account': self._account,
            'qos': 'short', 
            'time_limit': {
                'number': time,
                'set': True
            },
            'name': f'ai-factory-clients-{benchmark_id}',
            'partition': 'cpu',
            'nodes': '1',
            'tasks': 1,
            'cpus_per_task': 4,
            'current_working_directory': self._remote_logs_dir,
            'standard_output': f'{self._remote_logs_dir}/client-{benchmark_id}-%j.out',
            'standard_error': f'{self._remote_logs_dir}/client-{benchmark_id}-%j.err',
            'environment': [f'USER={self._username}'],  # Mandatory per MeluXina docs
        }
        
        script_content = f"""#!/bin/bash -l\n{script_command}\n"""
        
        # Submit job via SSH
        success, response_data = self._submit_slurm_job_via_ssh(
            script_content=script_content,
            job_config=job_config
        )

        if success:
            logger.info("Job submitted successfully via SSH!")
            logger.debug(json.dumps(response_data, indent=2))
        else:
            logger.error(f"Job submission failed via SSH: {response_data}")

        print(json.dumps(response_data, indent=2))

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