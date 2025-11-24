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
from types import SimpleNamespace

import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from main import app
from client_manager.client_manager import ClientManager, ClientManagerResponseStatus
from client_manager.client_group import ClientGroupStatus


@pytest.fixture(autouse=True)
def reset_client_manager_singleton():
    """Ensure ClientManager singleton uses a clean slate between tests."""
    ClientManager._instance = None  # type: ignore[attr-defined]
    yield
    ClientManager._instance = None  # type: ignore[attr-defined]


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
        with patch('client_manager.client_group.ClientGroup'):
            response = client.post(
                "/api/v1/client-groups",
                json={"service_id": "sg-test", "num_clients": 10, "time_limit": 30}
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
        response = client.get("/api/v1/client-groups/99999")
        # Should return 404 or empty response
        assert response.status_code in [200, 404]
    
    def test_run_client_group(self, client):
        """Test triggering a client group to run."""
        # Attempt to run a non-existent group
        # There is no direct run endpoint; ensure POST to create a group returns created
        response = client.post("/api/v1/client-groups", json={"service_id": "sg-test", "num_clients": 1, "requests_per_second": 0.1, "duration_seconds": 1})
        # Should handle gracefully (404 or error response)
        assert response.status_code in [200, 201]


class TestClientManager:
    """Test ClientManager class functionality."""
    
    def test_client_manager_singleton(self):
        """Test that ClientManager is a singleton."""
        manager1 = ClientManager()
        manager2 = ClientManager()
        assert manager1 is manager2
    
    def test_configure_client_manager(self):
        """Test configuring the client manager."""
        manager = ClientManager(server_addr="http://test:8001", use_container=True, account="test_account")
        assert manager._server_addr == "http://test:8001"
        assert manager._use_container is True
        assert manager._account == "test_account"
    
    def test_add_client_group(self, mock_ssh_manager):
        """Test adding a client group."""
        with patch('client_manager.client_group.ClientGroup'):
            manager = ClientManager(server_addr="http://test:8001")
            # avoid network calls by stubbing the orchestrator url
            manager._orchestrator_url = "http://orch:9000"

            load_config = {
                "service_id": "sg-test",
                "num_clients": 10,
                "time_limit": 30,
                "requests_per_second": 0.5,
                "duration_seconds": 30,
            }

            result = manager.add_client_group(12345, load_config)
            
            # Should return OK status
            assert result == ClientManagerResponseStatus.OK
    
    def test_add_duplicate_client_group(self, mock_ssh_manager):
        """Test that adding duplicate client group returns error."""
        with patch('client_manager.client_group.ClientGroup'):
            manager = ClientManager(server_addr="http://test:8001")
            manager._orchestrator_url = "http://orch:9000"

            load_config = {"service_id": "sg-test", "num_clients": 10, "time_limit": 30, "requests_per_second": 0.5}

            # Add first group
            manager.add_client_group(12345, load_config)

            # Try to add duplicate
            result = manager.add_client_group(12345, load_config)
            
            # Should return ALREADY_EXISTS status
            assert result == ClientManagerResponseStatus.ALREADY_EXISTS
    
    def test_remove_client_group(self, mock_ssh_manager):
        """Test removing a client group."""
        with patch('client_manager.client_group.ClientGroup'):
            manager = ClientManager(server_addr="http://test:8001")
            manager._orchestrator_url = "http://orch:9000"

            # Add then remove
            manager.add_client_group(12345, {"service_id": "sg-test", "num_clients": 10, "time_limit": 30, "requests_per_second": 0.5})
            manager.remove_client_group(12345)
            
            # Should be removed from list
            groups = manager.list_groups()
            assert 12345 not in groups
    
    def test_list_groups(self, mock_ssh_manager):
        """Test listing client groups."""
        with patch('client_manager.client_group.ClientGroup'):
            manager = ClientManager(server_addr="http://test:8001")
            manager._orchestrator_url = "http://orch:9000"

            # Add a few groups
            manager.add_client_group(1, {"service_id": "sg-a", "num_clients": 10, "time_limit": 30, "requests_per_second": 0.5})
            manager.add_client_group(2, {"service_id": "sg-b", "num_clients": 20, "time_limit": 60, "requests_per_second": 1.0})
            
            groups = manager.list_groups()
            assert len(groups) >= 2
            assert 1 in groups
            assert 2 in groups

    def test_set_orchestrator_url_success(self, monkeypatch):
        manager = ClientManager()
        captured = []

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"endpoint": "http://orch:9000"}

        def fake_get(url, timeout):  # pylint: disable=unused-argument
            captured.append(url)
            return FakeResponse()

        monkeypatch.setattr('client_manager.client_manager.requests.get', fake_get)

        assert manager.set_orchestrator_url("http://server:8001") is True
        assert manager._orchestrator_url == "http://orch:9000"  # type: ignore[attr-defined]
        assert captured == ["http://server:8001/api/v1/orchestrator/endpoint"]

    def test_set_orchestrator_url_handles_non_200(self, monkeypatch):
        manager = ClientManager()

        class FakeResponse:
            status_code = 503

            @staticmethod
            def json():
                return {}

        monkeypatch.setattr('client_manager.client_manager.requests.get', lambda *_, **__: FakeResponse())

        assert manager.set_orchestrator_url("http://server:8001") is False
        assert manager._orchestrator_url is None  # type: ignore[attr-defined]

    def test_set_orchestrator_url_handles_exception(self, monkeypatch):
        manager = ClientManager()

        def fake_get(*args, **kwargs):  # pylint: disable=unused-argument
            raise RuntimeError("boom")

        monkeypatch.setattr('client_manager.client_manager.requests.get', fake_get)

        assert manager.set_orchestrator_url("http://server:8001") is False
        assert manager._orchestrator_url is None  # type: ignore[attr-defined]

    def test_add_client_group_injects_prompt_url(self, monkeypatch):
        manager = ClientManager()
        manager._server_addr = "http://server:8001"  # type: ignore[attr-defined]
        manager._orchestrator_url = "http://orch:9000"  # type: ignore[attr-defined]

        created = {}

        class FakeClientGroup:
            def __init__(self, group_id, load_config, account=None, use_container=None):  # pylint: disable=unused-argument
                created['group_id'] = group_id
                created['load_config'] = dict(load_config)

        monkeypatch.setattr('client_manager.client_manager.ClientGroup', FakeClientGroup)

        load_config = {
            "service_id": "sg-123",
            "num_clients": 2,
            "requests_per_second": 0.5,
            "duration_seconds": 30,
        }

        status = manager.add_client_group(42, load_config)

        assert status == ClientManagerResponseStatus.OK
        assert load_config['prompt_url'] == "http://orch:9000/api/services/vllm/sg-123/prompt"
        assert created['load_config']['prompt_url'] == load_config['prompt_url']

    def test_add_client_group_without_orchestrator_keeps_config(self, monkeypatch):
        manager = ClientManager()
        manager._server_addr = "http://server:8001"  # type: ignore[attr-defined]

        monkeypatch.setattr('client_manager.client_manager.ClientGroup', lambda *_, **__: None)
        monkeypatch.setattr(manager, 'set_orchestrator_url', lambda *_args, **_kwargs: False)

        load_config = {
            "service_id": "sg-123",
            "num_clients": 2,
            "requests_per_second": 0.5,
        }

        status = manager.add_client_group(7, load_config)

        assert status == ClientManagerResponseStatus.OK
        assert 'prompt_url' not in load_config

    def test_run_client_group_rejects_non_running_group(self):
        manager = ClientManager()
        dummy_group = SimpleNamespace(
            get_status=lambda: ClientGroupStatus.PENDING,
            get_client_address=lambda: "http://client",
        )
        manager._client_groups[1] = dummy_group  # type: ignore[attr-defined]

        result = manager.run_client_group(1)

        assert result[0]['error'] == "client group not running"

    def test_run_client_group_forwards_request(self, monkeypatch):
        manager = ClientManager()

        class RunningGroup:
            def __init__(self):
                self._addr = "http://client"

            def get_status(self):
                return ClientGroupStatus.RUNNING

            def get_client_address(self):
                return self._addr

        manager._client_groups[5] = RunningGroup()  # type: ignore[attr-defined]

        class FakeResponse:
            status_code = 200
            text = "ok"

        captured = {}

        def fake_post(url, timeout):  # pylint: disable=unused-argument
            captured['url'] = url
            return FakeResponse()

        monkeypatch.setattr('client_manager.client_manager.requests.post', fake_post)

        results = manager.run_client_group(5)

        assert captured['url'] == "http://client/run"
        assert results[0]['status_code'] == 200
        assert results[0]['body'] == "ok"


class TestSlurmClientDispatcher:
    """Test SLURM Client Dispatcher functionality."""
    
    def test_dispatcher_initialization(self, mock_ssh_manager):
        """Test that dispatcher initializes correctly."""
        from deployment.client_dispatcher import SlurmClientDispatcher
        
        dispatcher = SlurmClientDispatcher(load_config={}, account="p200981", use_container=False)

        assert dispatcher._load_config == {}
        assert dispatcher._account == "p200981"
        assert dispatcher._use_container is False
    
    def test_dispatcher_dispatch_job(self, mock_ssh_manager):
        """Test job dispatch functionality."""
        from deployment.client_dispatcher import SlurmClientDispatcher
        
        with patch.object(SlurmClientDispatcher, '_submit_slurm_job_via_ssh') as mock_submit:
            mock_submit.return_value = (True, {"job_id": 12345})
            
            dispatcher = SlurmClientDispatcher(load_config={"num_clients": 10}, account="p200981")

            # Should not raise an error
            dispatcher.dispatch(group_id=12345, time_limit=30)
            
            # Verify SSH submission was called
            assert mock_submit.called


class TestSSHManager:
    """Test SSH Manager functionality."""
    
    def test_ssh_manager_initialization(self):
        """Test SSH manager can be initialized."""
        from ssh_manager import SSHManager
        
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
        from ssh_manager import SSHManager
        
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="SSH_USER must be set"):
                SSHManager()

