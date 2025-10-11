import requests
import json

from client_service.client_manager.slurm_config import SlurmConfig

import logging

logging.basicConfig(level=logging.DEBUG)

class AbstractClientDispatcher:
    def dispatch(self, num_clients: int):
        pass

class SlurmClientDispatcher(AbstractClientDispatcher):
    slurm_config : SlurmConfig = SlurmConfig.tmp_load_default()

    def __init__(self, slurm_config: SlurmConfig = SlurmConfig.tmp_load_default()):
        self._JOB = f"""echo 'Hello, world'"""

    def dispatch(self, num_clients: int):
        logging.debug(f"Dispatching {num_clients} clients using SlurmClientDispatcher.")
        SLURM_JOB = f'...{num_clients}...'

        logging.debug(f"Using SlurmConfig: {self.slurm_config}")

        response = requests.post(
            f'{self.slurm_config.url}/slurm/{self.slurm_config.api_ver}/job/submit',
            headers={
                'X-SLURM-USER-NAME': f'{self.slurm_config.user_name}',
                'X-SLURM-USER-TOKEN': f'{self.slurm_config.jwt}'
            },
            json={
                'script': "#!/bin/bash\necho Hello World",
                'job': {
                    'qos': 'default',
                    'time_limit': 5,
                    'account': f'{self.slurm_config.account}',
                    "current_working_directory":f'{self.slurm_config.user_name}',
                    'environment': {
                        'USER': f'{self.slurm_config.user_name}',
                    }
                }
        })
        logging.debug(f"Slurm job submission response: {response.status_code} - {response.text}")

        response.raise_for_status()
        print(json.dumps(response.json(), indent=2)) 