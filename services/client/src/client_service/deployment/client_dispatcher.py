import requests
import json

from client_service.deployment.slurm_config import SlurmConfig

import logging

# Use the logger configured by main.py instead of basic config
logger = logging.getLogger(__name__)

class AbstractClientDispatcher:
    def dispatch(self, num_clients: int, benchmark_id: int, time: int = 5):
        pass

class SlurmClientDispatcher(AbstractClientDispatcher):
    slurm_config : SlurmConfig = SlurmConfig.tmp_load_default()

    def __init__(self, server_addr : str, client_service_addr: str, slurm_config: SlurmConfig = SlurmConfig.tmp_load_default(), use_container: bool = False):
        self._server_addr = server_addr
        self._client_service_addr = client_service_addr
        self._use_container = use_container
        print("\n\n==============================================")
        print(f"SlurmClientDispatcher initialized with use_container={use_container}")
        print("============================================== \n\n")
        self._JOB = f"""echo 'Hello, world'"""

    def dispatch(self, num_clients: int, benchmark_id: int, time: int = 5):
        """
        Dispatch `num_clients` clients using Slurm to connect to `server_addr` and `client_service_addr` for `benchmark_id`.
        Params:
            - num_clients: Number of client processes to launch
            - benchmark_id: Benchmark ID to associate with the clients
            - time: Time limit for the Slurm job in minutes
        """
        logger.debug(f"Dispatching {num_clients} clients using SlurmClientDispatcher for benchmark {benchmark_id}.")
        SLURM_JOB = f'...{num_clients}...'

        logger.debug(f"Using SlurmConfig: {self.slurm_config}")

        # Check and refresh token if needed before making the request (default threshold: 2 minutes)
        self.slurm_config.refresh_token_if_needed(threshold_seconds=300)

        # Build script command based on container mode
        container_flag = " --container" if self._use_container else ""
        script_command = f"./client_service/deployment/start_client.sh {num_clients} {self._server_addr} {self._client_service_addr} {benchmark_id}{container_flag}"
        
        response = requests.post(
            f'{self.slurm_config.url}/slurm/{self.slurm_config.api_ver}/job/submit',
            headers={
                'X-SLURM-USER-NAME': f'{self.slurm_config.user_name}',
                'X-SLURM-USER-TOKEN': f'{self.slurm_config.token}'
            },
            json={
                'script': f"""#!/bin/bash -l\n {script_command}\n""",
                'job': {
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
                    }

                }
        })

        logger.debug(f"Slurm job submission response: {response.status_code} - {response.text}")
        
        if response.status_code == 200:
            logger.info("Job submitted successfully!")
            logger.debug(json.dumps(response.json(), indent=2))
        else:
            logger.error(f"Job submission failed with status code {response.status_code}:")
            logger.error(response.text)

        print(json.dumps(response.json(), indent=2)) 