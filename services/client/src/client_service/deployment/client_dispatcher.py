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
    """
    SLURM client dispatcher for MeluXina HPC cluster.
    """

    slurm_config : SlurmConfig = SlurmConfig.tmp_load_default()

    def __init__(self, server_addr : str, slurm_config: SlurmConfig = SlurmConfig.tmp_load_default(), use_container: bool = False):
        self._server_addr = server_addr
        self._use_container = use_container
        self._ssh_manager = SSHManager.get_instance()  # Get SSH manager singleton instance

        self._rest_api_port = self._ssh_manager.setup_slurm_rest_tunnel()
        self._base_url = f"http://localhost:{self._rest_api_port}/slurm/v0.0.40"



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
        
        # Note: Environment setup is now handled by setup_meluxina_environment.sh script
        # which should be run manually before using this dispatcher

        # Build script command based on container mode
        container_flag = " --container" if self._use_container else ""
        
        # Use the standard remote base path set by setup_meluxina_environment.sh
        import os
        remote_base_path = os.environ.get('REMOTE_BASE_PATH', f'/project/home/p200981/ai-factory')
        
        # Script command pointing to the standard location
        #script_command = f"cd {remote_base_path}/src && ./client_service/deployment/start_client.sh {num_clients} {self._server_addr} {benchmark_id}{container_flag}"
        script_command = "echo 'Hello world' > ~/test_slurm_dispatch.txt"
        
        # Prepare job configuration using standard paths
        job_config = {
            'name': f'ai-factory-clients-{benchmark_id}',
            'partition': 'cpu',
            'account': f'{self.slurm_config.account}',
            'qos': 'short', 
            'time_limit': {
                'number': time,
                'set': True
            },
            'nodes': '1',
            'tasks': 1,
            'cpus_per_task': 4,
            "current_working_directory": f'{remote_base_path}/src',
            "standard_output": f'{remote_base_path}/logs/client_dispatcher_%j.out',
            "standard_error": f'{remote_base_path}/logs/client_dispatcher_%j.err',
            # 'environment': [
            #     f'USER={self.slurm_config.user_name}',
            #     f'REMOTE_BASE_PATH={remote_base_path}',
            # ]
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
            token = self.slurm_config.get_slurm_token()
            
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
            
            response = requests.post(
                f"{self._base_url}/job/submit", 
                headers=headers, 
                json=payload
            )

            if not response.ok:
                logger.error(f"Failed to submit SLURM job via SSH: {response.text}")
                return False, {"error": response.text}
            
            # Parse JSON response
            response_data = response.json()
            logger.debug(f"SLURM job submission response: {json.dumps(response_data, indent=2)}")
            return True, response_data
                
        except Exception as e:
            logger.exception(f"Error submitting SLURM job via SSH tunnel: {e}")
            return False, {"error": str(e)} 