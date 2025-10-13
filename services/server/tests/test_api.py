"""
Unit Tests for Server

Unit tests test individual components in isolation using mocks and fakes.
They do NOT require external dependencies like SLURM, containers, or network calls.

Test:
1. API endpoint logic (FastAPI routes)
2. SLURM deployer initialization and configuration
3. Service creation workflow (mocked)
4. Error handling and validation
"""

import pytest
import os
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from main import app


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
        """
        Test the health check endpoint.
        
        This tests:
        - Route is accessible at /health
        - Returns 200 status code
        - Returns expected JSON structure
        """
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_root_endpoint(self, client):
        """
        Test the root endpoint.
        
        This tests:
        - Route is accessible at /
        - Returns service information
        - Returns expected JSON structure
        """
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "AI Factory Server Service" in data["service"]
        assert data["status"] == "running"
    
    @patch('api.routes.ServerService')
    def test_create_service_endpoint(self, mock_service_class, client):
        """
        Test the service creation endpoint with mocked ServerService.
        """
        # Create a mock service instance
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
        # When ServerService() is called, return our mock
        mock_service_class.return_value = mock_service
        
        # Make the API call
        response = client.post("/api/v1/services", json={
            "recipe_name": "inference/vllm",
            "config": {"nodes": 1}
        })
        
        # Verify the response
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "12345"
        assert data["recipe_name"] == "inference/vllm"
        
        # Verify the mock was called correctly
        mock_service.start_service.assert_called_once()
    
    @patch('api.routes.ServerService')
    def test_get_service_endpoint(self, mock_service_class, client):
        """
        Test getting individual service details.
        """
        mock_service = Mock()
        mock_service.get_service.return_value = {
            "id": "test-123",
            "name": "test-service",
            "recipe_name": "inference/vllm",
            "status": "running",
            "nodes": 1,
            "config": {"nodes": 1},
            "created_at": "2025-10-09T10:00:00"
        }
        mock_service_class.return_value = mock_service
        
        response = client.get("/api/v1/services/test-123")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-123"
        assert data["status"] == "running"
        
        mock_service.get_service.assert_called_once_with("test-123")
    
    @patch('api.routes.ServerService')
    def test_get_service_not_found(self, mock_service_class, client):
        """
        Test getting a non-existent service returns 404.
        """
        mock_service = Mock()
        mock_service.get_service.return_value = None
        mock_service_class.return_value = mock_service
        
        response = client.get("/api/v1/services/nonexistent")
        assert response.status_code == 404
        assert "Service not found" in response.json()["detail"]
    
    @patch('api.routes.ServerService')
    def test_stop_service_endpoint(self, mock_service_class, client):
        """
        Test stopping a service.
        """
        mock_service = Mock()
        mock_service.stop_service.return_value = True
        mock_service_class.return_value = mock_service
        
        response = client.delete("/api/v1/services/test-123")
        assert response.status_code == 200
        data = response.json()
        assert "stopped successfully" in data["message"]
        
        mock_service.stop_service.assert_called_once_with("test-123")
    
    @patch('api.routes.ServerService')
    def test_stop_service_not_found(self, mock_service_class, client):
        """
        Test stopping a non-existent service returns 404.
        """
        mock_service = Mock()
        mock_service.stop_service.return_value = False
        mock_service_class.return_value = mock_service
        
        response = client.delete("/api/v1/services/nonexistent")
        assert response.status_code == 404
        assert "Service not found" in response.json()["detail"]
    
    @patch('api.routes.ServerService')
    def test_get_service_logs_endpoint(self, mock_service_class, client):
        """
        Test getting service logs.
        """
        mock_service = Mock()
        mock_service.get_service_logs.return_value = "SLURM STDOUT (test-123_123.out):\nService started successfully\n"
        mock_service_class.return_value = mock_service
        
        response = client.get("/api/v1/services/test-123/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "Service started successfully" in data["logs"]
        
        mock_service.get_service_logs.assert_called_once_with("test-123")
    
    @patch('api.routes.ServerService')
    def test_get_service_status_endpoint(self, mock_service_class, client):
        """
        Test getting service status.
        """
        mock_service = Mock()
        mock_service.get_service_status.return_value = "running"
        mock_service_class.return_value = mock_service
        
        response = client.get("/api/v1/services/test-123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        
        mock_service.get_service_status.assert_called_once_with("test-123")
    
    @patch('api.routes.ServerService')
    def test_list_recipes_endpoint(self, mock_service_class, client):
        """
        Test listing all available recipes.
        """
        mock_service = Mock()
        mock_service.list_available_recipes.return_value = [
            {
                "name": "vllm",
                "category": "inference",
                "description": "VLLM inference service",
                "version": "1.0",
                "path": "inference/vllm"
            },
            {
                "name": "triton",
                "category": "inference", 
                "description": "NVIDIA Triton server",
                "version": "1.0",
                "path": "inference/triton"
            }
        ]
        mock_service_class.return_value = mock_service
        
        response = client.get("/api/v1/recipes")
        assert response.status_code == 200
        recipes = response.json()
        assert len(recipes) == 2
        assert recipes[0]["name"] == "vllm"
        assert recipes[1]["name"] == "triton"
        
        mock_service.list_available_recipes.assert_called_once()
    
    @patch('api.routes.ServerService')
    def test_get_recipe_endpoint(self, mock_service_class, client):
        """
        Test getting details of a specific recipe.
        """
        mock_service = Mock()
        mock_service.list_available_recipes.return_value = [
            {
                "name": "vllm",
                "category": "inference",
                "description": "VLLM inference service",
                "version": "1.0",
                "path": "inference/vllm"
            }
        ]
        mock_service_class.return_value = mock_service
        
        response = client.get("/api/v1/recipes/vllm")
        assert response.status_code == 200
        recipe = response.json()
        assert recipe["name"] == "vllm"
        assert recipe["category"] == "inference"
        
        mock_service.list_available_recipes.assert_called_once()
    
    @patch('api.routes.ServerService')
    def test_get_recipe_not_found(self, mock_service_class, client):
        """
        Test getting a non-existent recipe returns 404.
        """
        mock_service = Mock()
        mock_service.list_available_recipes.return_value = []
        mock_service_class.return_value = mock_service
        
        response = client.get("/api/v1/recipes/nonexistent")
        assert response.status_code == 404
        assert "Recipe not found" in response.json()["detail"]
    
    @patch('api.routes.ServerService')
    def test_list_vllm_services_endpoint(self, mock_service_class, client):
        """
        Test listing VLLM services.
        """
        mock_service = Mock()
        mock_service.find_vllm_services.return_value = [
            {
                "id": "vllm-123",
                "name": "vllm-service",
                "recipe_name": "inference/vllm",
                "endpoint": "http://node001:8000",
                "status": "running"
            }
        ]
        mock_service_class.return_value = mock_service
        
        response = client.get("/api/v1/vllm/services")
        assert response.status_code == 200
        data = response.json()
        assert "vllm_services" in data
        assert len(data["vllm_services"]) == 1
        assert data["vllm_services"][0]["id"] == "vllm-123"
        
        mock_service.find_vllm_services.assert_called_once()
    
    @patch('api.routes.ServerService')
    def test_prompt_vllm_service_endpoint(self, mock_service_class, client):
        """
        Test sending a prompt to a VLLM service.
        """
        mock_service = Mock()
        mock_service.prompt_vllm_service.return_value = {
            "success": True,
            "response": "Hello, this is a test response from VLLM.",
            "service_id": "vllm-123",
            "endpoint": "http://node001:8000",
            "usage": {"prompt_tokens": 5, "completion_tokens": 10}
        }
        mock_service_class.return_value = mock_service
        
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={
            "prompt": "Hello, how are you?",
            "max_tokens": 50,
            "temperature": 0.8
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Hello, this is a test response" in data["response"]
        assert data["service_id"] == "vllm-123"
        
        mock_service.prompt_vllm_service.assert_called_once_with(
            "vllm-123", "Hello, how are you?", max_tokens=50, temperature=0.8
        )
    
    def test_prompt_vllm_service_missing_prompt(self, client):
        """
        Test VLLM prompting with missing prompt returns 400.
        """
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={})
        assert response.status_code == 400
        assert "Prompt is required" in response.json()["detail"]
    
    @patch('api.routes.ServerService')
    def test_prompt_vllm_service_backend_error(self, mock_service_class, client):
        """
        Test VLLM prompting with backend error.
        """
        mock_service = Mock()
        mock_service.prompt_vllm_service.side_effect = Exception("VLLM service unavailable")
        mock_service_class.return_value = mock_service
        
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={
            "prompt": "Test prompt"
        })
        assert response.status_code == 500
        assert "VLLM service unavailable" in response.json()["detail"]


class TestSLURMDeployer:
    """
    Test SLURM deployer functionality with mocks.
    
    We test the logic and configuration, not actual SLURM communication.
    """
    
    @patch.dict(os.environ, {'USER': 'testuser', 'SLURM_JWT': 'test_token'})
    def test_deployer_initialization(self):
        """Test that SlurmDeployer initializes correctly."""
        from slurm import SlurmDeployer
        
        deployer = SlurmDeployer()
        assert deployer.username == "testuser"
        assert deployer.token == "test_token"
    
    @patch.dict(os.environ, {'USER': 'testuser', 'SLURM_JWT': 'test_token'})
    def test_job_submission_logic(self):
        """Test that deployer can be initialized and would make HTTP calls."""
        from slurm import SlurmDeployer
        
        deployer = SlurmDeployer()
        
        # Verify deployer is properly configured for HTTP calls
        assert deployer.base_url == "http://slurmrestd.meluxina.lxp.lu:6820/slurm/v0.0.40"
        assert deployer.headers['X-SLURM-USER-NAME'] == 'testuser'
        assert deployer.headers['X-SLURM-USER-TOKEN'] == 'test_token'
        assert 'Content-Type' in deployer.headers
        
        # Test that submit_job would fail appropriately without a recipe file
        try:
            deployer.submit_job("test/recipe", {"nodes": 1})
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            # Expected - this verifies the method attempts to find the recipe file
            pass
    
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_environment_variables(self):
        """Test error handling when SLURM_JWT is missing."""
        from slurm import SlurmDeployer
        
        with pytest.raises(RuntimeError, match="SLURM_JWT"):
            SlurmDeployer()


class TestServiceWorkflows:
    """
    Test complete service workflows using mocks.
    
    These tests verify that multiple components work together correctly
    when mocked, testing the integration logic without external dependencies.
    """
    
    @patch('api.routes.ServerService')
    def test_complete_service_lifecycle(self, mock_service_class, client=None):
        """
        Test a complete service lifecycle: create -> list -> (cleanup).
        
        This tests the workflow logic:
        1. Service creation returns valid ID
        2. Created service appears in service list
        3. Service data consistency between operations
        """
        if client is None:
            client = TestClient(app)
        
        mock_service = Mock()
        
        # Mock service creation
        mock_service.start_service.return_value = {
            "id": "workflow-test-123",
            "name": "workflow-service",
            "recipe_name": "test/recipe",
            "status": "pending",
            "nodes": 1,
            "config": {"nodes": 1},
            "created_at": "2025-10-08T10:00:00"
        }
        
        # Mock service listing (includes our created service)
        mock_service.list_running_services.return_value = [
            {
                "id": "workflow-test-123",
                "name": "workflow-service",
                "recipe_name": "test/recipe",
                "status": "running",  # Status changed to running
                "nodes": 1,
                "config": {"nodes": 1},
                "created_at": "2025-10-08T10:00:00"
            }
        ]
        
        mock_service_class.return_value = mock_service
        
        # Step 1: Create service
        create_response = client.post("/api/v1/services", json={
            "recipe_name": "test/recipe",
            "config": {"nodes": 1}
        })
        assert create_response.status_code == 200
        service_data = create_response.json()
        service_id = service_data["id"]
        
        # Step 2: List services and verify our service is there
        list_response = client.get("/api/v1/services")
        assert list_response.status_code == 200
        services = list_response.json()
        
        # Find our service in the list
        our_service = next((s for s in services if s["id"] == service_id), None)
        assert our_service is not None
        assert our_service["name"] == "workflow-service"
        
        # Verify both methods were called
        mock_service.start_service.assert_called_once()
        mock_service.list_running_services.assert_called_once()


# Fixture to create test client once per module
@pytest.fixture(scope="module")
def test_client():
    """Module-level test client fixture."""
    return TestClient(app)


if __name__ == "__main__":
    # Allow running tests directly: python test_api.py
    pytest.main([__file__, "-v"])