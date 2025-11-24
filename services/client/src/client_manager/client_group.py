from deployment.client_dispatcher import AbstractClientDispatcher, SlurmClientDispatcher
from ssh_manager import SSHManager
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
        load_config: dict,
        account: str = "p200981", 
        use_container: bool = False
    ):
        self._group_id = group_id
        self._load_config = load_config  # Store full load test configuration
        self._num_clients = load_config["num_clients"]
        self._time_limit = load_config.get("time_limit", 5)  # Default 5 minutes for faster queue
        self._client_address: Optional[str] = None
        self._created_at = time_module.time()
        self._use_container = use_container
        self._logger = logging.getLogger(f"client_manager.client_group.{group_id}")
        self._ssh_manager = SSHManager()
        self._status = ClientGroupStatus.PENDING
        self._job_id = None  # SLURM job ID
        
        # Get signal file path for polling
        import os
        remote_base_path = os.environ.get('REMOTE_BASE_PATH', f'/project/home/{account}/ai-factory')
        self._signal_file_path = f"{remote_base_path}/{group_id}_addr.txt"
        
        # Create and use dispatcher to start the SLURM job
        self._dispatcher = SlurmClientDispatcher(
            load_config=load_config,
            account=account, 
            use_container=use_container
        )
        try:
            self._job_id = self._dispatcher.dispatch(group_id, self._time_limit)
            if self._job_id:
                self._logger.info(f"Dispatched SLURM job {self._job_id} for client group {group_id}")
            else:
                self._logger.warning(f"Dispatched SLURM job for client group {group_id} but no job ID returned")
        except Exception as e:
            self._logger.error(f"Failed to dispatch SLURM job for client group {group_id}: {e}")
            raise

    def get_dispatcher(self) -> SlurmClientDispatcher:
        """Get the SLURM dispatcher for this group"""
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
        # For containerized load tests, check SLURM job status
        if self._job_id and self._status != ClientGroupStatus.STOPPED:
            try:
                # Query SLURM job state via SSH
                # First try squeue (for running jobs), fallback to sacct (for completed jobs)
                # Need to check if squeue has output, as it exits 0 even when no jobs found
                cmd = f"squeue -j {self._job_id} -h -o %T 2>/dev/null | grep -q . && squeue -j {self._job_id} -h -o %T || sacct -j {self._job_id} -n -o State | head -1"
                success, stdout, stderr = self._ssh_manager.execute_remote_command(cmd, timeout=5)
                
                if success and stdout:
                    state = stdout.strip().upper()
                    # SLURM states: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED, etc.
                    if state in ['RUNNING', 'COMPLETING']:
                        self._status = ClientGroupStatus.RUNNING
                        self._logger.debug(f"Job {self._job_id} is running")
                    elif state in ['COMPLETED']:
                        self._status = ClientGroupStatus.STOPPED
                        self._logger.info(f"Job {self._job_id} completed")
                    elif state in ['FAILED', 'CANCELLED', 'TIMEOUT', 'NODE_FAIL', 'PREEMPTED']:
                        self._status = ClientGroupStatus.STOPPED
                        self._logger.warning(f"Job {self._job_id} stopped with state: {state}")
                    # else: keep PENDING for queued jobs
            except Exception as e:
                self._logger.error(f"Error checking job status for {self._job_id}: {e}")
        
        # Legacy: Check signal file for old architecture (backward compatibility)
        if self._status == ClientGroupStatus.PENDING:
            import os
            if os.path.exists(self._signal_file_path):
                try:
                    with open(self._signal_file_path, 'r') as f:
                        addr = f.read().strip()
                        if addr:
                            self._client_address = addr
                            self._status = ClientGroupStatus.RUNNING
                            self._logger.info(f"Client registered for group {self._group_id} at address {addr}")
                except Exception as e:
                    self._logger.error(f"Error reading signal file for group {self._group_id}: {e}")

        return self._status

    def get_job_id(self) -> Optional[str]:
        """Get the SLURM job ID"""
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