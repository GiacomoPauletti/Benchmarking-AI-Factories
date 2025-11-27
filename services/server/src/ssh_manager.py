"""
SSH connection management for MeluXina HPC cluster.
Handles SSH tunnels, remote file operations, and command execution.
Uses SSH ControlMaster for persistent connections to reduce overhead.
"""

import os
import subprocess
import logging
import requests
import time
from pathlib import Path
from typing import Optional, Tuple, Dict


class SSHManager:
    """Manages SSH connections and operations from local to MeluXina HPC cluster.
    """
    
    def __init__(self, ssh_host: str = None, ssh_user: str = None, ssh_port: int = None, local_socks_port: int = 1080):
        """Initialize SSH manager with connection details.
        
        Authentication is handled via SSH agent forwarding (SSH_AUTH_SOCK).
        No raw SSH keys are exposed to the container.
        
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
        
        # Verify SSH agent is available
        ssh_auth_sock = os.getenv('SSH_AUTH_SOCK')
        if not ssh_auth_sock:
            self.logger.warning("SSH_AUTH_SOCK not set. SSH agent forwarding may not work.")
        
        # Build SSH target and base command
        self.ssh_target = f"{self.ssh_user}@{self.ssh_host}"
        
        # Build base SSH command with port (authentication via SSH agent)
        self._ssh_base_cmd = ["ssh"]
        if self.ssh_port != 22:
            self._ssh_base_cmd.extend(["-p", str(self.ssh_port)])
        
        # Disable host key checking for container environments
        # In production, consider mounting known_hosts or using accept-new
        self._ssh_base_cmd.extend(["-o", "StrictHostKeyChecking=no"])
        self._ssh_base_cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])
        
        # ControlMaster setup for persistent SSH connections
        self.control_socket_dir = Path("/tmp/ssh-control-sockets")
        self.control_socket_dir.mkdir(parents=True, exist_ok=True)
        self._control_master_socket = self.control_socket_dir / f"master-{self.ssh_user}@{self.ssh_host}:{self.ssh_port}"
        self._control_master_active = False
        self._last_control_check = 0
        self._control_check_interval = 30  # Check every 30s

        self._local_socks_port = local_socks_port
        self._establish_socks_proxy(local_port=local_socks_port)
        self._establish_session(local_socks_port=local_socks_port)
        
        self.logger.info(f"SSH Manager initialized for {self.ssh_target}:{self.ssh_port} (using SSH agent)")
        self.logger.info(f"ControlMaster socket: {self._control_master_socket}")

    def _establish_socks_proxy(self, local_port: int = 1080) -> bool:
        """Establish a SOCKS5 proxy tunnel to MeluXina via SSH.
        
        Args:
            local_port: Local port to bind the SOCKS5 proxy (default: 1080)
        """
        try:
            # Build SSH command for SOCKS5 proxy
            ssh_command = self._ssh_base_cmd + [
                "-D", str(local_port),
                "-N",
                "-o", "ExitOnForwardFailure=yes",
                "-o", "ServerAliveInterval=60",
                self.ssh_target
            ]
            
            self.logger.debug(f"Establishing SOCKS5 proxy: {' '.join(ssh_command)}")
            
            self.socks_proxy = subprocess.Popen(ssh_command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            
            # Wait a moment for the SOCKS proxy to be ready
            time.sleep(2)
            
            # Verify the proxy is actually listening
            if self.socks_proxy.poll() is not None:
                stderr = self.socks_proxy.stderr.read().decode() if self.socks_proxy.stderr else ""
                self.logger.error(f"SOCKS proxy failed to start: {stderr}")
                return False
            
            self.logger.info(f"SOCKS5 proxy established on localhost:{local_port}, PID: {self.socks_proxy.pid}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to establish SOCKS5 proxy: {e}")
            return False
        
    def _establish_session(self, local_socks_port: int = 1080) -> bool:
        """Establish a requests session that uses the SOCKS5 proxy."""
        try:
            self._session = requests.Session()
            self._session.proxies = {
                "http": f"socks5h://localhost:{local_socks_port}",
                "https": f"socks5h://localhost:{local_socks_port}"
            }
            self.logger.info("HTTP session established using SOCKS5 proxy")
            return True
        except Exception as e:
            self.logger.error(f"Failed to establish HTTP session via SOCKS5 proxy: {e}")
            return False
    
    def _ensure_control_master(self) -> bool:
        """Ensure a ControlMaster connection is active.
        
        Creates a persistent SSH connection that can be reused by subsequent commands,
        significantly reducing connection overhead.
        
        Returns:
            True if control master is active, False otherwise
        """
        now = time.time()
        
        # Check if we recently verified the connection
        if self._control_master_active and (now - self._last_control_check) < self._control_check_interval:
            return True
        
        # Check if control master socket exists and is responsive
        if self._control_master_socket.exists():
            try:
                # Test if control master is alive with a quick command
                test_cmd = self._ssh_base_cmd + [
                    "-S", str(self._control_master_socket),
                    "-O", "check",
                    self.ssh_target
                ]
                result = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    timeout=2
                )
                
                if result.returncode == 0:
                    self.logger.debug("ControlMaster connection is alive")
                    self._control_master_active = True
                    self._last_control_check = now
                    return True
                else:
                    self.logger.debug("ControlMaster check failed, will recreate")
                    # Force remove socket file if check failed
                    try:
                        if self._control_master_socket.exists():
                            self._control_master_socket.unlink()
                    except Exception as e:
                        self.logger.warning(f"Failed to remove stale socket: {e}")
            except Exception as e:
                self.logger.debug(f"ControlMaster check error: {e}")
                # Force remove socket file if check error
                try:
                    if self._control_master_socket.exists():
                        self._control_master_socket.unlink()
                except Exception as ex:
                    self.logger.warning(f"Failed to remove stale socket: {ex}")
        
        # Create new control master
        try:
            self.logger.info("Creating ControlMaster connection...")
            
            master_cmd = self._ssh_base_cmd + [
                "-M",  # Master mode
                "-S", str(self._control_master_socket),  # Control socket path
                "-o", "ControlPersist=600",  # Keep connection alive for 10 minutes after last use
                "-o", "ServerAliveInterval=60",  # Send keepalive every 60s
                "-o", "ServerAliveCountMax=3",  # Allow 3 missed keepalives before disconnect
                "-o", "ExitOnForwardFailure=yes",
                "-fN",  # Background, no command execution
                self.ssh_target
            ]
            
            result = subprocess.run(
                master_cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode != 0:
                self.logger.warning(f"Failed to create ControlMaster: {result.stderr}")
                self._control_master_active = False
                return False
            
            # Wait briefly for socket to be created
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
        """Build SSH command with optional ControlMaster support.
        
        Args:
            command: Optional command to execute
            use_control_master: Whether to use ControlMaster (default: True)
            
        Returns:
            List of command parts for subprocess
        """
        cmd = self._ssh_base_cmd.copy()
        
        # Add ControlMaster socket if available
        if use_control_master and self._ensure_control_master():
            cmd.extend(["-S", str(self._control_master_socket)])
        
        # Add target
        cmd.append(self.ssh_target)
        
        # Add command if provided
        if command:
            cmd.append(command)
        
        return cmd
    
    def close_control_master(self):
        """Close the ControlMaster connection gracefully."""
        if not self._control_master_active or not self._control_master_socket.exists():
            return
        
        try:
            self.logger.info("Closing ControlMaster connection...")
            exit_cmd = self._ssh_base_cmd + [
                "-S", str(self._control_master_socket),
                "-O", "exit",
                self.ssh_target
            ]
            subprocess.run(
                exit_cmd,
                capture_output=True,
                timeout=5
            )
            self._control_master_active = False
            self.logger.info("ControlMaster connection closed")
        except Exception as e:
            self.logger.warning(f"Error closing ControlMaster: {e}")
    
    def get_slurm_token(self) -> str:
        """Fetch a fresh SLURM JWT token from MeluXina."""
        self.logger.info("Fetching SLURM JWT token from MeluXina...")
        success, stdout, stderr = self.execute_remote_command("scontrol token", timeout=10)
        
        if not success:
            raise RuntimeError(f"Failed to fetch SLURM token: {stderr}")
        
        for line in stdout.strip().split('\n'):
            if line.startswith('SLURM_JWT='):
                token = line.split('=', 1)[1].strip()
                self.logger.info("Successfully fetched SLURM JWT token")
                return token
        
        raise RuntimeError(f"Could not parse SLURM token from output: {stdout}")
    
    def execute_remote_command(self, command: str, timeout: int = 30) -> Tuple[bool, str, str]:
        """Execute a command on MeluXina via SSH with ControlMaster.
        
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
                # Force remove socket
                try:
                    if self._control_master_socket.exists():
                        self._control_master_socket.unlink()
                except:
                    pass
                self._control_master_active = False
                
                # Retry command
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
    
    def http_request_via_ssh(self, remote_host: str, remote_port: int, method: str, path: str, 
                             headers: dict = None, json_data: dict = None, timeout: int = 30,
                             json_body: bool = True) -> Tuple[bool, int, str]:
        """Make an HTTP request to a remote host through the SSH SOCKS proxy.
        
        This allows making HTTP requests to internal MeluXina nodes that aren't
        directly accessible from the Docker container.
        
        Args:
            remote_host: Hostname of the remote service (e.g., 'mel2079')
            remote_port: Port of the remote service (e.g., 8001)
            method: HTTP method (GET, POST, etc.)
            path: URL path (e.g., '/v1/chat/completions')
            headers: Optional HTTP headers dict
            json_data: Optional JSON body for POST requests
            timeout: Request timeout in seconds
            json_body: Whether the expected response is JSON (default: True)
            
        Returns:
            Tuple of (success: bool, status_code: int, response_body: str)
        """
        if (self.socks_proxy is None) or (self.socks_proxy.poll() is not None):
            if self.socks_proxy is not None:
                (stdout, stderr) = self.socks_proxy.communicate()
                self.logger.warning(f"SOCKS5 proxy process not running, exited with code {self.socks_proxy.returncode}, restarting...")
                self.logger.debug(f"SOCKS5 proxy stdout: {stdout.decode().strip()}")
                self.logger.debug(f"SOCKS5 proxy stderr: {stderr.decode().strip()}")
            else:
                self.logger.warning("SOCKS5 proxy process not initialized, starting...")
            self.socks_proxy = None
            if not self._establish_socks_proxy(local_port=self._local_socks_port):
                self.logger.error("Cannot make HTTP request via SSH: SOCKS5 proxy not available")
                # Try even if SOCKS proxy failed to start, might be a leftover
        
        url = f"http://{remote_host}:{remote_port}{path}"
        
        try:
            resp = self._session.request(method, url, timeout=timeout, headers=headers, json=json_data)
            status_code = resp.status_code
            is_json = 'application/json' in resp.headers.get('Content-Type', '')
            
            # Try to parse as JSON first, fallback to text if that fails
            # This handles cases where Content-Type header is missing but body is actually JSON
            try:
                body = resp.json()
            except (ValueError, json.JSONDecodeError):
                body = resp.text
                
            self.logger.debug(f"HTTP {method} {remote_host}:{remote_port}{path} -> {status_code} ({len(str(body))} chars) took {resp.elapsed.total_seconds()*1000:.2f}ms")

            if not resp.ok:
                self.logger.warning(f"HTTP request via SSH failed to {remote_host}:{remote_port}{path}: {status_code} - {body}")

            if json_body and not is_json:
                self.logger.warning(f"Expected JSON response but got non-JSON (Content-Type: {resp.headers.get('Content-Type')}) from {remote_host}:{remote_port}{path}")
                # Still return success if the HTTP status was OK - Content-Type header might just be missing
                # Only fail if the actual HTTP request failed
            
            return resp.ok, status_code, body
        
        except requests.ConnectionError as e:
            self.logger.warning(f"Connection refused making HTTP request via SOCKS proxy to {remote_host}:{remote_port}{path}, likely service not running")
            return False, 0, None
        except requests.Timeout as e:
            self.logger.exception(f"Timeout making HTTP request via SOCKS proxy to {remote_host}:{remote_port}{path}: {e}")
            return False, 0, None
        except Exception as e:
            self.logger.exception(f"Error making HTTP request via SOCKS proxy to {remote_host}:{remote_port}{path}: {e}")
            return False, 0, None

