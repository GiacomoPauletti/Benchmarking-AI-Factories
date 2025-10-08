"""
Integration test.
"""

import pytest
import os
import requests
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from main import app


def test_basic_workflow():
    """Test basic API workflow with TestClient."""
    client = TestClient(app)
    
    # Test health
    response = client.get("/health")
    assert response.status_code == 200
    
    # Test root
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Factory Server Service" in response.json()["service"]


def test_live_server_workflow():
    """Test workflow against live server if available."""
    # Check if we have a live server endpoint
    endpoint_file = Path("/app/.server-endpoint")
    if not endpoint_file.exists():
        pytest.skip("No live server endpoint available")
    
    endpoint = endpoint_file.read_text().strip()
    
    # Test health
    response = requests.get(f"{endpoint}/health", timeout=10)
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    
    # Test root
    response = requests.get(f"{endpoint}/", timeout=10)
    assert response.status_code == 200
    assert "AI Factory Server Service" in response.json()["service"]
    
    # Test recipes
    response = requests.get(f"{endpoint}/api/v1/recipes", timeout=10)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@patch('api.routes.ServerService')
def test_service_workflow(mock_service_class):
    """Test basic service workflow with mocks."""
    client = TestClient(app)
    
    # Mock service
    mock_service = Mock()
    mock_service.start_service.return_value = {
        "id": "12345",
        "name": "test-service", 
        "recipe_name": "test/recipe",
        "status": "pending",
        "nodes": 1,
        "config": {"nodes": 1},
        "created_at": "2025-10-08T10:00:00"
    }
    mock_service.list_running_services.return_value = [
        {"id": "12345", "name": "test-service", "status": "running"}
    ]
    mock_service_class.return_value = mock_service
    
    # Create service
    response = client.post("/api/v1/services", json={
        "recipe_name": "test/recipe",
        "config": {"nodes": 1}
    })
    assert response.status_code == 200
    
    # List services
    response = client.get("/api/v1/services")
    assert response.status_code == 200
    assert len(response.json()) == 1