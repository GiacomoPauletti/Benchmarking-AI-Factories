import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from service_orchestration.api import create_app

@pytest.fixture
def mock_orchestrator():
    """Create a fully mocked orchestrator for API tests"""
    return MagicMock()

@pytest.fixture
def client(mock_orchestrator):
    """Create a TestClient with the mocked orchestrator"""
    app = create_app(mock_orchestrator)
    return TestClient(app)

class TestOrchestratorAPI:
    
    def test_list_services(self, client, mock_orchestrator):
        """Test list services endpoint"""
        mock_orchestrator.list_services.return_value = {"services": [], "total": 0}
        
        response = client.get("/api/services")
        
        assert response.status_code == 200
        assert response.json() == {"services": [], "total": 0}
        mock_orchestrator.list_services.assert_called_once()

    def test_start_service(self, client, mock_orchestrator):
        """Test start service endpoint"""
        mock_orchestrator.start_service.return_value = {"status": "submitted", "job_id": "123"}
        
        payload = {
            "recipe_name": "test-recipe",
            "config": {"nodes": 1}
        }
        
        response = client.post("/api/services/start", json=payload)
        
        assert response.status_code == 200
        assert response.json()["status"] == "submitted"
        mock_orchestrator.start_service.assert_called_with("test-recipe", {"nodes": 1})

    def test_start_service_missing_recipe(self, client):
        """Test start service with missing recipe"""
        response = client.post("/api/services/start", json={})
        
        assert response.status_code == 400
        assert "recipe_name required" in response.json()["detail"]

    def test_stop_service(self, client, mock_orchestrator):
        """Test stop service endpoint"""
        mock_orchestrator.stop_service.return_value = {"status": "cancelled", "service_id": "123"}
        
        response = client.post("/api/services/stop/123")
        
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        mock_orchestrator.stop_service.assert_called_with("123")

    def test_get_service(self, client, mock_orchestrator):
        """Test get service endpoint"""
        mock_orchestrator.get_service.return_value = {"id": "123", "status": "running"}
        
        response = client.get("/api/services/123")
        
        assert response.status_code == 200
        assert response.json()["id"] == "123"
        mock_orchestrator.get_service.assert_called_with("123")

    def test_get_service_not_found(self, client, mock_orchestrator):
        """Test get service not found"""
        mock_orchestrator.get_service.return_value = None
        
        response = client.get("/api/services/999")
        
        assert response.status_code == 404

    def test_get_service_status(self, client, mock_orchestrator):
        """Test get service status endpoint"""
        mock_orchestrator.get_service_status.return_value = {"status": "running"}
        
        response = client.get("/api/services/123/status")
        
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        mock_orchestrator.get_service_status.assert_called_with("123")
