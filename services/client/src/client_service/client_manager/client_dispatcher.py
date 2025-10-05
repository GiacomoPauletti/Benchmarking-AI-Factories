import requests
import json

from slurm_config import SlurmConfig

class AbstractClientDispatcher:
    def dispatch(self, num_clients: int):
        pass

class SlurmClientDispatcher(AbstractClientDispatcher):
    def __init__(self, slurm_config: SlurmConfig = SlurmConfig.tmp_load_default()):
        self._JOB = f"""echo 'Hello, world'"""
        self._config = slurm_config

    def dispatch(self, num_clients: int):
        SLURM_JOB = f'...{num_clients}...'

        response = requests.post(
            f'{self._config.url}/slurm/{self._config.api_ver}/job/submit',
            headers={
                'X-SLURM-USER-NAME': f'{self._config.user_name}',
                'X-SLURM-USER-TOKEN': f'{self._config.jwt}'
            },
            json={
                'script': self._JOB,
                'job': {
                    'qos': 'default',
                    'time_limit': 5,
                    'account': f'{self._config.account}',
                    "current_working_directory":f'{self._config.user_name}',
                    'environment': {
                        'USER': f'{self._config.user_name}'
                    }
                }
        })

        response.raise_for_status()
        print(json.dumps(response.json(), indent=2)) 