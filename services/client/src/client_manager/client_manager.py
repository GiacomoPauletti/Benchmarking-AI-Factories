import logging
import threading
import time
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

    def __init__(self) -> None:
        # mapping: group_id -> ClientGroup
        # Protect re-initialization in singleton pattern
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._client_groups: Dict[int, ClientGroup] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger("client_manager")
        # Default addresses - can be configured via environment or config file
        self._server_addr = "http://localhost:8002"
        self._client_service_addr = "http://localhost:8001"
        self._use_container = False  # Default to native execution
        self._account = "p200981"  # Default SLURM account
        self._initialized = True
    
    def configure(self, server_addr: Optional[str] = None, client_service_addr: Optional[str] = None, use_container: Optional[bool] = None, account: Optional[str] = None):
        """Configure server and client service addresses, container mode, and SLURM account after initialization"""
        if server_addr:
            self._server_addr = server_addr
        if client_service_addr:
            self._client_service_addr = client_service_addr
        if use_container is not None:
            self._use_container = use_container
        if account:
            self._account = account

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
                    f"targeting {load_config['target_url']}"
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

    def sync_logs(self, group_id: Optional[int] = None, local_logs_dir: str = "./logs") -> Dict[str, Any]:
        """Sync SLURM logs from remote MeluXina to local directory.
        
        Args:
            group_id: If specified, sync logs for specific group. If None, sync all logs.
            local_logs_dir: Local directory to sync logs to
            
        Returns:
            Dictionary with sync results
        """
        with self._lock:
            if group_id is not None:
                # Sync logs for specific group
                group = self._client_groups.get(group_id)
                if group is None:
                    return {"error": f"Group {group_id} not found", "success": False}
                
                dispatcher = group.get_dispatcher()
                pattern = f"loadgen-{group_id}-*.out"
                success, message = dispatcher.sync_logs_from_remote(local_logs_dir, pattern)
                
                return {
                    "group_id": group_id,
                    "success": success,
                    "message": message,
                    "local_path": local_logs_dir
                }
            else:
                # Sync all logs - create dispatcher if no groups exist
                if self._client_groups:
                    # Get dispatcher from existing group
                    any_group = next(iter(self._client_groups.values()))
                    dispatcher = any_group.get_dispatcher()
                else:
                    # No groups exist - create a standalone dispatcher just for syncing
                    from deployment.client_dispatcher import SlurmClientDispatcher
                    dispatcher = SlurmClientDispatcher(
                        load_config={},  # Empty config, only used for syncing
                        account=self._account,
                        use_container=self._use_container
                    )
                
                pattern = "loadgen-*.out"
                success, message = dispatcher.sync_logs_from_remote(local_logs_dir, pattern)
                
                return {
                    "group_id": "all",
                    "success": success,
                    "message": message,
                    "local_path": local_logs_dir,
                    "groups": list(self._client_groups.keys())
                }

