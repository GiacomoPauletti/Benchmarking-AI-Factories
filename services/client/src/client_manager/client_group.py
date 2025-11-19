from deployment.client_dispatcher import AbstractClientDispatcher, LocalClientDispatcher
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
    """Represents a group of client processes managed together for load testing."""
    
    def __init__(
        self, 
        group_id: int, 
        load_config: dict
    ):
        self._group_id = group_id
        self._load_config = load_config  # Store full load test configuration
        self._num_clients = load_config["num_clients"]
        self._time_limit = load_config.get("time_limit", 5)  # Default 5 minutes
        self._client_address: Optional[str] = None
        self._created_at = time_module.time()
        self._logger = logging.getLogger(f"client_manager.client_group.{group_id}")
        self._status = ClientGroupStatus.PENDING
        self._job_id = None  # Process ID
        
        # Create and use dispatcher to start the local process
        self._dispatcher = LocalClientDispatcher(
            load_config=load_config
        )
        try:
            self._job_id = self._dispatcher.dispatch(group_id, self._time_limit)
            if self._job_id:
                self._logger.info(f"Started local load generator for client group {group_id} (PID: {self._job_id})")
                self._status = ClientGroupStatus.RUNNING
            else:
                self._logger.warning(f"Failed to start load generator for client group {group_id}")
        except Exception as e:
            self._logger.error(f"Failed to start load generator for client group {group_id}: {e}")
            raise

    def get_dispatcher(self) -> LocalClientDispatcher:
        """Get the local dispatcher for this group"""
        return self._dispatcher

    def get_client_address(self) -> Optional[str]:
        """Get the registered client process address"""
        return self._client_address

    def get_group_id(self) -> int:
        """Get the unique identifier for this client group"""
        return self._group_id

    def get_num_clients(self) -> int:
        return self._num_clients

    def get_created_at(self) -> float:
        return self._created_at

    def get_status(self) -> ClientGroupStatus:
        # For local load tests, check process status via dispatcher
        if self._job_id and self._status != ClientGroupStatus.STOPPED:
            try:
                process_status = self._dispatcher.get_process_status(self._group_id)
                if process_status == 'running':
                    self._status = ClientGroupStatus.RUNNING
                elif process_status == 'completed':
                    self._status = ClientGroupStatus.STOPPED
                    self._logger.info(f"Process {self._job_id} completed")
            except Exception as e:
                self._logger.error(f"Error checking process status for {self._job_id}: {e}")
        
        return self._status

    def get_job_id(self) -> Optional[str]:
        """Get the process ID (PID)"""
        return self._job_id

    def get_info(self) -> dict:
        """Return group information as dict"""
        # Call get_status() to update status before returning info
        current_status = self.get_status()
        
        return {
            "num_clients": self._num_clients,
            "client_address": self._client_address,
            "created_at": self._created_at,
            "load_config": self._load_config,
            "job_id": self._job_id,
            "status": current_status.name.lower()
        }