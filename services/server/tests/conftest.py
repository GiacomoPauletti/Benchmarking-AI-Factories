"""
Pytest configuration and shared fixtures for Server tests.

This file is automatically loaded by pytest and provides shared fixtures
that can be used across all test files.
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path so tests can import modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def mock_ssh_manager():
    """Mock SSHManager to avoid real SSH connections in tests."""
    with patch('ssh_manager.SSHManager') as mock:
        # Configure mock to return sensible defaults
        mock_instance = Mock()
        mock_instance.ssh_user = "test_user"
        mock_instance.ssh_host = "test_host"
        mock_instance.ssh_port = 22
        mock_instance.setup_slurm_rest_tunnel.return_value = 6820
        mock_instance.fetch_remote_file.return_value = True
        mock_instance.execute_remote_command.return_value = (True, "output", "")
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_slurm_deployer():
    """Mock SlurmDeployer to avoid real SLURM API calls in tests."""
    with patch('slurm.SlurmDeployer') as mock:
        mock_instance = Mock()
        mock_instance.submit_job.return_value = {
            "id": "12345",
            "name": "test-job",
            "status": "pending"
        }
        mock_instance.get_job_status.return_value = {
            "id": "12345",
            "status": "running"
        }
        mock_instance.list_jobs.return_value = []
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
