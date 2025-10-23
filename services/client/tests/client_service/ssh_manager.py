"""
Unit tests for SSHManager.

These tests validate actual SSH connectivity to MeluXina HPC cluster.
They require proper SSH configuration in .env file and SSH keys to be set up.
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from client_service.ssh_manager import SSHManager


class TestSSHManager:
    """Integration tests for SSHManager using real MeluXina connections."""
    
    @classmethod
    def setup_class(cls):
        """Set up test class with environment variables."""
        # Load .env file from project root
        if os.environ.get('SSH_USER') is None:  # Only load if not already set
            env_file = Path(__file__).parent.parent.parent.parent.parent / '.env'
            if env_file.exists():
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            # Expand environment variables like ${SSH_USER}
                            if '${' in value:
                                value = os.path.expandvars(value)
                            os.environ[key] = value
    
    def test_ssh_manager_initialization(self):
        """Test that SSHManager can be initialized with environment variables."""
        ssh_manager = SSHManager() 
        
        # Check that the manager has the expected configuration
        assert ssh_manager.ssh_host == os.environ.get('SSH_HOST', 'login.lxp.lu')
        assert ssh_manager.ssh_port == int(os.environ.get('SSH_PORT', '8822'))
        assert ssh_manager.ssh_user == os.environ.get('SSH_USER')
        assert ssh_manager.ssh_key_path is not None
    
    @pytest.mark.unit
    def test_basic_ssh_connection(self):
        """Test basic SSH connection with a simple echo command."""
        ssh_manager = SSHManager()
        
        try:
            # Test simple echo command
            success, stdout, stderr = ssh_manager.execute_remote_command('echo "SSH connection test successful"')
            
            assert success == True
            assert "SSH connection test successful" in stdout
            print(f"SSH test successful: {stdout.strip()}")
            
        except Exception as e:
            pytest.fail(f"SSH connection failed: {str(e)}")
    
    @pytest.mark.unit
    def test_remote_directory_check(self):
        """Test checking if remote directory exists."""
        ssh_manager = SSHManager()
        
        try:
            # Check if home directory exists (should always exist)
            success, stdout, stderr = ssh_manager.execute_remote_command('test -d $HOME && echo "HOME exists"')
            
            assert success == True
            assert "HOME exists" in stdout
            print(f"Remote directory test successful: {stdout.strip()}")
            
        except Exception as e:
            pytest.fail(f"Remote directory check failed: {str(e)}")
    
    @pytest.mark.unit
    def test_remote_base_path_exists(self):
        """Test if the configured REMOTE_BASE_PATH exists on MeluXina."""
        ssh_manager = SSHManager()
        remote_base_path = os.environ.get('REMOTE_BASE_PATH', f"/home/users/{os.environ.get('SSH_USER')}/Benchmarking-AI-Factories")
        
        try:
            # Check if the remote base path exists
            success, stdout, stderr = ssh_manager.execute_remote_command(f'test -d "{remote_base_path}" && echo "Base path exists" || echo "Base path missing"')
            
            assert success == True
            
            if "Base path exists" in stdout:
                print(f"Remote base path exists: {remote_base_path}")
            else:
                print(f"Warning: Remote base path does not exist: {remote_base_path}")
                print("You may need to clone the repository on MeluXina")
            
        except Exception as e:
            pytest.fail(f"Remote base path check failed: {str(e)}")
    
    @pytest.mark.unit
    def test_slurm_availability(self):
        """Test if SLURM commands are available on MeluXina."""
        ssh_manager = SSHManager()
        
        try:
            # Check if sinfo command is available
            success, stdout, stderr = ssh_manager.execute_remote_command('which sinfo')
            
            if success:
                print(f"SLURM available at: {stdout.strip()}")
                
                # Try to get cluster info
                info_success, info_stdout, info_stderr = ssh_manager.execute_remote_command('sinfo --version')
                if info_success:
                    print(f"SLURM version: {info_stdout.strip()}")
            else:
                print("Warning: SLURM commands not found in PATH")
            
        except Exception as e:
            pytest.fail(f"SLURM availability check failed: {str(e)}")

    @pytest.mark.unit
    def test_get_slurm_token(self):
        """Test retrieving SLURM token via SSHManager."""
        ssh_manager = SSHManager()
        
        try:
            token = ssh_manager.get_slurm_token()
            assert token is not None
            assert len(token) > 0
            print(f"Retrieved SLURM token: {token}")
        except Exception as e:
            pytest.fail(f"Failed to retrieve SLURM token: {str(e)}")
    
