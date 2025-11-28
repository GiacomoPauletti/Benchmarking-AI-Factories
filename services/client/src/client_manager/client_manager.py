import logging
import threading
import time
import os
from typing import Dict, Any, Optional, List
import requests
import socket

from client_manager.client_group import ClientGroup, ClientGroupStatus


logging.getLogger(__name__).addHandler(logging.NullHandler())

class ClientManagerResponseStatus:
    OK = 0
    ERROR = 1
    ALREADY_EXISTS = 2


class CMResponse:
    """Simple response object returned by some ClientManager helper methods."""
    def __init__(self, status: int, body=None):
        self.status = status
        self.body = body

class ClientManager:
    """
    Manages client groups. Each group has a unique group_id and can contain
    multiple client processes managed via SLURM.
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

    def __init__(self, server_addr: Optional[str] = None, client_service_addr: Optional[str] = None, use_container: Optional[bool] = None, account: Optional[str] = None) -> None:
        # mapping: group_id -> ClientGroup
        # Protect re-initialization in singleton pattern
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._client_groups: Dict[int, ClientGroup] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger("client_manager")

        self._server_addr = server_addr or os.environ.get("SERVER_URL", "http://server:8001")
        self._client_service_addr = client_service_addr 
        self._use_container = use_container 
        self._account = account 

        # The orchestrator URL must be obtained from the Server API at runtime.
        self._orchestrator_url = None
        self._logger.info("Orchestrator will be discovered via Server API when needed")

        self._initialized = True

    def set_orchestrator_url(self, timeout: float = 2.0) -> bool:
        """Query the Server API to obtain the orchestrator endpoint and set
        ``self._orchestrator_url``.

        Args:
            timeout: HTTP request timeout in seconds.

        Returns:
            True if an orchestrator endpoint was discovered and set, False otherwise.
        """
        try:
            url = f"{self._server_addr}/api/v1/orchestrator/endpoint"
            resp = requests.get(url, timeout=timeout)
            if resp.status_code != 200:
                self._logger.warning(f"Failed to query orchestrator endpoint from server {self._server_addr}: status={resp.status_code}")
                return False

            data = resp.json()
            endpoint = data.get('endpoint')
            if not endpoint:
                self._logger.warning(f"Server {self._server_addr} returned no 'endpoint' field for orchestrator")
                return False

            self._orchestrator_url = endpoint
            self._logger.info(f"Orchestrator URL set to: {endpoint}")
            return True
        except Exception as e:
            self._logger.exception(f"Error while setting orchestrator URL from {self._server_addr}: {e}")
            return False

    def add_client_group(self, group_id: int, load_config: dict) -> int:
        """
        Create a new client group with `group_id` for load testing.
        
        Args:
            group_id: Unique identifier for the group
            load_config: Dictionary with load test configuration (target_url, num_clients, rps, etc.)
            
        Returns ClientManagerResponseStatus.OK, ALREADY_EXISTS, or ERROR.
        """
        with self._lock:
            if group_id in self._client_groups:
                self._logger.debug(f"Group {group_id} already exists")
                return ClientManagerResponseStatus.ALREADY_EXISTS
            
            try:
                if not self._orchestrator_url:
                    self.set_orchestrator_url()
                service_id = load_config.get('service_id')
                if service_id:
                    if self._orchestrator_url:
                        prompt_url = f"{self._orchestrator_url.rstrip('/')}/api/services/vllm/{service_id}/prompt"
                        load_config['prompt_url'] = prompt_url
                        self._logger.info(f"Using orchestrator prompt endpoint for service {service_id}: {prompt_url}")
                    else:
                        self._logger.warning(f"Service {service_id} requested but _orchestrator_url is not set; leaving load_config unchanged")

                # Create ClientGroup - it handles the dispatching internally
                client_group = ClientGroup(
                    group_id=group_id,
                    load_config=load_config,
                    account=self._account,
                    use_container=self._use_container
                )
                self._client_groups[group_id] = client_group
                self._logger.info(
                    f"Added client group {group_id}: {load_config['num_clients']} clients, "
                    f"{load_config['requests_per_second']} RPS, "
                    f"targeting {load_config.get('prompt_url') }"
                )
                return ClientManagerResponseStatus.OK
            except Exception as e:
                self._logger.error(f"Failed to create client group {group_id}: {e}")
                return ClientManagerResponseStatus.ERROR

    def remove_client_group(self, group_id: int) -> None:
        """Remove the group if present."""
        with self._lock:
            if group_id in self._client_groups:
                del self._client_groups[group_id]
                self._logger.info(f"Removed client group {group_id}")

    def list_groups(self) -> List[int]:
        """Return the list of registered group ids."""
        with self._lock:
            return list(self._client_groups.keys())

    def get_group_info(self, group_id: int) -> Optional[Dict[str, Any]]:
        """Return a copy of group information or None if it does not exist."""
        with self._lock:
            group = self._client_groups.get(group_id)
            if group is None:
                return None
            return group.get_info()

    def run_client_group(self, group_id: int, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """
        Forward a POST /run request to the registered client process of the group.
        The single process may spawn multiple internal clients; we request up to num_clients
        to be started by that process. Returns a list with a single entry (or error).
        """
        with self._lock:
            group = self._client_groups.get(group_id)
            if group is None:
                return [{"error": "unknown group_id", "group_id": group_id}]
            client_addr = group.get_client_address()

        results: List[Dict[str, Any]] = []
        if group.get_status() != ClientGroupStatus.RUNNING:
            self._logger.warning(f"Client group {group_id} is not in RUNNING state")
            results.append({"error": "client group not running", "group_id": group_id})
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

