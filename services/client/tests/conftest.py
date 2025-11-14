"""
Pytest configuration and shared fixtures for Client Service tests.

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
    Auto-use fixture that mocks SSH and SLURM for ALL tests.
    This prevents tests from trying to make real SSH connections.
    """
    with patch('client_service.ssh_manager.SSHManager') as mock_ssh:
        
        # Configure SSH Manager mock
        ssh_instance = MagicMock()
        ssh_instance.ssh_user = "testuser"
        ssh_instance.ssh_host = "test.example.com"
        ssh_instance.ssh_port = 22
        ssh_instance.ssh_target = "testuser@test.example.com"
        ssh_instance.get_slurm_token.return_value = "test-token-12345"
        ssh_instance.setup_slurm_rest_tunnel.return_value = 6820
        ssh_instance.fetch_remote_file.return_value = True
        ssh_instance.execute_remote_command.return_value = (True, "output", "")
        ssh_instance.check_remote_file_exists.return_value = True
        ssh_instance.check_remote_dir_exists.return_value = True
        ssh_instance.create_remote_directory.return_value = True
        ssh_instance.sync_directory_to_remote.return_value = True
        mock_ssh.return_value = ssh_instance
        
        yield {"ssh": ssh_instance}


@pytest.fixture
def mock_ssh_manager():
    """Mock SSHManager to avoid real SSH connections in tests."""
    with patch('client_service.ssh_manager.SSHManager') as mock:
        # Configure mock to return sensible defaults
        mock_instance = MagicMock()
        mock_instance.ssh_user = "test_user"
        mock_instance.ssh_host = "test_host"
        mock_instance.ssh_port = 22
        mock_instance.ssh_target = "test_user@test_host"
        mock_instance.get_slurm_token.return_value = "test-token"
        mock_instance.setup_slurm_rest_tunnel.return_value = 6820
        mock_instance.fetch_remote_file.return_value = True
        mock_instance.execute_remote_command.return_value = (True, "output", "")
        mock_instance.check_remote_file_exists.return_value = True
        mock_instance.check_remote_dir_exists.return_value = True
        mock_instance.create_remote_directory.return_value = True
        mock_instance.sync_directory_to_remote.return_value = True
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_slurm_dispatcher():
    """Mock SlurmClientDispatcher to avoid real SLURM API calls in tests."""
    with patch('client_service.deployment.client_dispatcher.SlurmClientDispatcher') as mock:
        mock_instance = MagicMock()
        mock_instance.dispatch.return_value = None
        mock_instance._submit_slurm_job_via_ssh.return_value = (True, {
            "job_id": 12345,
            "name": "test-job",
            "state": "PENDING"
        })
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


@pytest.fixture
def mock_client_manager():
    """Mock ClientManager for testing."""
    with patch('client_service.client_manager.client_manager.ClientManager') as mock:
        mock_instance = MagicMock()
        mock_instance.add_client_group.return_value = 0  # OK status
        mock_instance.remove_client_group.return_value = None
        mock_instance.list_groups.return_value = []
        mock_instance.get_group_info.return_value = {
            "num_clients": 10,
            "client_address": "http://test:8000",
            "created_at": 1234567890.0
        }
        mock_instance.run_client_group.return_value = [{"status": "ok"}]
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture(scope="session")
def docker_compose_command():
    """Command to use for docker-compose (handles both 'docker compose' and 'docker-compose')."""
    import subprocess
    try:
        subprocess.run(["docker", "compose", "version"], check=True, capture_output=True)
        return ["docker", "compose"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["docker-compose"]
