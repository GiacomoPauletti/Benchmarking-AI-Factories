"""
SSH connection management for MeluXina HPC cluster - Logs Service.
Handles log fetching and synchronization from remote MeluXina.
"""

import os
import subprocess
import logging
import time
from pathlib import Path
from typing import Optional, Tuple, List


class SSHManager:
    """Manages SSH connections for log synchronization from MeluXina HPC cluster.
    
    Provides functionality for:
    - Remote log file synchronization via rsync
    - Remote directory listing
    - Remote command execution for log management
    """
    
    def __init__(self, ssh_host: str = None, ssh_user: str = None, ssh_port: int = None):
        """Initialize SSH manager with connection details.
        
        Args:
            ssh_host: SSH hostname (e.g., 'login.lxp.lu')
            ssh_user: Username for SSH connection
            ssh_port: SSH port (default: 22, MeluXina uses 8822)
        """
        self.logger = logging.getLogger(__name__)
        
        # Get SSH configuration from environment
        self.ssh_host = ssh_host or os.getenv('SSH_HOST')
        self.ssh_user = ssh_user or os.getenv('SSH_USER')
        self.ssh_port = ssh_port or int(os.getenv('SSH_PORT', '22'))
        
        if not self.ssh_user:
            raise ValueError("SSH_USER must be set. Check your .env.local file.")
        if not self.ssh_host:
            raise ValueError("SSH_HOST must be set. Check your .env.local file.")
        
        # Build SSH target and base command
        self.ssh_target = f"{self.ssh_user}@{self.ssh_host}"
        
        # Build base SSH command with port
        self.ssh_base_cmd = ["ssh"]
        if self.ssh_port != 22:
            self.ssh_base_cmd.extend(["-p", str(self.ssh_port)])
        
        # Disable host key checking for container environments
        self.ssh_base_cmd.extend(["-o", "StrictHostKeyChecking=no"])
        self.ssh_base_cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])
        
        # ControlMaster setup for persistent SSH connections
        self.control_socket_dir = Path("/tmp/ssh-control-sockets")
        self.control_socket_dir.mkdir(parents=True, exist_ok=True)
        self._control_master_socket = self.control_socket_dir / f"logs-master-{self.ssh_user}@{self.ssh_host}:{self.ssh_port}"
        self._control_master_active = False
        self._last_control_check = 0
        self._control_check_interval = 30  # Check every 30s
        
        self.logger.info(f"SSH Manager initialized for {self.ssh_target}:{self.ssh_port}")
        self.logger.info(f"ControlMaster socket: {self._control_master_socket}")
    
    def _ensure_control_master(self) -> bool:
        """Ensure a ControlMaster connection is active."""
        now = time.time()
        
        # Check if we recently verified the connection
        if self._control_master_active and (now - self._last_control_check) < self._control_check_interval:
            return True
        
        # Check if control master socket exists and is responsive
        if self._control_master_socket.exists():
            try:
                test_cmd = self.ssh_base_cmd + [
                    "-S", str(self._control_master_socket),
                    "-O", "check",
                    self.ssh_target
                ]
                result = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    timeout=2,
                    env=os.environ.copy()
                )
                
                if result.returncode == 0:
                    self.logger.debug("ControlMaster connection is alive")
                    self._control_master_active = True
                    self._last_control_check = now
                    return True
                else:
                    self.logger.debug("ControlMaster check failed, will recreate")
                    try:
                        if self._control_master_socket.exists():
                            self._control_master_socket.unlink()
                    except Exception as e:
                        self.logger.warning(f"Failed to remove stale socket: {e}")
            except Exception as e:
                self.logger.debug(f"ControlMaster check error: {e}")
                try:
                    if self._control_master_socket.exists():
                        self._control_master_socket.unlink()
                except Exception as ex:
                    self.logger.warning(f"Failed to remove stale socket: {ex}")
        
        # Create new control master
        try:
            self.logger.info("Creating ControlMaster connection...")
            
            master_cmd = self.ssh_base_cmd + [
                "-M",
                "-S", str(self._control_master_socket),
                "-o", "ControlPersist=600",
                "-o", "ServerAliveInterval=60",
                "-o", "ServerAliveCountMax=3",
                "-o", "ExitOnForwardFailure=yes",
                "-fN",
                self.ssh_target
            ]
            
            result = subprocess.run(
                master_cmd,
                capture_output=True,
                text=True,
                timeout=15,
                env=os.environ.copy()
            )
            
            if result.returncode != 0:
                self.logger.warning(f"Failed to create ControlMaster: {result.stderr}")
                self._control_master_active = False
                return False
            
            time.sleep(0.5)
            
            if self._control_master_socket.exists():
                self.logger.info("ControlMaster connection established successfully")
                self._control_master_active = True
                self._last_control_check = now
                return True
            else:
                self.logger.warning("ControlMaster socket not created")
                self._control_master_active = False
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.warning("Timeout creating ControlMaster connection")
            self._control_master_active = False
            return False
        except Exception as e:
            self.logger.warning(f"Error creating ControlMaster: {e}")
            self._control_master_active = False
            return False
    
    def _get_ssh_command(self, command: str = None, use_control_master: bool = True) -> list:
        """Build SSH command with optional ControlMaster support."""
        cmd = self.ssh_base_cmd.copy()
        
        if use_control_master and self._ensure_control_master():
            cmd.extend(["-S", str(self._control_master_socket)])
        
        cmd.append(self.ssh_target)
        
        if command:
            cmd.append(command)
        
        return cmd
    
    def close_control_master(self):
        """Close the ControlMaster connection gracefully."""
        if not self._control_master_active or not self._control_master_socket.exists():
            return
        
        try:
            self.logger.info("Closing ControlMaster connection...")
            exit_cmd = self.ssh_base_cmd + [
                "-S", str(self._control_master_socket),
                "-O", "exit",
                self.ssh_target
            ]
            subprocess.run(
                exit_cmd,
                capture_output=True,
                timeout=5,
                env=os.environ.copy()
            )
            self._control_master_active = False
            self.logger.info("ControlMaster connection closed")
        except Exception as e:
            self.logger.warning(f"Error closing ControlMaster: {e}")
    
    def execute_remote_command(self, command: str, timeout: int = 30) -> Tuple[bool, str, str]:
        """Execute a command on MeluXina via SSH.
        
        Args:
            command: Command to execute
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (success, stdout, stderr)
        """
        try:
            cmd = self._get_ssh_command(command, use_control_master=True)
            
            env = os.environ.copy()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            
            # Check for ControlMaster connection refused error and retry once
            if result.returncode != 0 and "Control socket connect" in result.stderr and "Connection refused" in result.stderr:
                self.logger.warning("ControlMaster connection refused. Retrying with fresh connection...")
                try:
                    if self._control_master_socket.exists():
                        self._control_master_socket.unlink()
                except:
                    pass
                self._control_master_active = False
                
                cmd = self._get_ssh_command(command, use_control_master=True)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env
                )
            
            success = result.returncode == 0
            return success, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Timeout executing remote command: {command}")
            return False, "", "Timeout"
        except Exception as e:
            self.logger.warning(f"Error executing remote command: {e}")
            return False, "", str(e)
    
    def sync_remote_logs(self, remote_logs_path: str, local_logs_dir: Path, 
                        delete: bool = False, dry_run: bool = False) -> bool:
        """Sync logs from MeluXina to local directory using rsync.
        
        Args:
            remote_logs_path: Remote logs directory path (e.g., ~/ai-factory-benchmarks/logs/)
            local_logs_dir: Local directory to sync logs to
            delete: Whether to delete local files not present on remote (mirror mode)
            dry_run: Whether to perform a dry run without actual changes
            
        Returns:
            True if sync successful, False otherwise
        """
        try:
            # Ensure local directory exists
            local_logs_dir.mkdir(parents=True, exist_ok=True)
            
            # Build SSH command for rsync
            ssh_cmd = " ".join(self.ssh_base_cmd)
            
            # Build rsync command
            rsync_cmd = [
                "rsync",
                "-avz",
                "--partial",
                "--progress",
                "-e", ssh_cmd
            ]
            
            if delete:
                rsync_cmd.append("--delete")
            if dry_run:
                rsync_cmd.append("--dry-run")
            
            # Ensure remote path ends with / for rsync
            if not remote_logs_path.endswith('/'):
                remote_logs_path += '/'
            
            rsync_cmd.extend([
                f"{self.ssh_target}:{remote_logs_path}",
                str(local_logs_dir)
            ])
            
            self.logger.info(f"Syncing logs: {remote_logs_path} -> {local_logs_dir}")
            self.logger.debug(f"Running: {' '.join(rsync_cmd)}")
            
            result = subprocess.run(
                rsync_cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for large log syncs
                env=os.environ.copy()
            )
            
            if result.returncode == 0:
                self.logger.info("Log sync completed successfully")
                return True
            else:
                self.logger.warning(f"Log sync failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.warning("Timeout during log sync")
            return False
        except Exception as e:
            self.logger.error(f"Error syncing logs: {e}")
            return False
    
    def list_remote_directory(self, remote_path: str) -> List[str]:
        """List contents of a remote directory.
        
        Args:
            remote_path: Remote directory path
            
        Returns:
            List of filenames in the directory
        """
        success, stdout, stderr = self.execute_remote_command(
            f"ls -1 {remote_path}",
            timeout=10
        )
        
        if success and stdout:
            return [line.strip() for line in stdout.strip().split('\n') if line.strip()]
        else:
            self.logger.warning(f"Failed to list remote directory {remote_path}: {stderr}")
            return []
    
    def check_remote_dir_exists(self, remote_path: str) -> bool:
        """Check if a directory exists on MeluXina.
        
        Args:
            remote_path: Absolute path to check
            
        Returns:
            True if directory exists, False otherwise
        """
        success, _, _ = self.execute_remote_command(f"test -d {remote_path}", timeout=10)
        return success
