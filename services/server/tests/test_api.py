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
    
    @patch('api.routes.ServerService')
    def test_prompt_vllm_service_missing_prompt(self, mock_service_class, client):
        """
        Test VLLM prompting with missing prompt returns 400.
        """
        # Even though we don't use the service for validation errors,
        # we need to mock it so the endpoint doesn't fail during initialization
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={})
        assert response.status_code == 400 or response.status_code == 422  # FastAPI validation error
        # Note: FastAPI might return 422 for missing required fields
    
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
    
    @patch('api.routes.ServerService')
    def test_get_vllm_models_endpoint(self, mock_service_class, client):
        """
        Test getting available models from a VLLM service.
        """
        mock_service = Mock()
        mock_service.get_vllm_models.return_value = ["gpt2", "Qwen/Qwen2.5-0.5B-Instruct"]
        mock_service_class.return_value = mock_service
        
        response = client.get("/api/v1/vllm/vllm-123/models")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert len(data["models"]) == 2
        assert "gpt2" in data["models"]
        assert "Qwen/Qwen2.5-0.5B-Instruct" in data["models"]
        
        mock_service.get_vllm_models.assert_called_once_with("vllm-123")
    
    @patch('api.routes.ServerService')
    def test_prompt_vllm_service_not_ready(self, mock_service_class, client):
        """
        Test prompting a VLLM service that is still starting.
        """
        mock_service = Mock()
        mock_service.prompt_vllm_service.return_value = {
            "success": False,
            "error": "Service is not ready yet (status: starting)",
            "message": "The vLLM service is still starting up. Please wait a moment and try again.",
            "service_id": "vllm-123",
            "status": "starting",
            "endpoint": "http://node001:8000"
        }
        mock_service_class.return_value = mock_service
        
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={
            "prompt": "Test prompt"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not ready" in data["error"]
        assert "starting up" in data["message"]
        assert data["status"] == "starting"
    
    @patch('api.routes.ServerService')
    def test_prompt_vllm_service_connection_refused(self, mock_service_class, client):
        """
        Test prompting a VLLM service with connection refused error.
        """
        mock_service = Mock()
        mock_service.prompt_vllm_service.return_value = {
            "success": False,
            "error": "Service not available",
            "message": "Cannot connect to vLLM service. The service may still be starting up (status: running). Please wait and try again.",
            "service_id": "vllm-123",
            "status": "running",
            "endpoint": "http://node001:8000",
            "technical_details": "Connection refused"
        }
        mock_service_class.return_value = mock_service
        
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={
            "prompt": "Test prompt"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not available" in data["error"]
        assert "may still be starting" in data["message"]
    
    @patch('api.routes.ServerService')
    def test_create_service_with_custom_model(self, mock_service_class, client):
        """
        Test creating a VLLM service with custom model via environment variables.
        """
        mock_service = Mock()
        mock_service.start_service.return_value = {
            "id": "12345",
            "name": "vllm-custom",
            "recipe_name": "inference/vllm",
            "status": "pending",
            "config": {
                "environment": {
                    "VLLM_MODEL": "gpt2"
                },
                "resources": {
                    "nodes": 1,
                    "cpu": "8",
                    "memory": "64G",
                    "gpu": "1"
                }
            },
            "created_at": "2025-10-14T10:00:00"
        }
        mock_service_class.return_value = mock_service
        
        # Create service with custom model and resources
        response = client.post("/api/v1/services", json={
            "recipe_name": "inference/vllm",
            "config": {
                "environment": {
                    "VLLM_MODEL": "gpt2"
                },
                "resources": {
                    "nodes": 1,
                    "cpu": "8",
                    "memory": "64G",
                    "gpu": "1"
                }
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "12345"
        assert data["config"]["environment"]["VLLM_MODEL"] == "gpt2"
        assert data["config"]["resources"]["cpu"] == "8"
        
        # Verify the mock was called with the right config (using keyword arguments)
        mock_service.start_service.assert_called_once()
        call_args = mock_service.start_service.call_args
        assert call_args.kwargs["recipe_name"] == "inference/vllm"
        assert call_args.kwargs["config"]["environment"]["VLLM_MODEL"] == "gpt2"
        assert call_args.kwargs["config"]["resources"]["cpu"] == "8"


class TestVLLMServiceLogic:
    """
    Test VLLM-specific service logic including chat template fallback.
    """
    
    @patch('server_service.requests')
    def test_chat_template_error_detection(self, mock_requests):
        """
        Test that chat template errors are correctly detected.
        """
        from server_service import ServerService
        
        # Mock response with chat template error
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {
                "message": "default chat template is no longer allowed",
                "type": "BadRequestError"
            }
        }
        
        # Patch both SSHManager and SlurmDeployer during ServerService creation
        with patch('server_service.SlurmDeployer') as mock_deployer:
            mock_deployer.return_value = Mock()
            service = ServerService()
            is_error = service._is_chat_template_error(mock_response)
            assert is_error is True
        
        # Test with different error
        mock_response.json.return_value = {
            "error": {
                "message": "Invalid parameters",
                "type": "BadRequestError"
            }
        }
        with patch('server_service.SlurmDeployer') as mock_deployer:
            mock_deployer.return_value = Mock()
            service = ServerService()
            is_error = service._is_chat_template_error(mock_response)
            assert is_error is False
        
        # Test with non-400 status
        mock_response.status_code = 500
        with patch('server_service.SlurmDeployer') as mock_deployer:
            mock_deployer.return_value = Mock()
            service = ServerService()
            is_error = service._is_chat_template_error(mock_response)
            assert is_error is False
    
    @patch('server_service.requests')
    def test_model_discovery_openai_format(self, mock_requests):
        """
        Test model discovery with OpenAI API format (data field).
        """
        from server_service import ServerService
        
        # Mock the endpoint discovery
        mock_service_instance = Mock()
        mock_service_instance._get_vllm_endpoint = Mock(return_value="http://test:8001")
        
        # Mock the requests.get call
        mock_response = Mock()
        mock_response.ok = True
        mock_response.text = '{"object": "list", "data": [{"id": "gpt2", "object": "model"}]}'
        mock_response.json.return_value = {
            "object": "list",
            "data": [
                {"id": "gpt2", "object": "model", "created": 1234567890}
            ]
        }
        mock_requests.get.return_value = mock_response
        
        with patch('server_service.SlurmDeployer') as mock_deployer:
            mock_deployer.return_value = Mock()
            service = ServerService()
            service._get_vllm_endpoint = Mock(return_value="http://test:8001")
            
            models = service.get_vllm_models("test-123")
            
            assert "gpt2" in models
            assert len(models) == 1
    
    @patch('server_service.requests')
    def test_parse_chat_response_success(self, mock_requests):
        """
        Test parsing successful chat response.
        """
        from server_service import ServerService
        
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "This is a test response"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
        
        with patch('server_service.SlurmDeployer') as mock_deployer:
            mock_deployer.return_value = Mock()
            service = ServerService()
            result = service._parse_chat_response(mock_response, "http://test:8001", "test-123")
            
            assert result["success"] is True
            assert result["response"] == "This is a test response"
            assert result["service_id"] == "test-123"
            assert result["endpoint_used"] == "chat"
            assert result["usage"]["prompt_tokens"] == 10
    
    @patch('server_service.requests')
    def test_parse_completions_response_success(self, mock_requests):
        """
        Test parsing successful completions response.
        """
        from server_service import ServerService
        
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [
                {
                    "text": "This is a completion",
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 15,
                "total_tokens": 25
            }
        }
        
        with patch('server_service.SlurmDeployer') as mock_deployer:
            mock_deployer.return_value = Mock()
            service = ServerService()
            result = service._parse_completions_response(mock_response, "http://test:8001", "test-123")
            
            assert result["success"] is True
            assert result["response"] == "This is a completion"
            assert result["service_id"] == "test-123"
            assert result["endpoint_used"] == "completions"
            assert result["usage"]["total_tokens"] == 25


class TestSLURMDeployer:
    """
    Test SLURM deployer functionality with mocks.
    
    We test the logic and configuration, not actual SLURM communication.
    """
    
    @patch.dict(os.environ, {'SLURM_JWT': 'test_token'})
    @patch('slurm.SSHManager')
    def test_deployer_initialization(self, mock_ssh):
        """Test that SlurmDeployer initializes correctly."""
        from slurm import SlurmDeployer
        
        # Mock SSH Manager
        mock_ssh_instance = Mock()
        mock_ssh_instance.setup_slurm_rest_tunnel.return_value = 6820
        mock_ssh.return_value = mock_ssh_instance
        
        deployer = SlurmDeployer()
        assert deployer.token == "test_token"
        assert deployer.rest_api_port == 6820
    
    @patch.dict(os.environ, {'SLURM_JWT': 'test_token'})
    @patch('slurm.SSHManager')
    def test_job_submission_logic(self, mock_ssh):
        """Test that deployer can be initialized and would make HTTP calls."""
        from slurm import SlurmDeployer
        
        # Mock SSH Manager
        mock_ssh_instance = Mock()
        mock_ssh_instance.setup_slurm_rest_tunnel.return_value = 6820
        mock_ssh.return_value = mock_ssh_instance
        
        deployer = SlurmDeployer()
        
        # Verify deployer is properly configured for HTTP calls
        assert deployer.base_url == f"http://localhost:6820/slurm/v0.0.40"
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
    @patch('slurm.SSHManager')
    def test_missing_environment_variables(self, mock_ssh):
        """Test error handling when required env vars are missing."""
        from slurm import SlurmDeployer
        
        # Mock SSH Manager to fail with proper error
        mock_ssh.side_effect = ValueError("SSH_USER must be set. Check your .env.local file.")
        
        # Test should raise error when environment variables are missing
        with pytest.raises(ValueError, match="SSH_USER must be set"):
            SlurmDeployer()


class TestServiceWorkflows:
    """
    Test complete service workflows using mocks.
    
    These tests verify that multiple components work together correctly
    when mocked, testing the integration logic without external dependencies.
    """
    
    @patch('server_service.SlurmDeployer')
    @patch('api.routes.ServerService')
    def test_complete_service_lifecycle(self, mock_service_class, mock_deployer, client=None):
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