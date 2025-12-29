"""
ServiceOrchestrator Core Logic Tests

These tests verify the core business logic:
1. ServiceOrchestrator - SLURM job management, service lifecycle
2. Recipe building and SLURM script generation

Mock: SLURM Client, Service Manager, HTTP Client
Test: All the business logic that makes decisions
"""

import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock, patch

import pytest

from service_orchestration.core.service_orchestrator import ServiceOrchestrator
from service_orchestration.recipes import (
    Recipe, InferenceRecipe, VectorDbRecipe, StorageRecipe,
    RecipeResources, RecipeCategory
)


def create_mock_recipe(
    name: str = "test-recipe",
    category: str = "inference",
    is_replica: bool = False,
    gpu: int = 1,
    nodes: int = 1
) -> Recipe:
    """Create a mock Recipe object for testing."""
    resources = RecipeResources(nodes=nodes, cpu=4, memory="16G", gpu=gpu, time_limit=60)
    
    if is_replica:
        return InferenceRecipe(
            name=name,
            category=RecipeCategory.INFERENCE,
            container_def=f"{name}.def",
            image=f"{name}.sif",
            resources=resources,
            environment={"TEST": "1"},
            gpu_per_replica=1,
            base_port=8001
        )
    
    if category == "inference":
        return InferenceRecipe(
            name=name,
            category=RecipeCategory.INFERENCE,
            container_def=f"{name}.def",
            image=f"{name}.sif",
            resources=resources,
            environment={"TEST": "1"},
            gpu_per_replica=None,
            base_port=8001
        )
    elif category == "vector-db":
        return VectorDbRecipe(
            name=name,
            category=RecipeCategory.VECTOR_DB,
            container_def=f"{name}.def",
            image=f"{name}.sif",
            resources=resources,
            environment={"TEST": "1"},
            port=6333
        )
    else:
        return StorageRecipe(
            name=name,
            category=RecipeCategory.STORAGE,
            container_def=f"{name}.def",
            image=f"{name}.sif",
            resources=resources,
            environment={"TEST": "1"},
            port=9000
        )


@pytest.fixture
def mock_slurm_client():
    """Mock SLURM client"""
    mock = MagicMock()
    mock.submit_job.return_value = "12345"
    mock.cancel_job.return_value = True
    mock.get_job_status.return_value = "running"
    return mock


@pytest.fixture
def mock_service_manager():
    """Mock service manager"""
    mock = MagicMock()
    mock.register_service.return_value = None
    mock.update_service_status.return_value = True
    mock.get_service.return_value = {"id": "123", "status": "running"}
    mock.is_group.return_value = False
    return mock


@pytest.fixture
def mock_recipe_loader():
    """Mock recipe loader - returns Recipe objects"""
    mock = MagicMock()
    default_recipe = create_mock_recipe("test-recipe", "inference", is_replica=False, gpu=1, nodes=1)
    mock.load.return_value = default_recipe
    mock.list_all.return_value = [default_recipe]
    mock.get_recipe_port.return_value = 8001
    return mock


@pytest.fixture
def mock_job_builder():
    """Mock job builder"""
    mock = MagicMock()
    mock.build_job.return_value = {
        "script": "#!/bin/bash\necho test",
        "job": {"name": "test-job"}
    }
    return mock


@pytest.fixture
def mock_endpoint_resolver():
    """Mock endpoint resolver"""
    mock = MagicMock()
    mock.resolve.return_value = "http://node1:8001"
    mock.register.return_value = None
    return mock


@pytest.fixture
def orchestrator(mock_slurm_client, mock_service_manager, mock_recipe_loader, mock_job_builder, mock_endpoint_resolver):
    """Create a ServiceOrchestrator with mocked dependencies"""
    orch = ServiceOrchestrator()
    orch.slurm_client = mock_slurm_client
    orch.service_manager = mock_service_manager
    orch.recipe_loader = mock_recipe_loader
    orch.job_builder = mock_job_builder
    orch.endpoint_resolver = mock_endpoint_resolver

    mock_http = MagicMock()
    mock_http.aclose = AsyncMock()
    orch._http_client = mock_http

    return orch


class TestServiceOrchestratorCore:
    """
    Test ServiceOrchestrator Core Business Logic.
    
    Responsibility: Manage SLURM jobs, Handle Recipes, Manage State
    """

    def test_start_service_success(self, orchestrator, mock_slurm_client, mock_service_manager):
        """Test starting a service successfully"""
        result = orchestrator.start_service("test-recipe", {"nodes": 1})

        assert result["status"] == "submitted"
        assert result["job_id"] == "12345"
        mock_slurm_client.submit_job.assert_called_once()
        mock_service_manager.register_service.assert_called_once()

    def test_start_service_failure(self, orchestrator, mock_slurm_client, mock_recipe_loader, mock_job_builder):
        """Test starting a service with failure"""
        mock_recipe_loader.load.return_value = ("bob/test-recipe", {
            "name": "test-recipe",
            "resources": {"gpu": 1, "nodes": 1}
        })
        mock_job_builder.build_job.return_value = {
            "script": "#!/bin/bash\necho test",
            "job": {"name": "test-job"}
        }
        mock_slurm_client.submit_job.side_effect = Exception("SLURM error")

        result = orchestrator.start_service("test-recipe", {})

        assert result["status"] == "error"
        assert "SLURM error" in result["message"]

    def test_stop_service(self, orchestrator, mock_slurm_client, mock_service_manager):
        """Test stopping a service"""
        result = orchestrator.stop_service("12345")

        assert result["status"] == "cancelled"
        mock_slurm_client.cancel_job.assert_called_with("12345")
        mock_service_manager.update_service_status.assert_called_with("12345", "cancelled")

    def test_register_endpoint(self, orchestrator, mock_service_manager, mock_endpoint_resolver):
        """Test registering a service endpoint"""
        result = orchestrator.register_endpoint("12345", "node1", 8001, {"model": "gpt2"})

        assert result["status"] == "registered"
        assert "12345" in orchestrator.registered_endpoints
        assert orchestrator.registered_endpoints["12345"]["url"] == "http://node1:8001"
        mock_service_manager.update_service_status.assert_called_with("12345", "running")
        mock_endpoint_resolver.register.assert_called_with("12345", "node1", 8001)

    def test_unregister_endpoint(self, orchestrator):
        """Test unregistering a service endpoint"""
        # First register an endpoint
        orchestrator.registered_endpoints["12345"] = {
            "service_id": "12345",
            "host": "node1",
            "port": 8001,
            "url": "http://node1:8001"
        }
        
        result = orchestrator.unregister_endpoint("12345")
        
        assert result["status"] == "unregistered"
        assert "12345" not in orchestrator.registered_endpoints

    def test_unregister_endpoint_not_found(self, orchestrator):
        """Test unregistering a non-existent endpoint"""
        result = orchestrator.unregister_endpoint("nonexistent")
        
        assert result["status"] == "not_found"

    def test_list_services_refreshes_status(self, orchestrator, mock_service_manager, mock_slurm_client):
        """list_services should refresh non-terminal statuses from SLURM"""
        mock_service_manager.list_services.return_value = [
            {"id": "svc-1", "status": "pending"}
        ]
        mock_slurm_client.get_job_status.return_value = "running"
        orchestrator.service_manager = mock_service_manager

        result = orchestrator.list_services()

        assert result["services"][0]["status"] == "running"
        mock_service_manager.update_service_status.assert_called_once_with("svc-1", "running")

    def test_start_replica_group(self, orchestrator, mock_slurm_client, mock_service_manager, mock_recipe_loader, mock_job_builder):
        """Test starting a replica group"""
        recipe_name = "test-replica-recipe"
        config = {"nodes": 2, "gpu_per_replica": 1}

        # Mock recipe loader to return a replica group Recipe
        mock_recipe = create_mock_recipe(
            name=recipe_name,
            category="inference",
            is_replica=True,
            gpu=4,
            nodes=1
        )
        mock_recipe_loader.load.return_value = mock_recipe
        mock_job_builder.build_job.return_value = {
            "script": "#!/bin/bash\necho test",
            "job": {"name": "test-job"}
        }
        mock_service_manager.create_replica_group.return_value = "sg-123"
        mock_service_manager.get_group_info.return_value = {"id": "sg-123", "replicas": []}

        result = orchestrator.start_service(recipe_name, config)

        assert result["status"] == "submitted"
        assert result["group_id"] == "sg-123"
        mock_service_manager.create_replica_group.assert_called_once()

    def test_stop_service_group(self, orchestrator, mock_slurm_client, mock_service_manager):
        """Test stopping a service group"""
        mock_service_manager.get_group_info.return_value = {
            "node_jobs": [{"job_id": "job1"}, {"job_id": "job2"}]
        }

        result = orchestrator.stop_service_group("sg-123")

        assert result["status"] == "success"
        assert result["stopped"] == 2
        mock_slurm_client.cancel_job.assert_any_call("job1")
        mock_slurm_client.cancel_job.assert_any_call("job2")

    def test_stop_service_group_missing(self, orchestrator, mock_service_manager):
        """stop_service_group should return error when group not found"""
        mock_service_manager.get_group_info.return_value = None

        result = orchestrator.stop_service_group("sg-missing")

        assert result["status"] == "error"
        assert "sg-missing" in result["message"]

    @pytest.mark.asyncio
    async def test_check_vllm_health_success(self, orchestrator):
        """Test VLLM health check for healthy endpoint"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        # vLLM returns {"object": "list", "data": [...]} for /v1/models
        mock_response.json.return_value = {"object": "list", "data": [{"id": "model1"}]}
        orchestrator._http_client.get = AsyncMock(return_value=mock_response)

        result = await orchestrator._check_vllm_health("http://node1:8001")

        assert result is True
        orchestrator._http_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_vllm_health_failure(self, orchestrator):
        """Test VLLM health check for unhealthy endpoint"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        orchestrator._http_client.get = AsyncMock(return_value=mock_response)

        result = await orchestrator._check_vllm_health("http://node1:8001")

        assert result is False

    @pytest.mark.asyncio
    async def test_check_qdrant_health_success(self, orchestrator):
        """Test Qdrant health check for healthy endpoint"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Qdrant returns {"result": {"collections": [...]}}
        mock_response.json.return_value = {"result": {"collections": []}}
        orchestrator._http_client.get = AsyncMock(return_value=mock_response)

        result = await orchestrator._check_qdrant_health("http://node1:6333")

        assert result is True

    def test_get_service_group_status_counts(self, orchestrator, mock_service_manager):
        """Group status summary should aggregate replica states"""
        mock_service_manager.get_group_info.return_value = {"id": "sg-1"}
        mock_service_manager.get_all_replicas_flat.return_value = [
            {"id": "r1", "status": "running"},
            {"id": "r2", "status": "starting"},
            {"id": "r3", "status": "failed"}
        ]
        orchestrator.service_manager = mock_service_manager

        result = orchestrator.get_service_group_status("sg-1")

        assert result["overall_status"] == "degraded"
        assert result["healthy_replicas"] == 1
        assert result["failed_replicas"] == 1

    def test_get_service_group_status_not_found(self, orchestrator, mock_service_manager):
        """Group status should return None when group info missing"""
        mock_service_manager.get_group_info.return_value = None
        orchestrator.service_manager = mock_service_manager

        result = orchestrator.get_service_group_status("sg-unknown")

        assert result is None

    def test_get_service_metrics_starting(self, orchestrator, mock_service_manager):
        """get_service_metrics should return synthetic metrics for starting services"""
        mock_service_manager.is_group.return_value = False
        mock_service_manager.get_service.return_value = {
            "id": "svc-1",
            "recipe_name": "inference/vllm-single-node",
            "status": "starting",
            "created_at": "2025-12-11T10:00:00"
        }
        orchestrator.service_manager = mock_service_manager

        result = orchestrator.get_service_metrics("svc-1")

        assert result["success"] is True
        assert "process_start_time_seconds" in result["metrics"]
        assert result["endpoint"] == "synthetic"

    def test_get_service_metrics_pending(self, orchestrator, mock_service_manager):
        """get_service_metrics should return synthetic metrics for pending services"""
        mock_service_manager.is_group.return_value = False
        mock_service_manager.get_service.return_value = {
            "id": "svc-2",
            "recipe_name": "inference/vllm-single-node",
            "status": "pending",
            "created_at": "2025-12-11T10:00:00"
        }
        orchestrator.service_manager = mock_service_manager

        result = orchestrator.get_service_metrics("svc-2")

        assert result["success"] is True
        assert "process_start_time_seconds" in result["metrics"]
        assert result["endpoint"] == "synthetic"

    def test_get_service_metrics_service_group_pending_and_starting(self, orchestrator, mock_service_manager):
        """Service-group metrics should expose service_status_info with correct numeric value."""
        group_id = "sg-123"

        # Pending group -> value 0
        mock_service_manager.is_group.return_value = True
        mock_service_manager.get_group_info.return_value = {
            "id": group_id,
            "status": "pending",
            "created_at": "2025-12-11T10:00:00",
        }
        mock_service_manager.get_all_replicas_flat.return_value = []
        orchestrator.service_manager = mock_service_manager

        result = orchestrator.get_service_metrics(group_id)
        assert result["success"] is True
        assert f'service_status_info{{service_id="{group_id}",replica_id="aggregate"}} 0' in result["metrics"]

        # Starting group -> value 1
        mock_service_manager.get_group_info.return_value = {
            "id": group_id,
            "status": "starting",
            "created_at": "2025-12-11T10:00:00",
        }
        result = orchestrator.get_service_metrics(group_id)
        assert result["success"] is True
        assert f'service_status_info{{service_id="{group_id}",replica_id="aggregate"}} 1' in result["metrics"]

    def test_get_metrics(self, orchestrator):
        """Test getting aggregated metrics"""
        orchestrator.metrics["total_requests"] = 100
        orchestrator.metrics["failed_requests"] = 5

        # Register an endpoint using the new dict format
        orchestrator.registered_endpoints["123"] = {
            "service_id": "123",
            "host": "node1",
            "port": 8001,
            "url": "http://node1:8001",
            "status": "healthy",
            "registered_at": 1234567890
        }

        metrics = orchestrator.get_metrics()

        assert metrics["global"]["total_requests"] == 100
        assert metrics["global"]["failed_requests"] == 5
        assert "123" in metrics["services"]
        assert metrics["services"]["123"]["status"] == "healthy"

    def test_get_service_returns_group_info(self, orchestrator, mock_service_manager):
        """Test get_service returns group info when service_id is a group"""
        mock_service_manager.is_group.return_value = True
        mock_service_manager.get_group_info.return_value = {
            "id": "sg-123",
            "replicas": [{"id": "r1"}, {"id": "r2"}]
        }
        
        result = orchestrator.get_service("sg-123")
        
        assert result["id"] == "sg-123"
        assert len(result["replicas"]) == 2

    def test_get_service_resolves_endpoint(self, orchestrator, mock_service_manager, mock_endpoint_resolver):
        """Test get_service resolves endpoint for running service"""
        mock_service_manager.is_group.return_value = False
        mock_service_manager.get_service.return_value = {
            "id": "svc-1",
            "status": "running"
        }
        mock_endpoint_resolver.resolve.return_value = "http://node1:8001"
        
        result = orchestrator.get_service("svc-1")
        
        assert result["endpoint"] == "http://node1:8001"
