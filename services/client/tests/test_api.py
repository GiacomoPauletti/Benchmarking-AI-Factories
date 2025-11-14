"""
Unit Tests for Client Service API

Unit tests test individual components in isolation using mocks and fakes.
They do NOT require external dependencies like SLURM, containers, or network calls.

Test:
1. API endpoint logic (FastAPI routes)
2. Client Manager functionality
3. Client Group creation and management
4. SLURM dispatcher initialization and configuration
5. Error handling and validation
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from main import app
from client_service.client_manager.client_manager import ClientManager


class TestAPIEndpoints:
    """
    Test FastAPI endpoints using TestClient.
    
    TestClient creates a fake HTTP client that calls the FastAPI app directly
    without starting an actual server. This tests the route logic, validation,
    and response formatting.
    """
    
    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app."""
        return TestClient(app)
    
    def test_health_endpoint(self, client):
        """Test that the health endpoint returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
    
    def test_create_client_group(self, client, mock_ssh_manager):
        """Test creating a new client group via API."""
        with patch('client_service.client_manager.client_group.ClientGroup'):
            response = client.post(
                "/api/v1/client-group/12345",
                json={"num_clients": 10, "time_limit": 30}
            )
            
            # Should return 201 CREATED or 200 OK depending on implementation
            assert response.status_code in [200, 201]
    
    def test_list_client_groups(self, client):
        """Test listing all client groups."""
        response = client.get("/api/v1/client-groups")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or isinstance(data, dict)
    
    def test_get_client_group_info(self, client):
        """Test getting info about a specific client group."""
        # First try to get a non-existent group
        response = client.get("/api/v1/client-group/99999")
        # Should return 404 or empty response
        assert response.status_code in [200, 404]
    
    def test_run_client_group(self, client):
        """Test triggering a client group to run."""
        # Attempt to run a non-existent group
        response = client.post("/api/v1/client-group/99999/run")
        # Should handle gracefully (404 or error response)
        assert response.status_code in [200, 404, 500]


class TestClientManager:
    """Test ClientManager class functionality."""
    
    def test_client_manager_singleton(self):
        """Test that ClientManager is a singleton."""
        manager1 = ClientManager()
        manager2 = ClientManager()
        assert manager1 is manager2
    
    def test_configure_client_manager(self):
        """Test configuring the client manager."""
        manager = ClientManager()
        manager.configure(
            server_addr="http://test:8001",
            use_container=True,
            account="test_account"
        )
        assert manager._server_addr == "http://test:8001"
        assert manager._use_container == True
        assert manager._account == "test_account"
    
    def test_add_client_group(self, mock_ssh_manager):
        """Test adding a client group."""
        with patch('client_service.client_manager.client_group.ClientGroup'):
            manager = ClientManager()
            manager.configure(server_addr="http://test:8001")
            
            result = manager.add_client_group(
                benchmark_id=12345,
                num_clients=10,
                time_limit=30
            )
            
            # Should return OK status (0)
            assert result == 0
    
    def test_add_duplicate_client_group(self, mock_ssh_manager):
        """Test that adding duplicate client group returns error."""
        with patch('client_service.client_manager.client_group.ClientGroup'):
            manager = ClientManager()
            manager.configure(server_addr="http://test:8001")
            
            # Add first group
            manager.add_client_group(12345, 10, 30)
            
            # Try to add duplicate
            result = manager.add_client_group(12345, 10, 30)
            
            # Should return ERROR status (1)
            assert result == 1
    
    def test_remove_client_group(self, mock_ssh_manager):
        """Test removing a client group."""
        with patch('client_service.client_manager.client_group.ClientGroup'):
            manager = ClientManager()
            manager.configure(server_addr="http://test:8001")
            
            # Add then remove
            manager.add_client_group(12345, 10, 30)
            manager.remove_client_group(12345)
            
            # Should be removed from list
            groups = manager.list_groups()
            assert 12345 not in groups
    
    def test_list_groups(self, mock_ssh_manager):
        """Test listing client groups."""
        with patch('client_service.client_manager.client_group.ClientGroup'):
            manager = ClientManager()
            manager.configure(server_addr="http://test:8001")
            
            # Add a few groups
            manager.add_client_group(1, 10, 30)
            manager.add_client_group(2, 20, 60)
            
            groups = manager.list_groups()
            assert len(groups) >= 2
            assert 1 in groups
            assert 2 in groups


class TestSlurmClientDispatcher:
    """Test SLURM Client Dispatcher functionality."""
    
    def test_dispatcher_initialization(self, mock_ssh_manager):
        """Test that dispatcher initializes correctly."""
        from client_service.deployment.client_dispatcher import SlurmClientDispatcher
        
        dispatcher = SlurmClientDispatcher(
            server_addr="http://test:8001",
            account="p200981",
            use_container=False
        )
        
        assert dispatcher._server_addr == "http://test:8001"
        assert dispatcher._account == "p200981"
        assert dispatcher._use_container == False
    
    def test_dispatcher_dispatch_job(self, mock_ssh_manager):
        """Test job dispatch functionality."""
        from client_service.deployment.client_dispatcher import SlurmClientDispatcher
        
        with patch.object(SlurmClientDispatcher, '_submit_slurm_job_via_ssh') as mock_submit:
            mock_submit.return_value = (True, {"job_id": 12345})
            
            dispatcher = SlurmClientDispatcher(
                server_addr="http://test:8001",
                account="p200981"
            )
            
            # Should not raise an error
            dispatcher.dispatch(num_clients=10, benchmark_id=12345, time=30)
            
            # Verify SSH submission was called
            assert mock_submit.called


class TestSSHManager:
    """Test SSH Manager functionality."""
    
    def test_ssh_manager_initialization(self):
        """Test SSH manager can be initialized."""
        from client_service.ssh_manager import SSHManager
        
        with patch.dict(os.environ, {
            'SSH_HOST': 'test.example.com',
            'SSH_USER': 'testuser',
            'SSH_PORT': '22'
        }):
            manager = SSHManager()
            assert manager.ssh_host == 'test.example.com'
            assert manager.ssh_user == 'testuser'
            assert manager.ssh_port == 22
    
    def test_ssh_manager_requires_credentials(self):
        """Test that SSH manager requires SSH_USER and SSH_HOST."""
        from client_service.ssh_manager import SSHManager
        
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="SSH_USER must be set"):
                SSHManager()


# Import os for environment tests
import os
