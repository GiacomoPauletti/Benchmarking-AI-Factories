"""
Client Group singleton class for managing client processes
"""

import logging
import threading
import time
from typing import List, Optional


class ClientGroup:
    """
    Singleton class that manages the group of clients in a client process.
    This is different from the ClientGroup in client_service/client_manager
    which manages client processes from the service side.
    """
    
    _instance: Optional['ClientGroup'] = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ClientGroup, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Protect against multiple initialization
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self._benchmark_id: Optional[int] = None
        self._clients: List = []
        self._server_addr: Optional[str] = None
        self._client_service_addr: Optional[str] = None
        self._local_address: Optional[str] = None
        self._created_at = time.time()
        self._logger = logging.getLogger("client.client_group")
        self._initialized = True
        
        self._logger.info("ClientGroup singleton initialized")
    
    def configure(self, benchmark_id: int, clients: List, server_addr: str, 
                 client_service_addr: str, local_address: str):
        """Configure the client group with initial parameters"""
        self._benchmark_id = benchmark_id
        self._clients = clients
        self._server_addr = server_addr
        self._client_service_addr = client_service_addr
        self._local_address = local_address
        
        self._logger.info(f"ClientGroup configured: benchmark_id={benchmark_id}, "
                         f"num_clients={len(clients)}, local_address={local_address}")
    
    @property
    def benchmark_id(self) -> Optional[int]:
        """Get the benchmark ID"""
        return self._benchmark_id
    
    @property
    def clients(self) -> List:
        """Get the list of clients"""
        return self._clients
    
    @property
    def num_clients(self) -> int:
        """Get the number of clients"""
        return len(self._clients)
    
    @property
    def server_addr(self) -> Optional[str]:
        """Get the server address"""
        return self._server_addr
    
    @property
    def client_service_addr(self) -> Optional[str]:
        """Get the client service address"""
        return self._client_service_addr
    
    @property
    def local_address(self) -> Optional[str]:
        """Get the local address of this client process"""
        return self._local_address
    
    @property
    def created_at(self) -> float:
        """Get the creation timestamp"""
        return self._created_at
    
    def add_client(self, client):
        """Add a client to the group"""
        self._clients.append(client)
        self._logger.debug(f"Added client to group, total clients: {len(self._clients)}")
    
    def run_all_clients(self) -> int:
        """Start all clients in separate threads"""
        if not self._clients:
            self._logger.warning("No clients to run")
            return 0
        
        self._logger.info(f"Starting {len(self._clients)} clients for benchmark {self._benchmark_id}")
        
        started_count = 0
        for client in self._clients:
            try:
                thread = threading.Thread(target=client.run)
                thread.start()
                client.thread = thread
                started_count += 1
            except Exception as e:
                self._logger.error(f"Failed to start client: {e}")
        
        self._logger.info(f"Successfully started {started_count}/{len(self._clients)} clients")
        return started_count
    
    def register_observer(self, observer) -> bool:
        """Register an observer to all clients"""
        if not self._clients:
            self._logger.warning("No clients available for observer registration")
            return False
        
        try:
            registered_count = 0
            for client in self._clients:
                client.subscribe(observer)
                registered_count += 1
            
            self._logger.info(f"Registered observer to {registered_count} clients")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to register observer: {e}")
            return False
    
    def get_status(self) -> dict:
        """Get the current status of the client group"""
        return {
            "benchmark_id": self._benchmark_id,
            "num_clients": len(self._clients),
            "server_addr": self._server_addr,
            "client_service_addr": self._client_service_addr,
            "local_address": self._local_address,
            "created_at": self._created_at
        }