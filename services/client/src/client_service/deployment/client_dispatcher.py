import requests
import json

from client_service.deployment.slurm_config import SlurmConfig
from client_service.ssh_manager import SSHManager

import logging

# Use the logger configured by main.py instead of basic config
logger = logging.getLogger(__name__)

class AbstractClientDispatcher:
    def dispatch(self, num_clients: int, benchmark_id: int, time: int = 5):
        pass

class SlurmClientDispatcher(AbstractClientDispatcher):
    slurm_config : SlurmConfig = SlurmConfig.tmp_load_default()

    def __init__(self, server_addr : str, slurm_config: SlurmConfig = SlurmConfig.tmp_load_default(), use_container: bool = False):
        self._server_addr = server_addr
        self._use_container = use_container
        self._ssh_manager = SSHManager.get_instance()  # Get SSH manager singleton instance

    def dispatch(self, num_clients: int, benchmark_id: int, time: int = 5):
        """
        Dispatch `num_clients` clients using Slurm to connect to `server_addr` and `client_service_addr` for `benchmark_id`.
        Now runs via SSH from local client_service to MeluXina.
        Params:
            - num_clients: Number of client processes to launch
            - benchmark_id: Benchmark ID to associate with the clients
            - time: Time limit for the Slurm job in minutes
        """
        logger.debug(f"Dispatching {num_clients} clients using SlurmClientDispatcher via SSH for benchmark {benchmark_id}.")

        logger.debug(f"Using SlurmConfig: {self.slurm_config}")
        
        # Sync client code to MeluXina before submitting job
        logger.info("Syncing client code to MeluXina...")
        from pathlib import Path
        
        # Get the local client source directory 
        current_dir = Path(__file__).parent.parent  # Go up from deployment/ to src/
        client_src_dir = current_dir / "client"
        
        # Remote destination - where the client code should be copied
        remote_base = f"/home/users/{self.slurm_config.user_name}/Benchmarking-AI-Factories/services/client/src"
        remote_client_dir = f"{remote_base}/client"
        
        # Sync the client directory to MeluXina
        sync_success = self._ssh_manager.sync_directory_to_remote(
            local_dir=client_src_dir,
            remote_dir=remote_client_dir,
            exclude_patterns=["__pycache__", "*.pyc", ".pytest_cache"]
        )
        
        if not sync_success:
            logger.warning("Failed to sync client code to MeluXina - proceeding anyway")
        else:
            logger.info("Client code synced successfully to MeluXina")
        
        # Also sync the deployment scripts
        deployment_src_dir = current_dir / "client_service" / "deployment"
        remote_deployment_dir = f"{remote_base}/client_service/deployment"
        
        deployment_sync_success = self._ssh_manager.sync_directory_to_remote(
            local_dir=deployment_src_dir,
            remote_dir=remote_deployment_dir,
            exclude_patterns=["__pycache__", "*.pyc"]
        )
        
        if deployment_sync_success:
            logger.info("Deployment scripts synced successfully to MeluXina")
            # Make sure the start script is executable
            make_executable_cmd = f"chmod +x {remote_deployment_dir}/start_client.sh"
            self._ssh_manager.execute_remote_command(make_executable_cmd, timeout=10)
        else:
            logger.warning("Failed to sync deployment scripts to MeluXina")

        # Build script command based on container mode
        container_flag = " --container" if self._use_container else ""
        script_command = f"./client_service/deployment/start_client.sh {num_clients} {self._server_addr} {benchmark_id}{container_flag}"
        
        # Prepare job configuration
        import os
        remote_base_path = os.environ.get('REMOTE_BASE_PATH', f'/home/users/{self.slurm_config.user_name}/Benchmarking-AI-Factories')
        
        job_config = {
            'qos': 'default',
            'time_limit': time,
            'account': f'{self.slurm_config.account}',
            "current_working_directory":
                f'/home/users/{self.slurm_config.user_name}/Benchmarking-AI-Factories/services/client/src', 
            "standard_output": 
                f'/home/users/{self.slurm_config.user_name}/Benchmarking-AI-Factories/services/client/src/client_dispatcher_%j.out', 
            "standard_error": 
                f'/home/users/{self.slurm_config.user_name}/Benchmarking-AI-Factories/services/client/src/client_dispatcher_%j.err', 
            'environment': {
                'USER': f'{self.slurm_config.user_name}',
                'REMOTE_BASE_PATH': remote_base_path,
            }
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
            slurm_rest_host: SLURM REST API hostname
            slurm_rest_port: SLURM REST API port
            
        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        try:
            # Get fresh SLURM token using slurm_config
            token = self.slurm_config.get_slurm_token(self._ssh_manager)
            
            # Prepare the job submission payload
            payload = {
                'script': script_content,
                'job': job_config
            }
            
            headers = {
                'X-SLURM-USER-NAME': self.slurm_config.user_name,
                'X-SLURM-USER-TOKEN': token,
                'Content-Type': 'application/json'
            }
            
            # Submit job via SSH
            success, status_code, response_body = self._ssh_manager.http_request_via_ssh(
                remote_host=slurm_rest_host,
                remote_port=slurm_rest_port,
                method="POST",
                path="/slurm/v0.0.40/job/submit",
                headers=headers,
                json_data=payload,
                timeout=30
            )
            
            if not success:
                logger.error(f"Failed to submit SLURM job via SSH: {response_body}")
                return False, {"error": response_body}
            
            # Parse JSON response
            try:
                response_data = json.loads(response_body)
                
                if status_code == 200:
                    logger.info("SLURM job submitted successfully via SSH")
                    return True, response_data
                else:
                    logger.error(f"SLURM job submission failed with status {status_code}: {response_body}")
                    return False, response_data
                    
            except json.JSONDecodeError:
                logger.error(f"Failed to parse SLURM response: {response_body}")
                return False, {"error": "Invalid JSON response", "raw_response": response_body}
                
        except Exception as e:
            logger.exception(f"Error submitting SLURM job via SSH: {e}")
            return False, {"error": str(e)} 