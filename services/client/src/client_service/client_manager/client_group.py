from client_service.deployment.client_dispatcher import AbstractClientDispatcher, SlurmClientDispatcher
import time as time_module
import logging
from typing import Optional


class ClientGroup:
    def __init__(self, benchmark_id: int, num_clients: int, server_addr: str, client_service_addr: str, time_limit: int = 5): 
        self._benchmark_id = benchmark_id
        self._num_clients = num_clients
        self._server_addr = server_addr
        self._client_service_addr = client_service_addr
        self._client_address: Optional[str] = None
        self._created_at = time_module.time()
        self._logger = logging.getLogger(f"client_service.client_group.{benchmark_id}")

        # Create and use dispatcher to start the slurm job
        dispatcher = SlurmClientDispatcher(server_addr, client_service_addr)
        try:
            dispatcher.dispatch(num_clients, benchmark_id, time_limit)
            self._logger.info(f"Dispatched Slurm job for benchmark {benchmark_id}")
        except Exception as e:
            self._logger.error(f"Failed to dispatch Slurm job for benchmark {benchmark_id}: {e}")
            raise

    def register_client_address(self, client_address: str) -> bool:
        """Register the address of the client process"""
        self._client_address = client_address.rstrip('/')
        self._logger.info(f"Registered client process {client_address} for benchmark {self._benchmark_id}")
        return True

    def get_client_address(self) -> Optional[str]:
        """Get the registered client process address"""
        return self._client_address

    def get_benchmark_id(self) -> int:
        return self._benchmark_id

    def get_num_clients(self) -> int:
        return self._num_clients

    def get_created_at(self) -> float:
        return self._created_at

    def has_client_registered(self) -> bool:
        """Check if a client process has registered"""
        return self._client_address is not None

    def get_info(self) -> dict:
        """Return group information as dict"""
        return {
            "num_clients": self._num_clients,
            "client_address": self._client_address,
            "created_at": self._created_at
        }