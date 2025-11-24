"""
Pytest configuration and shared fixtures for Server tests.

This file is automatically loaded by pytest and provides shared fixtures
that can be used across all test files.
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add src to path so tests can import modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(autouse=True)
def mock_ssh_and_slurm():
    """
    Auto-use fixture that mocks SSH for ALL tests.
    This prevents tests from trying to make real SSH connections.
    """
    # We patch ssh_manager.SSHManager because src is in sys.path
    with patch('ssh_manager.SSHManager') as mock_ssh:
        
        # Configure SSH Manager mock
        ssh_instance = MagicMock()
        ssh_instance.ssh_user = "testuser"
        ssh_instance.ssh_host = "test.example.com"
        ssh_instance.ssh_port = 22
        ssh_instance.get_slurm_token.return_value = "test-token-12345"
        ssh_instance.fetch_remote_file.return_value = True
        ssh_instance.execute_remote_command.return_value = (0, "output", "")
        mock_ssh.return_value = ssh_instance
        
<<<<<<< HEAD
        yield {"ssh": ssh_instance}
=======
        # Configure SLURM Deployer mock
        slurm_instance = MagicMock()
        slurm_instance.submit_job.return_value = {
            "job_id": 12345,
            "name": "test-job",
            "state": "PENDING"
        }
        slurm_instance.get_job_status.return_value = {
            "job_id": 12345,
            "state": "RUNNING"
        }
        slurm_instance.list_jobs.return_value = []
        slurm_instance.ssh_manager = ssh_instance
        slurm_instance.token = "test-token-12345"
        mock_slurm.return_value = slurm_instance
        
        yield {"ssh": ssh_instance, "slurm": slurm_instance}
>>>>>>> dev


@pytest.fixture
def mock_ssh_manager():
    """Mock SSHManager to avoid real SSH connections in tests."""
    with patch('ssh_manager.SSHManager') as mock:
        # Configure mock to return sensible defaults
        mock_instance = MagicMock()
        mock_instance.ssh_user = "test_user"
        mock_instance.ssh_host = "test_host"
        mock_instance.ssh_port = 22
        mock_instance.get_slurm_token.return_value = "test-token"
        mock_instance.fetch_remote_file.return_value = True
        mock_instance.execute_remote_command.return_value = (0, "output", "")
        mock.return_value = mock_instance
        yield mock_instance





@pytest.fixture
def test_env():
    """Set up test environment variables."""
    original_env = os.environ.copy()
    
    # Set test environment variables
    os.environ['SSH_HOST'] = 'test.example.com'
    os.environ['SSH_USER'] = 'testuser'
    os.environ['SSH_PORT'] = '22'
    os.environ['REMOTE_BASE_PATH'] = '/test/path'
    os.environ['LOG_LEVEL'] = 'DEBUG'
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(scope="session")
def docker_compose_command():
    """Command to use for docker-compose (handles both 'docker compose' and 'docker-compose')."""
    import subprocess
    try:
        subprocess.run(["docker", "compose", "version"], check=True, capture_output=True)
        return ["docker", "compose"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["docker-compose"]
