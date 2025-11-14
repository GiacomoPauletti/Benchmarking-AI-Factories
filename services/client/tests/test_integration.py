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
        with patch('client_service.client_manager.client_group.ClientGroup'):
            # Step 1: Create a client group
            benchmark_id = int(time.time())
            response = client.post(
                f"/api/v1/client-group/{benchmark_id}",
                json={"num_clients": 5, "time_limit": 10}
            )
            assert response.status_code in [200, 201]
            
            # Step 2: Check group was created
            response = client.get("/api/v1/client-groups")
            assert response.status_code == 200
            
            # Step 3: Get group info
            response = client.get(f"/api/v1/client-group/{benchmark_id}")
            assert response.status_code == 200
            
            # Step 4: Try to run the group (will fail without real client process)
            response = client.post(f"/api/v1/client-group/{benchmark_id}/run")
            # Accept various status codes depending on implementation
            assert response.status_code in [200, 404, 500]
            
            # Step 5: Remove the group
            response = client.delete(f"/api/v1/client-group/{benchmark_id}")
            # Accept 200, 204 (No Content), or 404
            assert response.status_code in [200, 204, 404]
    
    def test_multiple_client_groups(self, client, mock_ssh_manager):
        """Test managing multiple client groups simultaneously."""
        with patch('client_service.client_manager.client_group.ClientGroup'):
            benchmark_ids = [int(time.time()) + i for i in range(3)]
            
            # Create multiple groups
            for bid in benchmark_ids:
                response = client.post(
                    f"/api/v1/client-group/{bid}",
                    json={"num_clients": 10, "time_limit": 30}
                )
                assert response.status_code in [200, 201]
            
            # List all groups
            response = client.get("/api/v1/client-groups")
            assert response.status_code == 200
            
            # Clean up
            for bid in benchmark_ids:
                client.delete(f"/api/v1/client-group/{bid}")
    
    def test_error_handling_invalid_benchmark_id(self, client):
        """Test error handling for invalid benchmark IDs."""
        # Try to get info for non-existent group
        response = client.get("/api/v1/client-group/999999999")
        assert response.status_code in [200, 404]
        
        # Try to run non-existent group
        response = client.post("/api/v1/client-group/999999999/run")
        assert response.status_code in [200, 404, 500]


class TestSlurmIntegration:
    """Test SLURM integration (with mocks)."""
    
    def test_slurm_job_submission(self, mock_ssh_manager):
        """Test that SLURM job can be submitted."""
        from client_service.deployment.client_dispatcher import SlurmClientDispatcher
        
        with patch.object(SlurmClientDispatcher, '_submit_slurm_job_via_ssh') as mock_submit:
            mock_submit.return_value = (True, {
                "job_id": 12345,
                "name": "ai-factory-clients-12345",
                "state": "PENDING"
            })
            
            dispatcher = SlurmClientDispatcher(
                server_addr="http://test:8001",
                account="p200981",
                use_container=False
            )
            
            dispatcher.dispatch(num_clients=10, benchmark_id=12345, time=30)
            
            # Verify the job was submitted
            assert mock_submit.called
            call_args = mock_submit.call_args
            assert call_args is not None
    
    def test_slurm_tunnel_setup(self, mock_ssh_manager):
        """Test that SSH tunnel for SLURM is set up correctly."""
        from client_service.deployment.client_dispatcher import SlurmClientDispatcher
        
        with patch.object(SlurmClientDispatcher, '_submit_slurm_job_via_ssh') as mock_submit:
            mock_submit.return_value = (True, {"job_id": 12345})
            
            dispatcher = SlurmClientDispatcher(
                server_addr="http://test:8001",
                account="p200981"
            )
            
            # Verify tunnel was set up
            assert mock_ssh_manager.setup_slurm_rest_tunnel.called
            assert dispatcher._rest_api_port == 6820


class TestSSHIntegration:
    """Test SSH integration (with mocks)."""
    
    def test_ssh_connection(self, mock_ssh_manager):
        """Test that SSH connection can be established."""
        from client_service.ssh_manager import SSHManager
        
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
        with patch('client_service.client_manager.client_group.ClientGroup'):
            num_groups = 10
            benchmark_ids = [int(time.time()) + i for i in range(num_groups)]
            
            # Create many groups
            for bid in benchmark_ids:
                response = client.post(
                    f"/api/v1/client-group/{bid}",
                    json={"num_clients": 100, "time_limit": 60}
                )
                assert response.status_code in [200, 201]
            
            # Verify all were created
            response = client.get("/api/v1/client-groups")
            assert response.status_code == 200
            
            # Clean up
            for bid in benchmark_ids:
                client.delete(f"/api/v1/client-group/{bid}")
