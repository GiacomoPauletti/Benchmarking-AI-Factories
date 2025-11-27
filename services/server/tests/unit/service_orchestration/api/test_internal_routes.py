"""
Orchestrator Internal API Tests

These tests verify that the internal orchestrator FastAPI app (running on MeluXina) correctly:
1. Receives internal HTTP requests
2. Calls the Core ServiceOrchestrator logic
3. Returns proper JSON responses

Mock: ServiceOrchestrator (core business logic)
Do NOT test SLURM/business logic here - only Internal API <-> Core translation.
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from service_orchestration.api import create_app


class TestOrchestratorInternalAPI:
    """
    Test Internal API (Orchestrator Layer).
    
    Responsibility: Internal HTTP Request → Call Core Logic → JSON Response
    
    This API runs on MeluXina and is called by the Gateway or other internal services.
    """
    
    @pytest.fixture
    def mock_core_orchestrator(self):
        """Create a fully mocked ServiceOrchestrator for API tests"""
        return MagicMock()

    @pytest.fixture
    def client(self, mock_core_orchestrator):
        """Create a TestClient with the mocked core orchestrator"""
        app = create_app(mock_core_orchestrator)
        return TestClient(app)

    def test_list_services(self, client, mock_core_orchestrator):
        """Test internal list services endpoint"""
        mock_core_orchestrator.list_services.return_value = {"services": [], "total": 0}
        
        response = client.get("/api/services")
        
        assert response.status_code == 200
        assert response.json() == {"services": [], "total": 0}
        mock_core_orchestrator.list_services.assert_called_once()

    def test_start_service(self, client, mock_core_orchestrator):
        """Test internal start service endpoint"""
        mock_core_orchestrator.start_service.return_value = {
            "status": "submitted", 
            "job_id": "123",
            "service_data": {
                "id": "123",
                "recipe_name": "test-recipe",
                "status": "pending"
            }
        }
        
        payload = {
            "recipe_name": "test-recipe",
            "config": {"nodes": 1}
        }
        
        response = client.post("/api/services/start", json=payload)
        
        assert response.status_code == 200
        assert response.json()["status"] == "submitted"
        assert response.json()["job_id"] == "123"
        mock_core_orchestrator.start_service.assert_called_with("test-recipe", {"nodes": 1})

    def test_start_service_missing_recipe(self, client):
        """Test start service with missing recipe name"""
        response = client.post("/api/services/start", json={})
        
        # FastAPI validation should catch this
        assert response.status_code in [400, 422]
        detail = response.json()["detail"]
        # Check if error mentions recipe_name
        assert any("recipe_name" in str(err).lower() for err in ([detail] if isinstance(detail, str) else detail))

    def test_stop_service(self, client, mock_core_orchestrator):
        """Test internal stop service endpoint"""
        mock_core_orchestrator.stop_service.return_value = {"status": "cancelled", "service_id": "123"}
        
        response = client.post("/api/services/stop/123")
        
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        mock_core_orchestrator.stop_service.assert_called_with("123")

    def test_get_service(self, client, mock_core_orchestrator):
        """Test internal get service endpoint"""
        mock_core_orchestrator.get_service.return_value = {
            "id": "123", 
            "status": "running",
            "recipe_name": "test-recipe"
        }
        
        response = client.get("/api/services/123")
        
        assert response.status_code == 200
        assert response.json()["id"] == "123"
        assert response.json()["status"] == "running"
        mock_core_orchestrator.get_service.assert_called_with("123")

    def test_get_service_not_found(self, client, mock_core_orchestrator):
        """Test get service returns 404 for non-existent service"""
        mock_core_orchestrator.get_service.return_value = None
        
        response = client.get("/api/services/999")
        
        assert response.status_code == 404

    def test_get_service_status(self, client, mock_core_orchestrator):
        """Test internal get service status endpoint"""
        mock_core_orchestrator.get_service_status.return_value = {"status": "running"}
        
        response = client.get("/api/services/123/status")
        
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        mock_core_orchestrator.get_service_status.assert_called_with("123")

    def test_get_service_logs(self, client, mock_core_orchestrator):
        """Test internal get service logs endpoint"""
        mock_core_orchestrator.get_service_logs.return_value = {
            "logs": "Job started\nService ready\n",
            "service_id": "123"
        }
        
        response = client.get("/api/services/123/logs")
        
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "Job started" in data["logs"]
        mock_core_orchestrator.get_service_logs.assert_called_with("123")

    def test_list_service_groups(self, client, mock_core_orchestrator):
        """Test internal list service groups endpoint"""
        mock_core_orchestrator.list_service_groups.return_value = [
            {
                "id": "sg-123",
                "type": "replica_group",
                "total_replicas": 4,
                "healthy_replicas": 3
            }
        ]
        
        response = client.get("/api/service-groups")
        
        assert response.status_code == 200
        groups = response.json()
        assert len(groups) == 1
        assert groups[0]["id"] == "sg-123"
        mock_core_orchestrator.list_service_groups.assert_called_once()

    def test_get_service_group_status(self, client, mock_core_orchestrator):
        """Internal service group status endpoint should surface orchestrator summary"""
        mock_core_orchestrator.get_service_group_status.return_value = {
            "group_id": "sg-1",
            "overall_status": "healthy"
        }

        response = client.get("/api/service-groups/sg-1/status")

        assert response.status_code == 200
        assert response.json()["overall_status"] == "healthy"
        mock_core_orchestrator.get_service_group_status.assert_called_once_with("sg-1")

    def test_get_service_group_status_not_found(self, client, mock_core_orchestrator):
        """Internal service group status returns 404 when orchestrator has no group"""
        mock_core_orchestrator.get_service_group_status.return_value = None

        response = client.get("/api/service-groups/missing/status")

        assert response.status_code == 404

    def test_stop_service_group(self, client, mock_core_orchestrator):
        """Stopping a service group should call orchestrator.stop_service_group"""
        mock_core_orchestrator.stop_service_group.return_value = {
            "status": "success",
            "message": "Service group stopped",
            "group_id": "sg-1",
            "stopped": 4,
            "stopped_jobs": ["123", "124"]
        }

        response = client.post("/api/service-groups/sg-1/stop")

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert result["group_id"] == "sg-1"
        assert result["replicas_stopped"] == 4
        mock_core_orchestrator.stop_service_group.assert_called_once_with("sg-1")

    def test_forward_completion(self, client, mock_core_orchestrator):
        """Test completion request forwarding to vLLM via data plane"""
        # Mock the vLLM service wrapper
        mock_core_orchestrator.vllm_service.prompt.return_value = {
            "success": True,
            "response": "hello",
            "service_id": "123",
            "endpoint": "http://mel1234:8001"
        }
        
        payload = {
            "prompt": "hi",
            "max_tokens": 100
        }
        response = client.post("/api/services/vllm/123/prompt", json=payload)
        
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert result["response"] == "hello"
        mock_core_orchestrator.vllm_service.prompt.assert_called_once()

    def test_get_available_recipes(self, client, mock_core_orchestrator):
        """Test internal get recipes endpoint"""
        mock_core_orchestrator.list_recipes.return_value = [
            {
                "name": "vllm",
                "path": "inference/vllm-single-node",
                "category": "inference"
            }
        ]
        
        response = client.get("/api/recipes")
        
        assert response.status_code == 200
        recipes = response.json()
        assert len(recipes) == 1
        assert recipes[0]["name"] == "vllm"
        mock_core_orchestrator.list_recipes.assert_called_once()

    def test_vector_db_listing(self, client, mock_core_orchestrator):
        """Vector DB discovery endpoint should call qdrant_service.find_services"""
        mock_core_orchestrator.qdrant_service.find_services.return_value = [
            {"id": "qdrant-1", "status": "running"}
        ]

        response = client.get("/api/services/vector-db")

        assert response.status_code == 200
        data = response.json()
        assert data["vector_db_services"][0]["id"] == "qdrant-1"
        mock_core_orchestrator.qdrant_service.find_services.assert_called_once()

    def test_vector_db_collections(self, client, mock_core_orchestrator):
        """Collections route should delegate to qdrant_service.get_collections"""
        mock_core_orchestrator.qdrant_service.get_collections.return_value = {
            "collections": ["docs"]
        }

        response = client.get("/api/services/vector-db/qdrant-1/collections")

        assert response.status_code == 200
        assert response.json()["collections"] == ["docs"]
        mock_core_orchestrator.qdrant_service.get_collections.assert_called_once_with("qdrant-1", 5)

    def test_vector_db_create_collection(self, client, mock_core_orchestrator):
        """Collection creation should send vector size to qdrant service"""
        mock_core_orchestrator.qdrant_service.create_collection.return_value = {"success": True}

        response = client.put(
            "/api/services/vector-db/qdrant-1/collections/new",
            json={"vector_size": 384}
        )

        assert response.status_code == 200
        mock_core_orchestrator.qdrant_service.create_collection.assert_called_once_with(
            "qdrant-1", "new", 384, "Cosine", 10
        )

    def test_management_configure_load_balancer(self, client, mock_core_orchestrator):
        """Management configure route should invoke orchestrator.configure_load_balancer"""
        mock_core_orchestrator.configure_load_balancer.return_value = {
            "status": "configured",
            "strategy": "least_loaded"
        }

        response = client.post("/api/configure", params={"strategy": "least_loaded"})

        assert response.status_code == 200
        assert response.json()["strategy"] == "least_loaded"
        mock_core_orchestrator.configure_load_balancer.assert_called_once_with("least_loaded")

    def test_management_metrics(self, client, mock_core_orchestrator):
        """Management metrics endpoint should return orchestrator metrics blob"""
        mock_core_orchestrator.get_metrics.return_value = {"global": {"total_requests": 5}}

        response = client.get("/api/metrics")

        assert response.status_code == 200
        assert response.json()["global"]["total_requests"] == 5
        mock_core_orchestrator.get_metrics.assert_called_once()

    def test_service_metrics_plain_text(self, client, mock_core_orchestrator):
        """Internal metrics endpoint should return Prometheus text when successful"""
        mock_core_orchestrator.get_service_metrics.return_value = {
            "success": True,
            "metrics": "# TYPE requests_total counter"
        }

        response = client.get("/api/services/svc-1/metrics")

        assert response.status_code == 200
        assert response.text.startswith("# TYPE")
        assert response.headers["content-type"].startswith("text/plain")

    def test_client_completions_runtime_error(self, client, mock_core_orchestrator):
        """Client completion route should map orchestrator runtime errors to HTTP"""
        mock_core_orchestrator.forward_completion.side_effect = RuntimeError("No healthy vLLM services available")

        response = client.post("/v1/completions", json={"prompt": "hi"})

        assert response.status_code == 503
        assert "No healthy" in response.json()["detail"]
