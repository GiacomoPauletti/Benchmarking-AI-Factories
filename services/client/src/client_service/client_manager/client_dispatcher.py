import requests
import json

from client_service.client_manager.slurm_config import SlurmConfig

import logging

logging.basicConfig(level=logging.DEBUG)

class AbstractClientDispatcher:
    def dispatch(self, num_clients: int, benchmark_id: int, time: int = 5):
        pass

class SlurmClientDispatcher(AbstractClientDispatcher):
    slurm_config : SlurmConfig = SlurmConfig.tmp_load_default()

    def __init__(self, server_addr : str, client_service_addr: str, slurm_config: SlurmConfig = SlurmConfig.tmp_load_default()):
        self._server_addr = server_addr
        self._client_service_addr = client_service_addr
        self._JOB = f"""echo 'Hello, world'"""

    def dispatch(self, num_clients: int, benchmark_id: int, time: int = 5):
        """
        Dispatch `num_clients` clients using Slurm to connect to `server_addr` and `client_service_addr` for `benchmark_id`.
        Params:
            - num_clients: Number of client processes to launch
            - benchmark_id: Benchmark ID to associate with the clients
            - time: Time limit for the Slurm job in minutes
        """
        logging.debug(f"Dispatching {num_clients} clients using SlurmClientDispatcher for benchmark {benchmark_id}.")
        SLURM_JOB = f'...{num_clients}...'

        logging.debug(f"Using SlurmConfig: {self.slurm_config}")

        # Check and refresh token if needed before making the request (default threshold: 2 minutes)
        self.slurm_config.refresh_token_if_needed(threshold_seconds=300)

        response = requests.post(
            f'{self.slurm_config.url}/slurm/{self.slurm_config.api_ver}/job/submit',
            headers={
                'X-SLURM-USER-NAME': f'{self.slurm_config.user_name}',
                'X-SLURM-USER-TOKEN': f'{self.slurm_config.token}'
            },
            json={
                'script': f"""#!/bin/bash -l\nmodule load env/release/2023.1\npython3 -m client.main {num_clients} {self._server_addr} {self._client_service_addr} {benchmark_id}\n""",
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

        logging.debug(f"Slurm job submission response: {response.status_code} - {response.text}")
        
        if response.status_code == 200:
            logging.debug("Job submitted successfully!")
            logging.debug(json.dumps(response.json(), indent=2))
        else:
            logging.debug(f"Job submission failed with status code {response.status_code}:")
            logging.debug(response.text)

        print(json.dumps(response.json(), indent=2)) 