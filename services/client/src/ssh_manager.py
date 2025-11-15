"""
SSH connection management for MeluXina HPC cluster.
Handles SSH tunnels, remote file operations, and command execution.
"""

import os
import subprocess
import logging
import requests
import json
from pathlib import Path
from typing import Optional, Tuple, List


class SSHManager:
    """Manages SSH connections and operations from local to MeluXina HPC cluster.
    
    Provides functionality for:
    - SSH tunnel creation for SLURM REST API
    - Remote file fetching (logs, etc.)
    - Recipe synchronization to remote HPC
    - Remote command execution
    - Auto-fetching SLURM JWT tokens
    """
    
    def __init__(self, ssh_host: str = None, ssh_user: str = None, ssh_port: int = None):
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
        self.ssh_base_cmd = ["ssh"]
        if self.ssh_port != 22:
            self.ssh_base_cmd.extend(["-p", str(self.ssh_port)])
        
        # Disable host key checking for container environments
        # In production, consider mounting known_hosts or using accept-new
        self.ssh_base_cmd.extend(["-o", "StrictHostKeyChecking=no"])
        self.ssh_base_cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])
        
        self.logger.info(f"SSH Manager initialized for {self.ssh_target}:{self.ssh_port} (using SSH agent)")
    
    def get_slurm_token(self) -> str:
        """Fetch a fresh SLURM JWT token from MeluXina.
        
        Returns:
            SLURM JWT token string
            
        Raises:
            RuntimeError: If token fetch fails
        """
        self.logger.info("Fetching SLURM JWT token from MeluXina...")
        success, stdout, stderr = self.execute_remote_command("scontrol token", timeout=10)
        
        if not success:
            raise RuntimeError(f"Failed to fetch SLURM token: {stderr}")
        
        # Parse output: "SLURM_JWT=eyJhbGc..."
        for line in stdout.strip().split('\n'):
            if line.startswith('SLURM_JWT='):
                token = line.split('=', 1)[1].strip()
                self.logger.info("Successfully fetched SLURM JWT token")
                return token
        
        raise RuntimeError(f"Could not parse SLURM token from output: {stdout}")
    
    def ensure_remote_directories(self, remote_base_path: str):
        """Ensure required directories exist on MeluXina.
        
        Creates directories for recipes and logs if they don't exist.
        
        Args:
            remote_base_path: Base path on MeluXina (e.g., /project/home/p200981/u103056/...)
        """
        self.logger.info(f"Ensuring remote directories exist at {remote_base_path}")
        
        dirs_to_create = [
            f"{remote_base_path}/src/recipes",
            f"{remote_base_path}/logs"
        ]
        
        cmd = f"mkdir -p {' '.join(dirs_to_create)}"
        success, stdout, stderr = self.execute_remote_command(cmd, timeout=10)
        
        if not success:
            self.logger.warning(f"Failed to create remote directories: {stderr}")
        else:
            self.logger.info("Remote directories ready")
    
    def setup_slurm_rest_tunnel(self, local_port: int = 6820, 
                                remote_host: str = "slurmrestd.meluxina.lxp.lu",
                                remote_port: int = 6820) -> int:
        """Establish SSH tunnel for SLURM REST API.
        
        Creates a port forward: localhost:local_port -> remote_host:remote_port
        
        Args:
            local_port: Local port to bind to (default: 6820)
            remote_host: Remote SLURM REST API host
            remote_port: Remote SLURM REST API port
            
        Returns:
            The local port number if successful
            
        Raises:
            RuntimeError: If tunnel creation fails
        """
        # Check if tunnel already exists
        if self._is_tunnel_active(local_port):
            self.logger.info(f"SSH tunnel already active on port {local_port}")
            return local_port
        
        # Create SSH tunnel in background
        try:
            ssh_command = self.ssh_base_cmd + [
                "-f", "-N",
                "-L", f"{local_port}:{remote_host}:{remote_port}",
                "-o", "ExitOnForwardFailure=yes",
                "-o", "ServerAliveInterval=60",
                self.ssh_target
            ]
            
            self.logger.debug(f"Creating SSH tunnel: {' '.join(ssh_command)}")
            
            # Ensure SSH_AUTH_SOCK is available for SSH agent authentication
            env = os.environ.copy()
            
            result = subprocess.run(
                ssh_command,
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            if result.returncode != 0:
                raise ConnectionError(f"Failed to create SSH tunnel: {result.stderr}")
            
            self.logger.info(f"SSH tunnel established: localhost:{local_port} -> {remote_host}:{remote_port}")
            
            # Wait a moment for tunnel to be ready
            import time
            time.sleep(1)
            
            return local_port
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("SSH tunnel creation timed out")
        except Exception as e:
            self.logger.error(f"Failed to establish SSH tunnel: {e}")
            raise RuntimeError(f"SSH tunnel setup failed: {str(e)}")
    
    def _is_tunnel_active(self, local_port: int) -> bool:
        """Check if an SSH tunnel is already active on the given port.
        
        Args:
            local_port: Port to check
            
        Returns:
            True if tunnel is active, False otherwise
        """
        try:
            test_response = requests.get(
                f"http://localhost:{local_port}/slurm/v0.0.40/ping",
                timeout=2
            )
            # API responding (even with auth errors) means tunnel is active
            return test_response.status_code in [200, 401, 403]
        except:

            return False
    
    def fetch_remote_file(self, remote_path: str, local_path: Path) -> bool:
        """Fetch a file from the remote MeluXina filesystem via SSH.
        
        Uses SSH to cat the remote file and save it locally.
        
        Args:
            remote_path: Absolute path to the file on MeluXina
            local_path: Local path where the file should be saved
            
        Returns:
            True if file was successfully fetched, False otherwise
        """
        try:
            # Build SSH command with proper port and key
            cmd = self.ssh_base_cmd + [
                self.ssh_target,
                f"cat {remote_path}"
            ]
            
            # Ensure SSH_AUTH_SOCK is available for SSH agent authentication
            env = os.environ.copy()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            
            if result.returncode == 0 and result.stdout:
                # Ensure local directory exists
                local_path.parent.mkdir(parents=True, exist_ok=True)
                # Write the fetched content
                local_path.write_text(result.stdout)
                self.logger.debug(f"Fetched remote file: {remote_path} -> {local_path}")
                return True
            else:
                self.logger.debug(f"Remote file not found or empty: {remote_path}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Timeout fetching remote file: {remote_path}")
            return False
        except Exception as e:
            self.logger.warning(f"Error fetching remote file {remote_path}: {e}")
            return False
    
    def sync_directory_to_remote(self, local_dir: Path, remote_dir: str, 
                                 exclude_patterns: Optional[List[str]] = None) -> bool:
        """Sync a local directory to MeluXina using rsync.
        
        Args:
            local_dir: Local directory path to sync
            remote_dir: Remote directory path on MeluXina
            exclude_patterns: List of patterns to exclude (e.g., ['*.pyc', '__pycache__/'])
            
        Returns:
            True if sync successful, False otherwise
        """
        if not local_dir.exists():
            self.logger.warning(f"Local directory not found: {local_dir}")
            return False
        
        try:
            # Ensure remote directory exists using proper SSH command
            mkdir_cmd = self.ssh_base_cmd + [self.ssh_target, f"mkdir -p {remote_dir}"]
            
            # Ensure SSH_AUTH_SOCK is available for SSH agent authentication
            env = os.environ.copy()
            
            subprocess.run(mkdir_cmd, check=True, capture_output=True, timeout=10, env=env)
            
            # Build SSH command for rsync (no -i flag needed with SSH agent)
            rsync_ssh_cmd = "ssh"
            if self.ssh_port != 22:
                rsync_ssh_cmd += f" -p {self.ssh_port}"
            
            # Build rsync command
            rsync_cmd = ["rsync", "-az", "--delete", "-e", rsync_ssh_cmd]
            
            # Add exclude patterns
            if exclude_patterns:
                for pattern in exclude_patterns:
                    rsync_cmd.extend(["--exclude", pattern])
            
            # Add source and destination (trailing slash important for rsync)
            rsync_cmd.append(f"{local_dir}/")
            rsync_cmd.append(f"{self.ssh_target}:{remote_dir}/")
            
            self.logger.debug(f"Running rsync: {' '.join(rsync_cmd)}")
            
            result = subprocess.run(
                rsync_cmd, 
                capture_output=True, 
                text=True, 
                timeout=60,
                env=env
            )
            
            if result.returncode == 0:
                self.logger.info(f"Synced directory: {local_dir} -> {remote_dir}")
                return True
            else:
                self.logger.warning(f"Failed to sync directory: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Timeout syncing directory: {local_dir}")
            return False
        except Exception as e:
            self.logger.warning(f"Error syncing directory {local_dir}: {e}")
            return False
    
    def execute_remote_command(self, command: str, timeout: int = 30) -> Tuple[bool, str, str]:
        """Execute a command on MeluXina via SSH.
        
        Args:
            command: Command to execute
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (success, stdout, stderr)
        """
        try:
            cmd = self.ssh_base_cmd + [self.ssh_target, command]
            
            # Ensure SSH_AUTH_SOCK is available for SSH agent authentication
            env = os.environ.copy()
            
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
    
    def check_remote_file_exists(self, remote_path: str) -> bool:
        """Check if a file exists on MeluXina.
        
        Args:
            remote_path: Absolute path to check
            
        Returns:
            True if file exists, False otherwise
        """
        success, _, _ = self.execute_remote_command(f"test -f {remote_path}", timeout=10)
        return success
    
    def check_remote_dir_exists(self, remote_path: str) -> bool:
        """Check if a directory exists on MeluXina.
        
        Args:
            remote_path: Absolute path to check
            
            
        Returns:
            True if directory exists, False otherwise
        """
        success, _, _ = self.execute_remote_command(f"test -d {remote_path}", timeout=10)
        return success
    
    def create_remote_directory(self, remote_path: str) -> bool:
        """Create a directory on MeluXina (with parents).
        
        Args:
            remote_path: Absolute path to create
            
        Returns:
            True if successful, False otherwise
        """
        success, _, stderr = self.execute_remote_command(f"mkdir -p {remote_path}", timeout=10)
        if not success:
            self.logger.warning(f"Failed to create remote directory {remote_path}: {stderr}")
        return success
    
    def http_request_via_ssh(self, remote_host: str, remote_port: int, method: str, path: str, 
                             headers: Optional[dict] = None, json_data: Optional[dict] = None, timeout: int = 30) -> Tuple[bool, int, str]:
        """Make an HTTP request to a remote host through SSH using curl.
        
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
            
        Returns:
            Tuple of (success: bool, status_code: int, response_body: str)
        """
        import json as json_lib
        import shlex
        
        url = f"http://{remote_host}:{remote_port}{path}"
        
        # Build curl command as a list (will be properly escaped)
        curl_cmd_parts = ["curl", "-s", "-w", "\\nHTTP_STATUS:%{http_code}"]
        
        # Add method
        if method != "GET":
            curl_cmd_parts.extend(["-X", method])
        
        # Add headers
        if headers:
            for key, value in headers.items():
                curl_cmd_parts.extend(["-H", f"{key}: {value}"])
        
        # Add JSON data for POST/PUT
        if json_data:
            curl_cmd_parts.extend(["-H", "Content-Type: application/json"])
            # Use shlex.quote to properly escape the JSON string
            json_str = json_lib.dumps(json_data)
            curl_cmd_parts.extend(["-d", json_str])
        
        # Add URL and timeout
        curl_cmd_parts.extend(["--max-time", str(timeout), url])
        
        curl_cmd = " ".join(shlex.quote(str(part)) for part in curl_cmd_parts)
        
        self.logger.debug(f"Executing HTTP request via SSH: {curl_cmd}")
        
        try:
            success, stdout, stderr = self.execute_remote_command(curl_cmd, timeout=timeout + 5)
            
            if not success:
                self.logger.warning(f"HTTP request via SSH failed: {stderr}")
                return False, 0, stderr
            
            # Parse response - curl writes status code after HTTP_STATUS:
            if "HTTP_STATUS:" in stdout:
                parts = stdout.rsplit("HTTP_STATUS:", 1)
                body = parts[0].strip()
                try:
                    status_code = int(parts[1].strip())
                except ValueError:
                    status_code = 0
                    body = stdout
            else:
                body = stdout
                status_code = 200 if success else 0
            
            return True, status_code, body
            
        except Exception as e:
            self.logger.exception(f"Error making HTTP request via SSH: {e}")
            return False, 0, str(e)

    def setup_slurm_rest_tunnel(self, local_port: int = 6821, 
                                remote_host: str = "slurmrestd.meluxina.lxp.lu",
                                remote_port: int = 6820) -> int:
        """Establish SSH tunnel for SLURM REST API.
        
        Creates a port forward: localhost:local_port -> remote_host:remote_port
        
        Args:
            local_port: Local port to bind to (default: 6821 for client service)
            remote_host: Remote SLURM REST API host
            remote_port: Remote SLURM REST API port
            
        Returns:
            The local port number if successful
            
        Raises:
            RuntimeError: If tunnel creation fails
        """
        # Check if tunnel already exists
        if self._is_tunnel_active(local_port):
            self.logger.info(f"SSH tunnel already active on port {local_port}")
            return local_port
        
        # Create SSH tunnel in background
        try:
            ssh_command = self.ssh_base_cmd + [
                "-f", "-N",
                "-L", f"{local_port}:{remote_host}:{remote_port}",
                "-o", "ExitOnForwardFailure=yes",
                "-o", "ServerAliveInterval=60",
                self.ssh_target
            ]
            
            self.logger.debug(f"Creating SSH tunnel: {' '.join(ssh_command)}")
            
            # Ensure SSH_AUTH_SOCK is available for SSH agent authentication
            env = os.environ.copy()
            
            result = subprocess.run(
                ssh_command,
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            if result.returncode != 0:
                raise ConnectionError(f"Failed to create SSH tunnel: {result.stderr}")
            
            self.logger.info(f"SSH tunnel established: localhost:{local_port} -> {remote_host}:{remote_port}")
            
            # Wait a moment for tunnel to be ready
            import time
            time.sleep(1)
            
            return local_port
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("SSH tunnel creation timed out")
        except Exception as e:
            self.logger.error(f"Failed to establish SSH tunnel: {e}")
            raise RuntimeError(f"SSH tunnel setup failed: {str(e)}")
    
    def _is_tunnel_active(self, local_port: int) -> bool:
        """Check if an SSH tunnel is already active on the given port.
        
        Args:
            local_port: Port to check
            
        Returns:
            True if tunnel is active, False otherwise
        """
        try:
            test_response = requests.get(
                f"http://localhost:{local_port}/slurm/v0.0.40/ping",
                timeout=2
            )
            # API responding (even with auth errors) means tunnel is active
            return test_response.status_code in [200, 401, 403]
        except:
            return False

    