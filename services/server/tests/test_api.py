"""
⚠️ DEPRECATED - This file is being phased out ⚠️

This test file has been split into a better-organized structure:

NEW STRUCTURE (in tests/unit/):
├── test_gateway_api.py       - Public API / Proxy layer tests
├── test_orchestrator_api.py  - Internal Orchestrator API tests  
└── test_orchestrator_core.py - Core business logic tests

USE THE NEW TEST RUNNER:
  ./run_tests.sh              # Run all unit tests
  ./run_tests.sh gateway      # Run only gateway tests
  ./run_tests.sh orch-api     # Run only orchestrator API tests
  ./run_tests.sh orch-core    # Run only core logic tests
  ./run_tests.sh help         # Show usage

WHY THE SPLIT?
1. Gateway tests (test_gateway_api.py): Test the public API's HTTP handling and proxy forwarding
2. Orchestrator API tests (test_orchestrator_api.py): Test the internal API that runs on MeluXina
3. Core Logic tests (test_orchestrator_core.py): Test business logic (SLURM, VllmService, etc.)

This file is kept temporarily for backwards compatibility but should not be modified.
All new tests should go into the appropriate file in tests/unit/.

---

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
from api.routes import get_orchestrator_proxy


class TestAPIEndpoints:
    """
    Test FastAPI endpoints using TestClient.
    
    TestClient creates a fake HTTP client that calls the FastAPI app directly
    without starting an actual server. This tests the route logic, validation,
    and response formatting.
    """
    
    @pytest.fixture
    def mock_server_service(self):
        """Create a mock OrchestratorProxy instance."""
        return Mock()
    
    @pytest.fixture
    def client(self, mock_server_service):
        """Create a test client for the FastAPI app with mocked dependencies."""
        # Override the dependency with our mock
        app.dependency_overrides[get_orchestrator_proxy] = lambda: mock_server_service
        client = TestClient(app)
        yield client
        # Clean up the override after the test
        app.dependency_overrides.clear()
    
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
    
    def test_create_service_endpoint(self, mock_server_service, client):
        """
        Test the service creation endpoint with mocked ServerService.
        """
        # Configure the mock to return expected data
        mock_server_service.start_service.return_value = {
            "id": "12345",
            "name": "test-service",
            "recipe_name": "inference/vllm-single-node",
            "status": "pending",
            "config": {"nodes": 1},
            "created_at": "2025-10-08T10:00:00"
        }
        
        # Make the API call
        response = client.post("/api/v1/services", json={
            "recipe_name": "inference/vllm-single-node"
        })
        
        # Verify the response
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "12345"
        assert data["recipe_name"] == "inference/vllm-single-node"
        
        # Verify the mock was called correctly
        mock_server_service.start_service.assert_called_once()
    
    def test_get_service_endpoint(self, mock_server_service, client):
        """
        Test getting individual service details.
        """
        mock_server_service.get_service.return_value = {
            "id": "test-123",
            "name": "test-service",
            "recipe_name": "inference/vllm-single-node",
            "status": "running",
            "config": {"nodes": 1},
            "created_at": "2025-10-09T10:00:00"
        }
        
        response = client.get("/api/v1/services/test-123")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-123"
        assert data["status"] == "running"
        
        mock_server_service.get_service.assert_called_once_with("test-123")
    
    def test_get_service_not_found(self, mock_server_service, client):
        """
        Test getting a non-existent service returns 404.
        """
        mock_server_service.get_service.return_value = None
        
        response = client.get("/api/v1/services/nonexistent")
        assert response.status_code == 404
        assert "Service not found" in response.json()["detail"]
    
    def test_stop_service_endpoint(self, mock_server_service, client):
        """
        Test stopping a service (DEPRECATED - using DELETE).
        """
        mock_server_service.stop_service.return_value = True
        
        response = client.delete("/api/v1/services/test-123")
        assert response.status_code == 200
        data = response.json()
        assert "stopped successfully" in data["message"]
        
        mock_server_service.stop_service.assert_called_once_with("test-123")
    
    def test_stop_service_not_found(self, mock_server_service, client):
        """
        Test stopping a non-existent service returns 404.
        """
        mock_server_service.stop_service.return_value = False
        
        response = client.delete("/api/v1/services/nonexistent")
        assert response.status_code == 404
        assert "Service not found" in response.json()["detail"]
    
    def test_update_service_status_cancelled(self, mock_server_service, client):
        """
        Test cancelling a service via POST status update (recommended approach).
        """
        mock_server_service.stop_service.return_value = True
        mock_server_service.service_manager.update_service_status.return_value = True
        
        response = client.post(
            "/api/v1/services/test-123/status",
            json={"status": "cancelled"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["service_id"] == "test-123"
        assert data["status"] == "cancelled"
        assert "status updated" in data["message"]
        
        mock_server_service.stop_service.assert_called_once_with("test-123")
        mock_server_service.service_manager.update_service_status.assert_called_once_with("test-123", "cancelled")
    
    def test_update_service_status_invalid(self, mock_server_service, client):
        """
        Test updating service status with invalid value returns 400.
        """
        response = client.post(
            "/api/v1/services/test-123/status",
            json={"status": "invalid_status"}
        )
        assert response.status_code == 400
        assert "Unsupported status value" in response.json()["detail"]
    
    def test_update_service_status_missing_field(self, mock_server_service, client):
        """
        Test updating service status without status field returns 400.
        """
        response = client.post(
            "/api/v1/services/test-123/status",
            json={}
        )
        assert response.status_code == 400
        assert "Missing 'status' field" in response.json()["detail"]
    
    def test_update_service_status_not_found(self, mock_server_service, client):
        """
        Test updating status of non-existent service returns 404.
        """
        mock_server_service.stop_service.return_value = False
        
        response = client.post(
            "/api/v1/services/nonexistent/status",
            json={"status": "cancelled"}
        )
        assert response.status_code == 404
        assert "Service not found" in response.json()["detail"]
    
    def test_get_service_logs_endpoint(self, mock_server_service, client):
        """
        Test getting service logs.
        """
        mock_server_service.get_service_logs.return_value = {
            "logs": "SLURM STDOUT (test-123_123.out):\nService started successfully\n"
        }
        
        response = client.get("/api/v1/services/test-123/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "Service started successfully" in data["logs"]
        
        mock_server_service.get_service_logs.assert_called_once_with("test-123")
    
    def test_get_service_status_endpoint(self, mock_server_service, client):
        """
        Test getting service status.
        """
        mock_server_service.get_service_status.return_value = {"status": "running"}
        
        response = client.get("/api/v1/services/test-123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        
        mock_server_service.get_service_status.assert_called_once_with("test-123")
    
    def test_list_recipes_endpoint(self, mock_server_service, client):
        """
        Test listing all available recipes.
        """
        mock_server_service.list_available_recipes.return_value = [
            {
                "name": "vllm",
                "category": "inference",
                "description": "VLLM inference service",
                "version": "1.0",
                "path": "inference/vllm-single-node"
            },
            {
                "name": "triton",
                "category": "inference", 
                "description": "NVIDIA Triton server",
                "version": "1.0",
                "path": "inference/triton"
            }
        ]
        
        response = client.get("/api/v1/recipes")
        assert response.status_code == 200
        recipes = response.json()
        assert len(recipes) == 2
        assert recipes[0]["name"] == "vllm"
        assert recipes[1]["name"] == "triton"
        
        mock_server_service.list_available_recipes.assert_called_once()
    
    def test_get_recipe_by_path(self, mock_server_service, client):
        """
        Test getting details of a specific recipe by path.
        """
        mock_server_service.list_available_recipes.return_value = [
            {
                "name": "vLLM Inference Service",
                "category": "inference",
                "description": "VLLM inference service",
                "version": "1.0",
                "path": "inference/vllm-single-node"
            }
        ]
        
        response = client.get("/api/v1/recipes?path=inference/vllm-single-node")
        assert response.status_code == 200
        recipe = response.json()
        assert recipe["name"] == "vLLM Inference Service"
        assert recipe["category"] == "inference"
        assert recipe["path"] == "inference/vllm-single-node"
        
        mock_server_service.list_available_recipes.assert_called_once()
    
    def test_get_recipe_by_name(self, mock_server_service, client):
        """
        Test getting details of a specific recipe by name.
        """
        mock_server_service.list_available_recipes.return_value = [
            {
                "name": "vLLM Inference Service",
                "category": "inference",
                "description": "VLLM inference service",
                "version": "1.0",
                "path": "inference/vllm-single-node"
            }
        ]
        
        response = client.get("/api/v1/recipes?name=vLLM%20Inference%20Service")
        assert response.status_code == 200
        recipe = response.json()
        assert recipe["name"] == "vLLM Inference Service"
        
        mock_server_service.list_available_recipes.assert_called_once()
    
    def test_get_recipe_no_params(self, mock_server_service, client):
        """
        Test getting recipes without parameters returns list of all recipes.
        """
        mock_server_service.list_available_recipes.return_value = [
            {
                "name": "vllm",
                "category": "inference",
                "description": "VLLM inference service",
                "version": "1.0",
                "path": "inference/vllm-single-node"
            }
        ]
        
        response = client.get("/api/v1/recipes")
        # This should return the list of all recipes
        assert response.status_code == 200
        recipes = response.json()
        assert isinstance(recipes, list)
        assert len(recipes) == 1
    
    def test_get_recipe_not_found(self, mock_server_service, client):
        """
        Test getting a non-existent recipe returns 404.
        """
        mock_server_service.list_available_recipes.return_value = []
        
        response = client.get("/api/v1/recipes?path=nonexistent")
        assert response.status_code == 404
        assert "Recipe not found" in response.json()["detail"]
    
    def test_list_vllm_services_endpoint(self, mock_server_service, client):
        """
        Test listing VLLM services.
        """
        mock_server_service.find_vllm_services.return_value = [
            {
                "id": "vllm-123",
                "name": "vllm-service",
                "recipe_name": "inference/vllm-single-node",
                "endpoint": "http://node001:8000",
                "status": "running"
            }
        ]
        
        response = client.get("/api/v1/vllm/services")
        assert response.status_code == 200
        data = response.json()
        assert "vllm_services" in data
        assert len(data["vllm_services"]) == 1
        assert data["vllm_services"][0]["id"] == "vllm-123"
        
        mock_server_service.find_vllm_services.assert_called_once()
    
    def test_prompt_vllm_service_endpoint(self, mock_server_service, client):
        """
        Test sending a prompt to a VLLM service.
        """
        mock_server_service.prompt_vllm_service.return_value = {
            "success": True,
            "response": "Hello, this is a test response from VLLM.",
            "service_id": "vllm-123",
            "endpoint": "http://node001:8000",
            "usage": {"prompt_tokens": 5, "completion_tokens": 10}
        }
        
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
        
        mock_server_service.prompt_vllm_service.assert_called_once_with(
            "vllm-123", "Hello, how are you?", max_tokens=50, temperature=0.8
        )
    
    def test_prompt_vllm_service_missing_prompt(self, mock_server_service, client):
        """
        Test VLLM prompting with missing prompt returns 400.
        """
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={})
        assert response.status_code == 400 or response.status_code == 422  # FastAPI validation error
        # Note: FastAPI might return 422 for missing required fields
    
    def test_prompt_vllm_service_backend_error(self, mock_server_service, client):
        """
        Test VLLM prompting with backend error.
        """
        mock_server_service.prompt_vllm_service.side_effect = Exception("VLLM service unavailable")
        
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={
            "prompt": "Test prompt"
        })
        assert response.status_code == 500
        assert "VLLM service unavailable" in response.json()["detail"]
    
    def test_get_vllm_models_endpoint(self, mock_server_service, client):
        """
        Test getting models from a VLLM service.
        """
        mock_server_service.get_vllm_models.return_value = {
            "success": True,
            "models": ["gpt2", "Qwen/Qwen2.5-0.5B-Instruct"],
            "service_id": "test-123",
            "endpoint": "http://compute01:8000"
        }
        
        response = client.get("/api/v1/vllm/test-123/models")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["models"]) == 2
        assert "gpt2" in data["models"]
    
    def test_list_service_groups_endpoint(self, mock_server_service, client):
        """
        Test listing all service groups.
        """
        mock_server_service.list_service_groups.return_value = [
            {
                "id": "sg-test123",
                "type": "replica_group",
                "recipe_name": "inference/vllm-replicas",
                "total_replicas": 4,
                "healthy_replicas": 3,
                "starting_replicas": 1,
                "pending_replicas": 0,
                "failed_replicas": 0,
                "created_at": "2025-11-10T12:00:00"
            }
        ]
        
        response = client.get("/api/v1/service-groups")
        assert response.status_code == 200
        groups = response.json()
        assert len(groups) == 1
        assert groups[0]["id"] == "sg-test123"
        assert groups[0]["total_replicas"] == 4
        assert groups[0]["healthy_replicas"] == 3
        
        mock_server_service.list_service_groups.assert_called_once()
    
    def test_get_service_group_endpoint(self, mock_server_service, client):
        """
        Test getting detailed information about a service group.
        """
        mock_server_service.get_service_group.return_value = {
            "id": "sg-test123",
            "type": "replica_group",
            "replicas": [
                {
                    "id": "1234:8001",
                    "name": "vllm-replicas-1234-replica-0",
                    "status": "running",
                    "port": 8001,
                    "gpu_id": 0
                },
                {
                    "id": "1234:8002",
                    "name": "vllm-replicas-1234-replica-1",
                    "status": "running",
                    "port": 8002,
                    "gpu_id": 1
                }
            ],
            "total_replicas": 2,
            "healthy_replicas": 2,
            "recipe_name": "inference/vllm-replicas"
        }
        
        response = client.get("/api/v1/service-groups/sg-test123")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "sg-test123"
        assert len(data["replicas"]) == 2
        assert data["healthy_replicas"] == 2
        
        mock_server_service.get_service_group.assert_called_once_with("sg-test123")
    
    def test_get_service_group_not_found(self, mock_server_service, client):
        """
        Test getting a non-existent service group returns 404.
        """
        mock_server_service.get_service_group.return_value = None
        
        response = client.get("/api/v1/service-groups/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_stop_service_group_endpoint(self, mock_server_service, client):
        """
        Test stopping a service group and all its replicas.
        """
        mock_server_service.stop_service_group.return_value = {
            "success": True,
            "message": "Service group sg-test123 stopped successfully",
            "group_id": "sg-test123",
            "replicas_stopped": 4
        }
        
        response = client.delete("/api/v1/service-groups/sg-test123")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["replicas_stopped"] == 4
        
        mock_server_service.stop_service_group.assert_called_once_with("sg-test123")
    
    def test_stop_service_group_not_found(self, mock_server_service, client):
        """
        Test stopping a non-existent service group returns 404.
        """
        mock_server_service.stop_service_group.return_value = {
            "success": False,
            "error": "Service group not found"
        }
        
        response = client.delete("/api/v1/service-groups/nonexistent")
        assert response.status_code == 404
    
    def test_get_service_group_status_endpoint(self, mock_server_service, client):
        """
        Test getting aggregated status of a service group.
        """
        mock_server_service.get_service_group_status.return_value = {
            "group_id": "sg-test123",
            "overall_status": "healthy",
            "total_replicas": 4,
            "healthy_replicas": 4,
            "starting_replicas": 0,
            "pending_replicas": 0,
            "failed_replicas": 0,
            "replica_statuses": [
                {"id": "1234:8001", "status": "running"},
                {"id": "1234:8002", "status": "running"},
                {"id": "1234:8003", "status": "running"},
                {"id": "1234:8004", "status": "running"}
            ]
        }
        
        response = client.get("/api/v1/service-groups/sg-test123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "healthy"
        assert data["healthy_replicas"] == 4
        assert len(data["replica_statuses"]) == 4
        
        mock_server_service.get_service_group_status.assert_called_once_with("sg-test123")
    
    def test_prompt_vllm_service_not_ready(self, mock_server_service, client):
        """
        Test prompting a VLLM service that is still starting.
        """
        mock_server_service.prompt_vllm_service.return_value = {
            "success": False,
            "error": "Service is not ready yet (status: starting)",
            "message": "The vLLM service is still starting up. Please wait a moment and try again.",
            "service_id": "vllm-123",
            "status": "starting",
            "endpoint": "http://node001:8000"
        }
        
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={
            "prompt": "Test prompt"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not ready" in data["error"]
        assert "starting up" in data["message"]
        assert data["status"] == "starting"
    
    def test_prompt_vllm_service_connection_refused(self, mock_server_service, client):
        """
        Test prompting a VLLM service with connection refused error.
        """
        mock_server_service.prompt_vllm_service.return_value = {
            "success": False,
            "error": "Service not available",
            "message": "Cannot connect to vLLM service. The service may still be starting up (status: running). Please wait and try again.",
            "service_id": "vllm-123",
            "status": "running",
            "endpoint": "http://node001:8000",
            "technical_details": "Connection refused"
        }
        
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={
            "prompt": "Test prompt"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not available" in data["error"]
        assert "may still be starting" in data["message"]
    
    def test_create_service_with_custom_model(self, mock_server_service, client):
        """
        Test creating a VLLM service with custom model via environment variables.
        """
        mock_server_service.start_service.return_value = {
            "id": "12345",
            "name": "vllm-custom",
            "recipe_name": "inference/vllm-single-node",
            "status": "pending",
            "config": {
                "environment": {
                    "VLLM_MODEL": "gpt2"
                },
                "resources": {
                    "cpu": "8",
                    "memory": "64G",
                    "gpu": "1"
                }
            },
            "created_at": "2025-10-14T10:00:00"
        }
        
        # Create service with custom model and resources
        response = client.post("/api/v1/services", json={
            "recipe_name": "inference/vllm-single-node",
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
        mock_server_service.start_service.assert_called_once()
        call_args = mock_server_service.start_service.call_args
        assert call_args.kwargs["recipe_name"] == "inference/vllm-single-node"
        assert call_args.kwargs["config"]["environment"]["VLLM_MODEL"] == "gpt2"
        assert call_args.kwargs["config"]["resources"]["cpu"] == "8"
    
    def test_get_available_vllm_models_endpoint(self, client):
        """
        Test getting vLLM architecture info and example models.
        """
        response = client.get("/api/v1/vllm/available-models")
        assert response.status_code == 200
        data = response.json()
        
        # Check structure
        assert "model_source" in data
        assert "supported_architectures" in data
        assert "examples" in data
        assert "how_to_find_models" in data
        assert "resource_guidelines" in data
        
        # Check content
        assert "HuggingFace Hub" in data["model_source"]
        assert "text-generation" in data["supported_architectures"]
        assert len(data["supported_architectures"]["text-generation"]) > 0
        assert "LlamaForCausalLM" in data["supported_architectures"]["text-generation"]
        assert "gpt2" in data["examples"].values() or any("gpt2" in str(v) for v in data["examples"].values())
    
    @patch('api.routes.search_hf_models')
    def test_search_vllm_models_endpoint(self, mock_search, client):
        """
        Test searching HuggingFace models compatible with vLLM.
        """
        mock_search.return_value = [
            {
                "id": "Qwen/Qwen2.5-7B-Instruct",
                "downloads": 500000,
                "likes": 1500,
                "architecture": "Qwen2ForCausalLM",
                "vllm_compatible": True,
                "created_at": "2024-09-15T12:00:00",
                "tags": ["text-generation", "qwen2", "instruct"]
            },
            {
                "id": "Qwen/Qwen2.5-3B-Instruct",
                "downloads": 300000,
                "likes": 900,
                "architecture": "Qwen2ForCausalLM",
                "vllm_compatible": True,
                "created_at": "2024-09-15T12:00:00",
                "tags": ["text-generation", "qwen2", "instruct"]
            }
        ]
        
        response = client.get("/api/v1/vllm/search-models?query=qwen&limit=20")
        assert response.status_code == 200
        data = response.json()
        
        assert "models" in data
        assert "total" in data
        assert data["total"] == 2
        assert len(data["models"]) == 2
        assert data["models"][0]["id"] == "Qwen/Qwen2.5-7B-Instruct"
        assert data["models"][0]["vllm_compatible"] is True
        assert data["models"][0]["architecture"] == "Qwen2ForCausalLM"
        
        # Verify the search was called with correct parameters
        mock_search.assert_called_once_with(
            query="qwen",
            architecture=None,
            limit=20,
            sort_by="downloads"
        )
    
    @patch('api.routes.search_hf_models')
    def test_search_vllm_models_with_architecture_filter(self, mock_search, client):
        """
        Test searching models with architecture filter.
        """
        mock_search.return_value = [
            {
                "id": "meta-llama/Llama-2-7b-hf",
                "downloads": 2000000,
                "likes": 5000,
                "architecture": "LlamaForCausalLM",
                "vllm_compatible": True,
                "created_at": "2023-07-18T12:00:00",
                "tags": ["llama", "text-generation"]
            }
        ]
        
        response = client.get("/api/v1/vllm/search-models?architecture=LlamaForCausalLM&limit=10")
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 1
        assert data["models"][0]["architecture"] == "LlamaForCausalLM"
        
        mock_search.assert_called_once_with(
            query=None,
            architecture="LlamaForCausalLM",
            limit=10,
            sort_by="downloads"
        )
    
    @patch('api.routes.search_hf_models')
    def test_search_vllm_models_hf_not_installed(self, mock_search, client):
        """
        Test search endpoint when huggingface_hub is not installed.
        """
        mock_search.side_effect = RuntimeError("huggingface_hub package not installed. Install it with: pip install huggingface-hub")
        
        response = client.get("/api/v1/vllm/search-models?query=test")
        assert response.status_code == 503
        assert "huggingface_hub" in response.json()["detail"]
    
    @patch('api.routes.get_hf_model_info')
    def test_get_vllm_model_info_endpoint(self, mock_get_info, client):
        """
        Test getting detailed info about a specific model.
        """
        mock_get_info.return_value = {
            "id": "Qwen/Qwen2.5-3B-Instruct",
            "architecture": "Qwen2ForCausalLM",
            "vllm_compatible": True,
            "task_type": "text-generation",
            "downloads": 300000,
            "likes": 900,
            "tags": ["text-generation", "qwen2", "instruct"],
            "size_bytes": 6442450944,
            "size_gb": 6.0,
            "pipeline_tag": "text-generation",
            "library_name": "transformers"
        }
        
        response = client.get("/api/v1/vllm/model-info/Qwen/Qwen2.5-3B-Instruct")
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == "Qwen/Qwen2.5-3B-Instruct"
        assert data["architecture"] == "Qwen2ForCausalLM"
        assert data["vllm_compatible"] is True
        assert data["task_type"] == "text-generation"
        assert data["size_gb"] == 6.0
        
        mock_get_info.assert_called_once_with("Qwen/Qwen2.5-3B-Instruct")
    
    @patch('api.routes.get_hf_model_info')
    def test_get_vllm_model_info_not_found(self, mock_get_info, client):
        """
        Test getting info for non-existent model.
        """
        mock_get_info.side_effect = Exception("Model not found")
        
        response = client.get("/api/v1/vllm/model-info/nonexistent/model")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    @patch('api.routes.get_hf_model_info')
    def test_get_vllm_model_info_with_slashes(self, mock_get_info, client):
        """
        Test model info endpoint handles model IDs with slashes correctly.
        """
        mock_get_info.return_value = {
            "id": "meta-llama/Llama-2-7b-chat-hf",
            "architecture": "LlamaForCausalLM",
            "vllm_compatible": True,
            "task_type": "text-generation",
            "downloads": 2000000,
            "likes": 5000,
            "tags": ["llama", "chat", "conversational"],
            "size_bytes": 13476929536,
            "size_gb": 12.56,
            "pipeline_tag": "text-generation",
            "library_name": "transformers"
        }
        
        response = client.get("/api/v1/vllm/model-info/meta-llama/Llama-2-7b-chat-hf")
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == "meta-llama/Llama-2-7b-chat-hf"
        assert data["vllm_compatible"] is True
        
        # Verify the full path with slashes was passed correctly
        mock_get_info.assert_called_once_with("meta-llama/Llama-2-7b-chat-hf")


class TestVLLMServiceLogic:
    """
    Test VLLM-specific service logic including chat template fallback.
    """
    
    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_chat_template_error_detection(self, mock_requests):
        """
        Test that chat template errors are correctly detected.
        """
        from service_orchestration.services.inference import VllmService
        
        # Create VllmService with mocked dependencies
        mock_deployer = Mock()
        mock_service_manager = Mock()
        mock_endpoint_resolver = Mock()
        mock_logger = Mock()
        
        vllm_service = VllmService(mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger)
        is_error = vllm_service._is_chat_template_error(False, 400, {
            "error": {
                "message": "default chat template is no longer allowed",
                "type": "BadRequestError"
            }
        })
        assert is_error is True
        
        # Test with different error
        is_error = vllm_service._is_chat_template_error(False, 400, {
            "error": {
                "message": "Invalid parameters",
                "type": "BadRequestError"
            }
        })
        assert is_error is False
        
        # Test with non-400 status
        is_error = vllm_service._is_chat_template_error(False, 500, {
            "error": {
                "message": "Invalid parameters",
                "type": "BadRequestError"
            }
        })
        assert is_error is False
    
    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_model_discovery_openai_format(self, mock_requests):
        """
        Test model discovery with OpenAI API format (data field).
        """
        from service_orchestration.services.inference import VllmService
        
        # Create VllmService with mocked dependencies
        mock_deployer = Mock()
        mock_deployer.get_job_status.return_value = "running"
        
        # Mock requests response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"object": "list", "data": [{"id": "gpt2", "object": "model", "created": 1234567890}]}
        mock_requests.get.return_value = mock_response
        
        mock_service_manager = Mock()
        mock_service_manager.get_service.return_value = {
            "id": "test-123",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }
        mock_endpoint_resolver = Mock()
        mock_endpoint_resolver.resolve = Mock(return_value="http://test:8001")
        mock_logger = Mock()
        
        vllm_service = VllmService(mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger)
        
        result = vllm_service.get_models("test-123")
        
        # Now returns dict with success and models
        assert result["success"] is True
        assert "gpt2" in result["models"]
        assert len(result["models"]) == 1
    
    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_parse_chat_response_success(self, mock_requests):
        """
        Test parsing successful chat response.
        """
        from service_orchestration.services.inference import VllmService
        
        # Create VllmService with mocked dependencies
        mock_deployer = Mock()
        mock_service_manager = Mock()
        mock_endpoint_resolver = Mock()
        mock_logger = Mock()

        response_body = {
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
        
        vllm_service = VllmService(mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger)
        result = vllm_service._parse_chat_response(True, 200, response_body, "http://test:8001", "test-123")
        
        assert result["success"] is True
        assert result["response"] == "This is a test response"
        assert result["service_id"] == "test-123"
        assert result["endpoint_used"] == "chat"
        assert result["usage"]["prompt_tokens"] == 10
    
    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_parse_completions_response_success(self, mock_requests):
        """
        Test parsing successful completions response.
        """
        from service_orchestration.services.inference import VllmService
        
        # Create VllmService with mocked dependencies
        mock_deployer = Mock()
        mock_service_manager = Mock()
        mock_endpoint_resolver = Mock()
        mock_logger = Mock()

        response_body = {
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
        
        vllm_service = VllmService(mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger)
        result = vllm_service._parse_completions_response(True, 200, response_body, "http://test:8001", "test-123")
        
        assert result["success"] is True
        assert result["response"] == "This is a completion"
        assert result["service_id"] == "test-123"
        assert result["endpoint_used"] == "completions"
        assert result["usage"]["total_tokens"] == 25


class TestServiceWorkflows:
    """
    Test complete service workflows using mocks.
    
    These tests verify that multiple components work together correctly
    when mocked, testing the integration logic without external dependencies.
    """
    
    @pytest.fixture
    def mock_server_service(self):
        """Create a mock OrchestratorProxy instance."""
        return Mock()
    
    @pytest.fixture
    def client(self, mock_server_service):
        """Create a test client for the FastAPI app with mocked dependencies."""
        # Override the dependency with our mock
        app.dependency_overrides[get_orchestrator_proxy] = lambda: mock_server_service
        client = TestClient(app)
        yield client
        # Clean up the override after the test
        app.dependency_overrides.clear()
    
    def test_complete_service_lifecycle(self, mock_server_service, client):
        """
        Test a complete service lifecycle: create -> list -> (cleanup).
        
        This tests the workflow logic:
        1. Service creation returns valid ID
        2. Created service appears in service list
        3. Service data consistency between operations
        """
        # Mock service creation
        mock_server_service.start_service.return_value = {
            "id": "workflow-test-123",
            "name": "workflow-service",
            "recipe_name": "test/recipe",
            "status": "pending",
            "nodes": 1,
            "config": {"nodes": 1},
            "created_at": "2025-10-08T10:00:00"
        }
        
        # Mock service listing (includes our created service)
        mock_server_service.list_services.return_value = [
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
        mock_server_service.start_service.assert_called_once()
        mock_server_service.list_services.assert_called_once()


class TestVllmServiceUnit:
    """
    Unit tests for VllmService methods.
    
    These tests exercise VllmService implementation directly with mocked
    dependencies to catch implementation bugs that high-level API tests miss.
    """
    
    @pytest.fixture
    def mock_deployer(self):
        """Create a mock SlurmDeployer."""
        return Mock()
    
    @pytest.fixture
    def mock_service_manager(self):
        """Create a mock ServiceManager."""
        return Mock()
    
    @pytest.fixture
    def mock_endpoint_resolver(self):
        """Create a mock EndpointResolver."""
        return Mock()
    
    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger."""
        return Mock()
    
    @pytest.fixture
    def vllm_service(self, mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger):
        """Create a VllmService instance with mocked dependencies."""
        from service_orchestration.services.inference import VllmService
        
        service = VllmService(
            deployer=mock_deployer,
            service_manager=mock_service_manager,
            endpoint_resolver=mock_endpoint_resolver,
            logger=mock_logger
        )
        return service
    
    def test_find_services_filters_correctly(self, vllm_service, mock_service_manager, mock_deployer, mock_endpoint_resolver):
        """Test that find_services correctly filters VLLM services."""
        # Mock service_manager.list_services() to return mixed services
        mock_service_manager.list_services.return_value = [
            {"id": "123", "name": "vllm-service", "recipe_name": "inference/vllm-single-node", "status": "running"},
            {"id": "456", "name": "postgres-db", "recipe_name": "database/postgres", "status": "running"},
            {"id": "789", "name": "my-inference", "recipe_name": "inference/vllm-single-node", "status": "running"},
        ]
        
        # Mock the readiness check to return (is_ready, status, model)
        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", "test-model"))
        
        # Mock endpoint resolver
        mock_endpoint_resolver.resolve.side_effect = [
            "http://node1:8000",
            "http://node2:8000"
        ]
        
        # Call find_services
        result = vllm_service.find_services()
        
        # Should only return VLLM services (not postgres)
        assert len(result) == 2
        assert result[0]["id"] == "123"
        assert result[1]["id"] == "789"
        
        # Verify endpoint resolver was called with correct args
        assert mock_endpoint_resolver.resolve.call_count == 2
        mock_endpoint_resolver.resolve.assert_any_call("123", default_port=8001)
        mock_endpoint_resolver.resolve.assert_any_call("789", default_port=8001)
    
    def test_prompt_gets_live_status(self, vllm_service, mock_service_manager, mock_deployer, mock_endpoint_resolver):
        """Test that prompt() fetches live status from deployer, not cached."""
        # Mock service_manager.get_service() to return service with stale status
        mock_service_manager.get_service.return_value = {
            "id": "123",
            "name": "vllm-test",
            "status": "pending",  # Stale cached status
            "recipe_name": "inference/vllm-single-node"
        }

        # Mock is_group to return False (this is a single service, not a group)
        mock_service_manager.is_group.return_value = False
        
        # Mock the check method to return not ready
        vllm_service._check_ready_and_discover_model = Mock(return_value=(False, "starting", None))

        # Don't go through fast path
        mock_service_manager.is_service_recently_healthy.return_value = False
        
        # Mock endpoint resolver
        mock_endpoint_resolver.resolve.return_value = "http://node1:8000"
        
        # Call prompt
        result = vllm_service.prompt("123", "test prompt")
        
        # Should use live status from check
        assert result["success"] is False
        assert "initializing" in result["message"].lower() or "starting" in result["message"].lower()
        assert result["status"] == "starting"
        assert "starting" in result["message"].lower()
    
    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_prompt_uses_correct_endpoint_resolver_method(self, mock_requests, vllm_service, mock_service_manager, mock_deployer, mock_endpoint_resolver, mock_logger):
        """Test that prompt() calls endpoint_resolver.resolve() (not resolve_endpoint())."""
        # Mock service exists and is running
        mock_service_manager.get_service.return_value = {
            "id": "123",
            "name": "vllm-test",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }
        
        # Mock is_group to return False (this is a single service, not a group)
        mock_service_manager.is_group.return_value = False
        
        # Mock the check method to return ready with model
        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", "test-model"))
        
        # Mock endpoint resolver to return valid endpoint
        mock_endpoint_resolver.resolve.return_value = "http://node1:8000"
        
        # Mock requests response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "id": "chat-123", 
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        }
        mock_requests.post.return_value = mock_response
        
        # Mock service health tracking
        mock_service_manager.is_service_recently_healthy.return_value = False
        mock_service_manager.mark_service_healthy.return_value = None
        
        # Call prompt with explicit model to avoid get_models call
        result = vllm_service.prompt("123", "test prompt", model="test-model")
        
        # Verify endpoint_resolver.resolve() was called
        # May be called multiple times (for readiness check and prompt)
        assert mock_endpoint_resolver.resolve.call_count >= 1
        mock_endpoint_resolver.resolve.assert_any_call("123", default_port=8001)
        
        # Should succeed
        assert result["success"] is True, f"Expected success but got: {result}"
    
    def test_prompt_service_not_found(self, vllm_service, mock_service_manager):
        """Test that prompt() handles missing service correctly."""
        # Mock service_manager.get_service() to return None
        mock_service_manager.get_service.return_value = None
        
        # Mock service manager method
        mock_service_manager.is_group.return_value = False
        
        # Call prompt
        result = vllm_service.prompt("nonexistent", "test prompt")
        
        # Should return error dict (not raise exception)
        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()
    
    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_get_models_uses_correct_endpoint(self, mock_requests, vllm_service, mock_service_manager, mock_deployer, mock_endpoint_resolver):
        """Test that get_models() uses the resolved endpoint correctly and returns proper dict format."""
        # Mock service exists and is running
        mock_service_manager.get_service.return_value = {
            "id": "123",
            "name": "vllm-test",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }
        
        # Mock the check method to return ready
        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", None))
        
        # Mock endpoint resolver
        mock_endpoint_resolver.resolve.return_value = "http://node1:8000"
        
        # Mock requests response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"data": [{"id": "model1"}, {"id": "model2"}]}
        mock_requests.get.return_value = mock_response
        
        # Call get_models
        result = vllm_service.get_models("123")
        
        # Should return dict with success and models
        assert result["success"] is True
        assert "models" in result
        assert len(result["models"]) == 2
        assert "model1" in result["models"]
        assert "model2" in result["models"]
        assert result["service_id"] == "123"
        assert result["endpoint"] == "http://node1:8000"
        
        # Verify endpoint was resolved (may be called multiple times due to optimizations)
        assert mock_endpoint_resolver.resolve.call_count >= 1
        mock_endpoint_resolver.resolve.assert_any_call("123", default_port=8001)
        
        # Verify requests was used
        mock_requests.get.assert_called_with(
            "http://node1:8000/v1/models",
            timeout=30
        )

    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_get_models_handles_errors(self, mock_requests, vllm_service, mock_service_manager, mock_deployer, mock_endpoint_resolver):
        """Test that get_models() handles errors gracefully."""
        # Mock service exists and is running
        mock_service_manager.get_service.return_value = {
            "id": "123",
            "name": "vllm-test",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }
        
        # Mock the check method to return ready
        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", None))
        
        # Mock endpoint resolver
        mock_endpoint_resolver.resolve.return_value = "http://node1:8000"
        
        # Mock requests exception
        mock_requests.get.side_effect = Exception("Connection refused")
        
        # Call get_models
        result = vllm_service.get_models("123")
        
        # Should return dict with success=False
        assert result["success"] is False
        assert "error" in result
        assert "Connection refused" in result["error"]
        


# Fixture to create test client once per module
@pytest.fixture(scope="module")
def test_client():
    """Module-level test client fixture."""
    return TestClient(app)


if __name__ == "__main__":
    # Allow running tests directly: python test_api.py
    pytest.main([__file__, "-v"])