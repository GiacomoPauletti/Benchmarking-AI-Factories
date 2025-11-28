"""
Gateway API Tests (Public API / Proxy Layer)

These tests verify that the public-facing Server API correctly:
1. Receives HTTP requests
2. Validates input
3. Forwards to OrchestratorProxy
4. Returns proper responses

Mock: OrchestratorProxy
Do NOT test business logic here - only HTTP <-> Proxy translation.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi import status, HTTPException

from main import app
from api.routes import get_orchestrator_proxy


class TestGatewayAPI:
    """
    Test Public API (Gateway Layer).
    
    Responsibility: HTTP Request → Validate → Call Proxy → HTTP Response
    """
    
    @pytest.fixture
    def mock_proxy(self):
        """Create a mock OrchestratorProxy instance."""
        return Mock()
    
    @pytest.fixture
    def client(self, mock_proxy):
        """Create a test client for the FastAPI app with mocked proxy."""
        app.dependency_overrides[get_orchestrator_proxy] = lambda: mock_proxy
        
        # Mock orchestrator health state for health endpoint tests
        with patch('main.orchestrator_proxy', mock_proxy), \
             patch('main.orchestrator_health') as mock_health:
            mock_health.alive = True
            mock_health.last_check = None
            mock_health.last_error = None
            
            client = TestClient(app)
            yield client
            
        app.dependency_overrides.clear()
    
    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns service info"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "AI Factory Server Service" in data["service"]
        assert data["status"] == "running"
    
    def test_create_service_forwards_to_proxy(self, mock_proxy, client):
        """Verify POST /services calls proxy.start_service"""
        mock_proxy.start_service.return_value = {
            "id": "12345",
            "name": "test-service",
            "recipe_name": "inference/vllm-single-node",
            "status": "pending",
            "config": {"nodes": 1},
            "created_at": "2025-10-08T10:00:00"
        }
        
        response = client.post("/api/v1/services", json={
            "recipe_name": "inference/vllm-single-node"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "12345"
        assert data["recipe_name"] == "inference/vllm-single-node"
        mock_proxy.start_service.assert_called_once()
    
    def test_get_service_forwards_to_proxy(self, mock_proxy, client):
        """Verify GET /services/{id} calls proxy.get_service"""
        mock_proxy.get_service.return_value = {
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
        mock_proxy.get_service.assert_called_once_with("test-123")
    
    def test_get_service_not_found(self, mock_proxy, client):
        """Verify 404 is returned when service doesn't exist"""
        mock_proxy.get_service.return_value = None
        
        response = client.get("/api/v1/services/nonexistent")
        assert response.status_code == 404
        assert "Service not found" in response.json()["detail"]
    
    def test_stop_service_forwards_to_proxy(self, mock_proxy, client):
        """Verify DELETE /services/{id} calls proxy.stop_service"""
        mock_proxy.stop_service.return_value = True
        
        response = client.delete("/api/v1/services/test-123")
        assert response.status_code == 200
        data = response.json()
        assert "stopped successfully" in data["message"]
        mock_proxy.stop_service.assert_called_once_with("test-123")
    
    def test_stop_service_not_found(self, mock_proxy, client):
        """Verify 404 when trying to stop non-existent service"""
        mock_proxy.stop_service.return_value = False
        
        response = client.delete("/api/v1/services/nonexistent")
        assert response.status_code == 404
        assert "Service not found" in response.json()["detail"]
    
    def test_update_service_status_cancelled(self, mock_proxy, client):
        """Test cancelling a service via POST status update"""
        mock_proxy.stop_service.return_value = True
        mock_proxy.service_manager.update_service_status.return_value = True
        
        response = client.post(
            "/api/v1/services/test-123/status",
            json={"status": "cancelled"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["service_id"] == "test-123"
        assert data["status"] == "cancelled"
        mock_proxy.stop_service.assert_called_once_with("test-123")
    
    def test_update_service_status_invalid(self, mock_proxy, client):
        """Test invalid status value returns 400"""
        response = client.post(
            "/api/v1/services/test-123/status",
            json={"status": "invalid_status"}
        )
        assert response.status_code == 400
        assert "Unsupported status value" in response.json()["detail"]
    
    def test_update_service_status_missing_field(self, mock_proxy, client):
        """Test missing status field returns 400"""
        response = client.post(
            "/api/v1/services/test-123/status",
            json={}
        )
        assert response.status_code == 400
        assert "Missing 'status' field" in response.json()["detail"]
    
    def test_get_service_logs(self, mock_proxy, client):
        """Test getting service logs"""
        mock_proxy.get_service_logs.return_value = {
            "logs": "SLURM STDOUT:\nService started successfully\n"
        }
        
        response = client.get("/api/v1/services/test-123/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "Service started successfully" in data["logs"]
        mock_proxy.get_service_logs.assert_called_once_with("test-123")
    
    def test_get_service_status(self, mock_proxy, client):
        """Test getting service status"""
        mock_proxy.get_service_status.return_value = {"status": "running"}
        
        response = client.get("/api/v1/services/test-123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        mock_proxy.get_service_status.assert_called_once_with("test-123")
    
    def test_list_recipes(self, mock_proxy, client):
        """Test listing available recipes"""
        mock_proxy.list_available_recipes.return_value = [
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
        mock_proxy.list_available_recipes.assert_called_once()
    
    def test_get_recipe_by_path(self, mock_proxy, client):
        """Test getting specific recipe by path"""
        mock_proxy.list_available_recipes.return_value = [
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
        assert recipe["path"] == "inference/vllm-single-node"
    
    def test_get_recipe_not_found(self, mock_proxy, client):
        """Test 404 for non-existent recipe"""
        mock_proxy.list_available_recipes.return_value = []
        
        response = client.get("/api/v1/recipes?path=nonexistent")
        assert response.status_code == 404
        assert "Recipe not found" in response.json()["detail"]
    
    def test_list_vllm_services(self, mock_proxy, client):
        """Test listing vLLM services"""
        mock_proxy.find_vllm_services.return_value = [
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
        mock_proxy.find_vllm_services.assert_called_once()
    
    def test_prompt_vllm_service(self, mock_proxy, client):
        """Test sending prompt to vLLM service"""
        mock_proxy.prompt_vllm_service.return_value = {
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
        mock_proxy.prompt_vllm_service.assert_called_once()
    
    def test_prompt_vllm_missing_prompt(self, client):
        """Test vLLM prompt with missing prompt field"""
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={})
        # FastAPI validation error - either 400 or 422
        assert response.status_code in [400, 422]
    
    def test_prompt_vllm_backend_error(self, mock_proxy, client):
        """Test vLLM prompt with backend error"""
        mock_proxy.prompt_vllm_service.side_effect = Exception("VLLM service unavailable")
        
        response = client.post("/api/v1/vllm/vllm-123/prompt", json={
            "prompt": "Test prompt"
        })
        assert response.status_code == 500
        assert "VLLM service unavailable" in response.json()["detail"]
    
    def test_get_vllm_models(self, mock_proxy, client):
        """Test getting models from vLLM service"""
        mock_proxy.get_vllm_models.return_value = {
            "success": True,
            "models": ["gpt2", "Qwen/Qwen2.5-0.5B-Instruct"],
            "service_id": "test-123",
            "endpoint": "http://compute01:8000"
        }
        
        response = client.get("/api/v1/vllm/test-123/models")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "gpt2" in data["models"]
    
    def test_get_service_targets(self, mock_proxy, client):
        """Service targets endpoint should emit Prometheus discovery format"""
        mock_proxy.list_services.return_value = [
            {"id": "svc-1", "recipe_name": "inference/vllm", "status": "running"}
        ]
        mock_proxy.get_service.return_value = {
            "id": "svc-1",
            "recipe_name": "inference/vllm",
            "status": "running",
            "endpoint": "http://mel2079:8001"
        }

        response = client.get("/api/v1/services/targets")

        assert response.status_code == 200
        targets = response.json()
        assert len(targets) == 1
        assert targets[0]["targets"] == ["mel2079:8001"]
        assert targets[0]["labels"]["service_id"] == "svc-1"
        assert targets[0]["labels"]["status"] == "running"
        mock_proxy.list_services.assert_called_once()
        mock_proxy.get_service.assert_called_once_with("svc-1")

    def test_get_service_group_status(self, mock_proxy, client):
        """Service-group status should proxy orchestrator summary"""
        mock_proxy.get_service_group_status.return_value = {
            "group_id": "sg-1",
            "overall_status": "healthy"
        }

        response = client.get("/api/v1/service-groups/sg-1/status")

        assert response.status_code == 200
        assert response.json()["overall_status"] == "healthy"
        mock_proxy.get_service_group_status.assert_called_once_with("sg-1")

    def test_get_service_group_status_not_found(self, mock_proxy, client):
        """Service-group status returns 404 when orchestrator has no record"""
        mock_proxy.get_service_group_status.return_value = None

        response = client.get("/api/v1/service-groups/sg-missing/status")

        assert response.status_code == 404
        assert "sg-missing" in response.json()["detail"]

    def test_get_service_metrics_vllm(self, mock_proxy, client):
        """Service metrics route should return text when vLLM metrics succeed"""
        mock_proxy.get_service.return_value = {
            "id": "svc-1",
            "recipe_name": "inference/vllm-single-node"
        }
        mock_proxy.get_service_metrics.return_value = "# HELP\nmetric 1"

        response = client.get("/api/v1/services/svc-1/metrics")

        assert response.status_code == 200
        assert "metric" in response.text
        assert response.headers["content-type"].startswith("text/plain")
        mock_proxy.get_service_metrics.assert_called_once_with("svc-1")

    def test_get_service_metrics_qdrant(self, mock_proxy, client):
        """Service metrics route should handle vector DB recipes"""
        mock_proxy.get_service.return_value = {
            "id": "svc-2",
            "recipe_name": "vector-db/qdrant"
        }
        mock_proxy.get_service_metrics.return_value = "# TYPE qdrant"

        response = client.get("/api/v1/services/svc-2/metrics")

        assert response.status_code == 200
        assert "qdrant" in response.text
        mock_proxy.get_service_metrics.assert_called_once_with("svc-2")

    def test_get_service_metrics_unsupported_recipe(self, mock_proxy, client):
        """Service metrics returns 400 for unknown recipes"""
        mock_proxy.get_service.return_value = {
            "id": "svc-3",
            "recipe_name": "monitoring/prometheus"
        }

        mock_proxy.get_service_metrics.side_effect = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metrics not available"
        )
        response = client.get("/api/v1/services/svc-3/metrics")

        print(f"Response: {response.status_code} - {response.text}")
        assert response.status_code == 400
        assert "Metrics not available" in response.json()["detail"]

    def test_generic_metrics_success(self, mock_proxy, client):
        """Generic metrics endpoint should emit Prometheus text on success"""
        mock_proxy.get_service_metrics.return_value = {
            "success": True,
            "metrics": "# TYPE requests_total counter"
        }

        response = client.get("/api/v1/metrics/svc-99")

        assert response.status_code == 200
        assert "requests_total" in response.text
        mock_proxy.get_service_metrics.assert_called_once_with("svc-99")

    def test_generic_metrics_error(self, mock_proxy, client):
        """Generic metrics endpoint surfaces orchestrator errors"""
        mock_proxy.get_service_metrics.return_value = {
            "success": False,
            "error": "Not found",
            "status_code": 404
        }

        response = client.get("/api/v1/metrics/missing")

        assert response.status_code == 404
        assert "Not found" in response.json()["detail"]

    def test_list_vector_db_services(self, mock_proxy, client):
        """List vector DB services should proxy orchestrator discovery"""
        mock_proxy.find_vector_db_services.return_value = [{"id": "qdrant-1"}]

        response = client.get("/api/v1/vector-db/services")

        assert response.status_code == 200
        assert response.json()["vector_db_services"][0]["id"] == "qdrant-1"
        mock_proxy.find_vector_db_services.assert_called_once()

    def test_get_vector_db_collections(self, mock_proxy, client):
        """Collections endpoint should call orchestrator helper"""
        mock_proxy.get_collections.return_value = {"collections": ["docs"]}

        response = client.get("/api/v1/vector-db/qdrant-1/collections")

        assert response.status_code == 200
        assert response.json()["collections"] == ["docs"]
        mock_proxy.get_collections.assert_called_once_with("qdrant-1")

    def test_create_vector_db_collection_requires_vector_size(self, client):
        """Creating a collection without vector_size should 400"""
        response = client.put(
            "/api/v1/vector-db/qdrant-1/collections/new",
            json={"distance": "Cosine"}
        )

        assert response.status_code == 400
        assert "vector_size" in response.json()["detail"]

    def test_upsert_points_validates_payload(self, client):
        """Upsert endpoint should enforce non-empty point list"""
        response = client.put(
            "/api/v1/vector-db/qdrant-1/collections/docs/points",
            json={"points": []}
        )

        assert response.status_code == 400
        assert "points" in response.json()["detail"]

    def test_search_points_requires_query_vector(self, client):
        """Search endpoint validates query vector"""
        response = client.post(
            "/api/v1/vector-db/qdrant-1/collections/docs/points/search",
            json={"limit": 5}
        )

        assert response.status_code == 400
        assert "query_vector" in response.json()["detail"]

    def test_orchestrator_endpoint(self, mock_proxy, client):
        """Orchestrator endpoint should surface URL when available"""
        mock_proxy.get_orchestrator_url.return_value = "http://meluxina:8003"

        response = client.get("/api/v1/orchestrator/endpoint")

        assert response.status_code == 200
        assert response.json()["endpoint"].startswith("http://meluxina")

    @patch('api.routes.get_architecture_info')
    def test_list_available_vllm_models(self, mock_arch, client):
        """Available models endpoint relays architecture catalog"""
        mock_arch.return_value = {"supported_architectures": {"text-generation": ["LlamaForCausalLM"]}}

        response = client.get("/api/v1/vllm/available-models")

        assert response.status_code == 200
        assert "supported_architectures" in response.json()
        mock_arch.assert_called_once()

    def test_list_service_groups(self, mock_proxy, client):
        """Test listing service groups"""
        mock_proxy.list_service_groups.return_value = [
            {
                "id": "sg-test123",
                "type": "replica_group",
                "recipe_name": "inference/vllm-replicas",
                "total_replicas": 4,
                "healthy_replicas": 3
            }
        ]
        
        response = client.get("/api/v1/service-groups")
        assert response.status_code == 200
        groups = response.json()
        assert len(groups) == 1
        assert groups[0]["id"] == "sg-test123"
        mock_proxy.list_service_groups.assert_called_once()
    
    def test_get_service_group(self, mock_proxy, client):
        """Test getting service group details"""
        mock_proxy.get_service_group.return_value = {
            "id": "sg-test123",
            "type": "replica_group",
            "replicas": [
                {"id": "1234:8001", "name": "replica-0", "status": "running"},
                {"id": "1234:8002", "name": "replica-1", "status": "running"}
            ],
            "total_replicas": 2,
            "healthy_replicas": 2
        }
        
        response = client.get("/api/v1/service-groups/sg-test123")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "sg-test123"
        assert len(data["replicas"]) == 2
        mock_proxy.get_service_group.assert_called_once_with("sg-test123")
    
    def test_stop_service_group(self, mock_proxy, client):
        """Test stopping service group"""
        mock_proxy.stop_service_group.return_value = {
            "success": True,
            "message": "Service group stopped",
            "group_id": "sg-test123",
            "replicas_stopped": 4
        }
        
        response = client.delete("/api/v1/service-groups/sg-test123")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_proxy.stop_service_group.assert_called_once_with("sg-test123")
    
    @patch('api.routes.search_hf_models')
    def test_search_vllm_models(self, mock_search, client):
        """Test searching HuggingFace models"""
        mock_search.return_value = [
            {
                "id": "Qwen/Qwen2.5-7B-Instruct",
                "downloads": 500000,
                "architecture": "Qwen2ForCausalLM",
                "vllm_compatible": True
            }
        ]
        
        response = client.get("/api/v1/vllm/search-models?query=qwen&limit=20")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert data["total"] == 1
        mock_search.assert_called_once()
    
    @patch('api.routes.get_hf_model_info')
    def test_get_vllm_model_info(self, mock_get_info, client):
        """Test getting model info from HuggingFace"""
        mock_get_info.return_value = {
            "id": "Qwen/Qwen2.5-3B-Instruct",
            "architecture": "Qwen2ForCausalLM",
            "vllm_compatible": True,
            "size_gb": 6.0
        }
        
        response = client.get("/api/v1/vllm/model-info/Qwen/Qwen2.5-3B-Instruct")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "Qwen/Qwen2.5-3B-Instruct"
        assert data["vllm_compatible"] is True
        mock_get_info.assert_called_once_with("Qwen/Qwen2.5-3B-Instruct")


class TestServiceWorkflows:
    """
    Test complete service workflows using mocks.
    
    These tests verify that multiple components work together correctly
    when mocked, testing the integration logic without external dependencies.
    """
    
    @pytest.fixture
    def mock_proxy(self):
        """Create a mock OrchestratorProxy instance."""
        return Mock()
    
    @pytest.fixture
    def client(self, mock_proxy):
        """Create a test client for the FastAPI app with mocked proxy."""
        app.dependency_overrides[get_orchestrator_proxy] = lambda: mock_proxy
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()
    
    def test_complete_service_lifecycle(self, mock_proxy, client):
        """
        Test a complete service lifecycle: create -> list -> verify
        
        This tests the workflow logic:
        1. Service creation returns valid ID
        2. Created service appears in service list
        3. Service data consistency between operations
        """
        # Mock service creation
        mock_proxy.start_service.return_value = {
            "id": "workflow-test-123",
            "name": "workflow-service",
            "recipe_name": "test/recipe",
            "status": "pending",
            "nodes": 1,
            "config": {"nodes": 1},
            "created_at": "2025-10-08T10:00:00"
        }
        
        # Mock service listing (includes our created service)
        mock_proxy.list_services.return_value = [
            {
                "id": "workflow-test-123",
                "name": "workflow-service",
                "recipe_name": "test/recipe",
                "status": "running",
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
        mock_proxy.start_service.assert_called_once()
        mock_proxy.list_services.assert_called_once()
