from client_service.deployment.client_dispatcher import AbstractClientDispatcher, SlurmClientDispatcher
from client_service.ssh_manager import SSHManager
import time as time_module
import logging
import random
from typing import Optional
from enum import Enum

class ClientGroupStatus(Enum):
    PENDING = 0
    RUNNING = 1
    STOPPED = 2
    



class ClientGroup:
    def __init__(self, benchmark_id: int, num_clients: int, server_addr: str, time_limit: int = 5, use_container: bool = False): 
        self._benchmark_id = benchmark_id
        self._num_clients = num_clients
        self._server_addr = server_addr
        self._client_address: Optional[str] = None
        self._created_at = time_module.time()
        self._use_container = use_container
        self._logger = logging.getLogger(f"client_service.client_group.{benchmark_id}")
        self._ssh_manager = SSHManager.get_instance()
        self._status = ClientGroupStatus.PENDING
        
        # Get signal file path for polling
        import os
        remote_base_path = os.environ.get('REMOTE_BASE_PATH', '/home/users/u103213/Benchmarking-AI-Factories')
        self._signal_file_path = f"{remote_base_path}/{benchmark_id}_addr.txt"
        
        # Create and use dispatcher to start the slurm job
        dispatcher = SlurmClientDispatcher(server_addr, use_container=use_container)
        try:
            dispatcher.dispatch(num_clients, benchmark_id, time_limit)
            self._logger.info(f"Dispatched Slurm job for benchmark {benchmark_id}")
        except Exception as e:
            self._logger.error(f"Failed to dispatch Slurm job for benchmark {benchmark_id}: {e}")
            raise

    def get_client_address(self) -> Optional[str]:
        """Get the registered client process address"""
        return self._client_address

    def get_benchmark_id(self) -> int:
        return self._benchmark_id

    def get_num_clients(self) -> int:
        return self._num_clients

    def get_created_at(self) -> float:
        return self._created_at

    def get_status(self) -> ClientGroupStatus:
        if ( self._status == ClientGroupStatus.PENDING ):
            # Check if signal file exists
            import os
            if os.path.exists(self._signal_file_path):
                try:
                    with open(self._signal_file_path, 'r') as f:
                        addr = f.read().strip()
                        if addr:
                            self._client_address = addr
                            self._status = ClientGroupStatus.RUNNING
                            self._logger.info(f"Client registered for benchmark {self._benchmark_id} at address {addr}")
                except Exception as e:
                    self._logger.error(f"Error reading signal file for benchmark {self._benchmark_id}: {e}")

        return self._status

    def get_info(self) -> dict:
        """Return group information as dict"""
        return {
            "num_clients": self._num_clients,
            "client_address": self._client_address,
            "created_at": self._created_at
        }