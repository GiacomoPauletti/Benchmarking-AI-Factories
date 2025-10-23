import logging
import threading
import time
from typing import Dict, Any, Optional, List
import requests
import socket

from client_service.client_manager.client_group import ClientGroup, ClientGroupStatus


logging.getLogger(__name__).addHandler(logging.NullHandler())

class ClientManagerResponseStatus:
    OK = 0
    ERROR = 1


class CMResponse:
    """Simple response object returned by some ClientManager helper methods."""
    def __init__(self, status: int, body=None):
        self.status = status
        self.body = body

class ClientManager:
    """
    Manages client groups (one group per benchmark_id). Uses self._client_groups
    (mapping benchmark_id -> dict) to store group metadata and a single registered
    client process address for that group. 
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            logging.getLogger(__name__).debug("Creating ClientManager instance")
            cls._instance = super(ClientManager, cls).__new__(cls)
        else:
            # Get file name and line number where __new__ is called
            import inspect
            frame = inspect.currentframe()
            if frame is None:
                return cls._instance
            else:
                caller_frame = frame.f_back
                if caller_frame is None:
                    return cls._instance

                filename = caller_frame.f_code.co_filename
                filename = filename.split('/')[-1]  # Just the file name, not full path
                lineno = caller_frame.f_lineno
                logging.getLogger(__name__).debug(f"Reusing existing ClientManager instance in file {filename} at line {lineno}")

        return cls._instance

    def __init__(self) -> None:
        # mapping: benchmark_id -> ClientGroup
        # Protect re-initialization in singleton pattern
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._client_groups: Dict[int, ClientGroup] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger("client_service.client_manager")
        # Default addresses - can be configured via environment or config file
        self._server_addr = "http://localhost:8002"
        self._client_service_addr = "http://localhost:8001"
        self._use_container = False  # Default to native execution
        self._initialized = True
    
    def configure(self, server_addr: Optional[str] = None, client_service_addr: Optional[str] = None, use_container: Optional[bool] = None):
        """Configure server and client service addresses and container mode after initialization"""
        if server_addr:
            self._server_addr = server_addr
        if client_service_addr:
            self._client_service_addr = client_service_addr
        if use_container is not None:
            self._use_container = use_container

    def add_client_group(self, benchmark_id: int, num_clients: int, time_limit: int = 5) -> int:
        """
        Create a new client group for `benchmark_id` expecting `num_clients`.
        Returns ClientManagerResponseStatus.OK, or ERROR if the group already exists.
        """
        with self._lock:
            if benchmark_id in self._client_groups:
                self._logger.debug(f"Group {benchmark_id} already exists")
                return ClientManagerResponseStatus.ERROR
            
            try:
                # Create ClientGroup - it handles the dispatching internally
                client_group = ClientGroup(benchmark_id, num_clients, self._server_addr, time_limit, self._use_container)
                self._client_groups[benchmark_id] = client_group
                self._logger.info(f"Added client group {benchmark_id}: expecting {num_clients} with time limit {time_limit}, container mode: {self._use_container}")
                return ClientManagerResponseStatus.OK
            except Exception as e:
                self._logger.error(f"Failed to create client group {benchmark_id}: {e}")
                return ClientManagerResponseStatus.ERROR

    def remove_client_group(self, benchmark_id: int) -> None:
        """Remove the group if present."""
        with self._lock:
            if benchmark_id in self._client_groups:
                del self._client_groups[benchmark_id]
                self._logger.info(f"Removed client group {benchmark_id}")

    def list_groups(self) -> List[int]:
        """Return the list of registered group ids."""
        with self._lock:
            return list(self._client_groups.keys())

    def get_group_info(self, benchmark_id: int) -> Optional[Dict[str, Any]]:
        """Return a copy of group information or None if it does not exist."""
        with self._lock:
            group = self._client_groups.get(benchmark_id)
            if group is None:
                return None
            return group.get_info()

    def run_client_group(self, benchmark_id: int, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """
        Forward a POST /run request to the registered client process of the group.
        The single process may spawn multiple internal clients; we request up to num_clients
        to be started by that process. Returns a list with a single entry (or error).
        """
        with self._lock:
            group = self._client_groups.get(benchmark_id)
            if group is None:
                return [{"error": "unknown benchmark_id", "benchmark_id": benchmark_id}]
            client_addr = group.get_client_address()

        results: List[Dict[str, Any]] = []
        if group.get_status() != ClientGroupStatus.RUNNING:
            self._logger.warning(f"Client group {benchmark_id} is not in RUNNING state")
            results.append({"error": "client group not running", "benchmark_id": benchmark_id})
            return results

        client_addr = group.get_client_address()
        url = f"{client_addr}/run"
        try:
            r = requests.post(url, timeout=timeout)
            results.append({"client_process": client_addr, "status_code": r.status_code, "body": r.text})
            self._logger.debug(f"Forwarded run to {client_addr} -> {r.status_code}")
        except Exception as e:
            self._logger.exception(f"Error forwarding run to {client_addr}")
            results.append({"client_process": client_addr, "error": str(e)})

        return results

