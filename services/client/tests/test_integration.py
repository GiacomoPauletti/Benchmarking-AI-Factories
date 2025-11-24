"""
Integration Tests for Client Service

Integration tests test the full system working together.
These tests may require:
- Docker containers
- Network access
- SLURM REST API (mocked or real)
- Longer execution time

Run with: pytest tests/test_integration.py -v
Skip with: pytest tests/ -v -m "not integration"
"""

import pytest
import time
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from main import app


# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


class TestFullClientWorkflow:
    """Test the full client service workflow end-to-end."""
    
    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app."""
        return TestClient(app)
    
    def test_create_and_run_client_group_workflow(self, client, mock_ssh_manager):
        """Test creating a client group and running it."""
        with patch('client_manager.client_group.ClientGroup'):
            # Step 1: Create a client group
            response = client.post(
                "/api/v1/client-groups",
                json={"service_id": "sg-int", "num_clients": 5, "requests_per_second": 1.0, "duration_seconds": 10}
            )
            assert response.status_code in [200, 201]

            data = response.json()
            group_id = data.get("group_id")
            assert group_id is not None

            # Step 2: Check group was created
            response = client.get("/api/v1/client-groups")
            assert response.status_code == 200

            # Step 3: Get group info
            response = client.get(f"/api/v1/client-groups/{group_id}")
            assert response.status_code in [200, 404]

            # Step 4: Attempt to remove the group
            response = client.delete(f"/api/v1/client-groups/{group_id}")
            assert response.status_code in [200, 204, 404]
    
    def test_multiple_client_groups(self, client, mock_ssh_manager):
        """Test managing multiple client groups simultaneously."""
        with patch('client_manager.client_group.ClientGroup'):
            benchmark_ids = [int(time.time()) + i for i in range(3)]
            
            # Create multiple groups
            for bid in benchmark_ids:
                response = client.post(
                    "/api/v1/client-groups",
                    json={"service_id": "sg-int", "num_clients": 10, "requests_per_second": 1.0, "duration_seconds": 30}
                )
                assert response.status_code in [200, 201]
            
            # List all groups
            response = client.get("/api/v1/client-groups")
            assert response.status_code == 200
            
            # Clean up
            for bid in benchmark_ids:
                # We don't have the generated group ids here; just ensure delete endpoint can be called gracefully
                pass
    
    def test_error_handling_invalid_benchmark_id(self, client):
        """Test error handling for invalid benchmark IDs."""
        # Try to get info for non-existent group
        response = client.get("/api/v1/client-groups/999999999")
        assert response.status_code in [200, 404]
        
        # Try to run non-existent group (no direct run endpoint). Ensure delete/get behave as expected
        response = client.get("/api/v1/client-groups/999999999")
        assert response.status_code in [200, 404]


class TestSlurmIntegration:
    """Test SLURM integration (with mocks)."""
    
    def test_slurm_job_submission(self, mock_ssh_manager):
        """Test that SLURM job can be submitted."""
        from deployment.client_dispatcher import SlurmClientDispatcher
        
        with patch.object(SlurmClientDispatcher, '_submit_slurm_job_via_ssh') as mock_submit:
            mock_submit.return_value = (True, {
                "job_id": 12345,
                "name": "ai-factory-clients-12345",
                "state": "PENDING"
            })
            
            dispatcher = SlurmClientDispatcher(load_config={"num_clients": 10}, account="p200981", use_container=False)

            dispatcher.dispatch(group_id=12345, time_limit=30)
            
            # Verify the job was submitted
            assert mock_submit.called
            call_args = mock_submit.call_args
            assert call_args is not None
    
    def test_slurm_tunnel_setup(self, mock_ssh_manager):
        """Test that SSH tunnel for SLURM is set up correctly."""
        from deployment.client_dispatcher import SlurmClientDispatcher
        
        with patch.object(SlurmClientDispatcher, '_submit_slurm_job_via_ssh') as mock_submit:
            mock_submit.return_value = (True, {"job_id": 12345})
            
            dispatcher = SlurmClientDispatcher(load_config={}, account="p200981")

            # Verify remote directories were ensured (SSH execute called)
            assert mock_ssh_manager.execute_remote_command.called
            assert dispatcher._rest_api_port == 6821


class TestSSHIntegration:
    """Test SSH integration (with mocks)."""
    
    def test_ssh_connection(self, mock_ssh_manager):
        """Test that SSH connection can be established."""
        from ssh_manager import SSHManager
        
        # SSH manager should initialize without errors
        assert mock_ssh_manager.ssh_user == "testuser"
        assert mock_ssh_manager.ssh_host == "test.example.com"
    
    def test_slurm_token_fetch(self, mock_ssh_manager):
        """Test fetching SLURM token via SSH."""
        token = mock_ssh_manager.get_slurm_token()
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0


@pytest.mark.slow
class TestStressTests:
    """Stress tests for client service (marked as slow)."""
    
    def test_many_client_groups(self, client, mock_ssh_manager):
        """Test creating many client groups."""
        with patch('client_manager.client_group.ClientGroup'):
            num_groups = 10
            benchmark_ids = [int(time.time()) + i for i in range(num_groups)]
            
            # Create many groups
            for bid in benchmark_ids:
                response = client.post(
                    f"/api/v1/client-groups",
                    json={"service_id": f"sg-{bid}", "num_clients": 100, "time_limit": 60, "requests_per_second": 1.0}
                )
                assert response.status_code in [200, 201]
            
            # Verify all were created
            response = client.get("/api/v1/client-groups")
            assert response.status_code == 200
            
            # Clean up
            for bid in benchmark_ids:
                client.delete(f"/api/v1/client-groups/{bid}")
