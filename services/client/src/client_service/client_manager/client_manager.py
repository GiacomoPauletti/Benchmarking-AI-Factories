import logging
import threading
import time
from typing import Dict, Any, Optional, List
import requests

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
        logging.getLogger(__name__).debug("Creating ClientManager instance")
        if not cls._instance:
            cls._instance = super(ClientManager, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # mapping: benchmark_id -> {
        #   "num_clients": int,
        #   "client_address": Optional[str],
        #   "created_at": float
        # }
        # Protect re-initialization in singleton pattern
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._client_groups: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger("client_service.client_manager")
        self._initialized = True

    def add_client_group(self, benchmark_id: int, num_clients: int) -> int:
        """
        Create a new client group for `benchmark_id` expecting `num_clients`.
        Returns ClientManagerResponseStatus.OK, or ERROR if the group already exists.
        """
        with self._lock:
            if benchmark_id in self._client_groups:
                self._logger.debug(f"Group {benchmark_id} already exists")
                return ClientManagerResponseStatus.ERROR
            self._client_groups[benchmark_id] = {
                "num_clients": int(num_clients),
                "client_address": None,
                "created_at": time.time()
            }
            self._logger.info(f"Added client group {benchmark_id}: expecting {num_clients}")
            return ClientManagerResponseStatus.OK

    def remove_client_group(self, benchmark_id: int) -> None:
        """Remove the group if present."""
        with self._lock:
            if benchmark_id in self._client_groups:
                del self._client_groups[benchmark_id]
                self._logger.info(f"Removed client group {benchmark_id}")

    def register_client(self, benchmark_id: int, client_address: str) -> bool:
        """
        Called by a client *process* to register its HTTP address (e.g. "http://10.0.0.2:9000").
        The registering process declares how many internal clients it will spawn via provided_clients.
        If provided_clients is None, it is treated as claiming to provide all expected clients.
        Returns True if registered, False if the group does not exist.
        """
        with self._lock:
            group = self._client_groups.get(benchmark_id)
            if group is None:
                self._logger.warning(f"Tried to register client for unknown benchmark {benchmark_id}")
                return False


            group["client_address"] = client_address.rstrip('/')
            self._logger.info(
                f"Registered client process {client_address} for benchmark {benchmark_id} "
            )
            return True

    def list_groups(self) -> List[int]:
        """Return the list of registered group ids."""
        with self._lock:
            return list(self._client_groups.keys())

    def get_group_info(self, benchmark_id: int) -> Optional[Dict[str, Any]]:
        """Return a copy of group information or None if it does not exist."""
        with self._lock:
            g = self._client_groups.get(benchmark_id)
            if g is None:
                return None
            # return a stable copy of the stored fields
            return {
                "num_clients": g["num_clients"],
                "client_address": g.get("client_address"),
                "created_at": g.get("created_at")
            }

    def wait_for_clients(self, benchmark_id: int, timeout: float = 30.0, poll_interval: float = 0.5) -> bool:
        """
        Wait until the client registers or timeout expires. 
        Returns True if client registers, False otherwise.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                group = self._client_groups.get(benchmark_id)
                if group is None:
                    return False
                client_addr = group["client_address"]
                if client_addr is None:
                    # no process registered yet
                    pass
                else:
                    return True
            time.sleep(poll_interval)
        return False

    def run_client_group(self, benchmark_id: int, num_clients: int, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """
        Forward a POST /run request to the registered client process of the group.
        The single process may spawn multiple internal clients; we request up to num_clients
        to be started by that process. Returns a list with a single entry (or error).
        """
        with self._lock:
            group = self._client_groups.get(benchmark_id)
            if group is None:
                raise ValueError(f"Unknown benchmark id {benchmark_id}")
            client_addr = group["client_address"]

        results: List[Dict[str, Any]] = []
        if client_addr is None:
            self._logger.warning(f"No client process registered for benchmark {benchmark_id}")
            return [{"error": "no client process registered", "benchmark_id": benchmark_id}]

        url = f"{client_addr}/run"
        try:
            r = requests.post(url, timeout=timeout)
            results.append({"client_process": client_addr, "requested": num_clients, "status_code": r.status_code, "body": r.text})
            self._logger.debug(f"Forwarded run to {client_addr}: requested={num_clients} -> {r.status_code}")
        except Exception as e:
            self._logger.exception(f"Error forwarding run to {client_addr}")
            results.append({"client_process": client_addr, "requested": num_clients, "error": str(e)})

        return results

