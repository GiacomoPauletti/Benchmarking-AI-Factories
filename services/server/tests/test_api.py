"""
Unit tests for API routes.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from main import app


class TestAPI:
    """API tests."""
    
    @pytest.fixture
    def client(self):
        """Test client."""
        return TestClient(app)
    
    def test_health_endpoint(self, client):
        """Test health check."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "AI Factory Server Service" in data["service"]
        assert data["status"] == "running"
    
    @patch('api.routes.ServerService')
    def test_create_service(self, mock_service_class, client):
        """Test service creation."""
        mock_service = Mock()
        mock_service.start_service.return_value = {
            "id": "12345",
            "name": "test-service",
            "recipe_name": "inference/vllm",
            "status": "pending",
            "nodes": 1,
            "config": {"nodes": 1},
            "created_at": "2025-10-08T10:00:00"
        }
        mock_service_class.return_value = mock_service
        
        response = client.post("/api/v1/services", json={
            "recipe_name": "inference/vllm",
            "config": {"nodes": 1}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "12345"
        assert data["recipe_name"] == "inference/vllm"
    
    @patch('api.routes.ServerService')
    def test_list_services(self, mock_service_class, client):
        """Test service listing."""
        mock_service = Mock()
        mock_service.list_running_services.return_value = [
            {"id": "12345", "name": "test-service", "status": "running"}
        ]
        mock_service_class.return_value = mock_service
        
        response = client.get("/api/v1/services")
        assert response.status_code == 200
        assert len(response.json()) == 1