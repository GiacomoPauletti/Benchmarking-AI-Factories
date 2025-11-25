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

from service_orchestration.core.service_orchestrator import ServiceOrchestrator, VLLMEndpoint


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
    """Mock recipe loader"""
    mock = MagicMock()
    mock.load.return_value = {
        "name": "test-recipe",
        "resources": {"gpu": 1, "nodes": 1},
        "environment": {}
    }
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
def orchestrator(mock_slurm_client, mock_service_manager, mock_recipe_loader, mock_job_builder):
    """Create a ServiceOrchestrator with mocked dependencies"""
    orch = ServiceOrchestrator()
    orch.slurm_client = mock_slurm_client
    orch.service_manager = mock_service_manager
    orch.recipe_loader = mock_recipe_loader
    orch.job_builder = mock_job_builder

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
        mock_recipe_loader.load.return_value = {
            "name": "test-recipe",
            "resources": {"gpu": 1, "nodes": 1}
        }
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

    def test_register_service(self, orchestrator, mock_service_manager):
        """Test registering a service"""
        with patch("asyncio.create_task") as mock_create_task:
            result = orchestrator.register_service("12345", "node1", 8001, "gpt2")

            assert result["status"] == "registered"
            assert "12345" in orchestrator.endpoints
            assert orchestrator.endpoints["12345"].url == "http://node1:8001"
            mock_service_manager.update_service_status.assert_called_with("12345", "running")
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_completion_success(self, orchestrator):
        """Test forwarding completion request"""
        endpoint = VLLMEndpoint("123", "node1", 8001, "gpt2", status="healthy")
        orchestrator.endpoints["123"] = endpoint

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"text": "test"}]}
        orchestrator._http_client.post = AsyncMock(return_value=mock_response)

        result = await orchestrator.forward_completion({"prompt": "Hello"})

        assert "_orchestrator_meta" in result
        assert result["_orchestrator_meta"]["service_id"] == "123"
        orchestrator._http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_completion_no_endpoints(self, orchestrator):
        """Test forwarding when no endpoints available"""
        orchestrator.endpoints = {}

        with pytest.raises(RuntimeError, match="No healthy vLLM services available"):
            await orchestrator.forward_completion({"prompt": "Hello"})

    def test_load_balancer_round_robin(self, orchestrator):
        """Test round robin load balancing"""
        ep1 = VLLMEndpoint("1", "node1", 8001, "gpt2", status="healthy")
        ep2 = VLLMEndpoint("2", "node2", 8001, "gpt2", status="healthy")

        async def run_test():
            selected1 = await orchestrator.load_balancer.select_endpoint([ep1, ep2])
            selected2 = await orchestrator.load_balancer.select_endpoint([ep1, ep2])
            selected_again = await orchestrator.load_balancer.select_endpoint([ep1, ep2])

            assert selected1 != selected2
            assert selected_again == selected1

        asyncio.run(run_test())

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

        mock_recipe_loader.load.return_value = {
            "name": recipe_name,
            "gpu_per_replica": 1,
            "resources": {"gpu": 4, "nodes": 2}
        }
        mock_job_builder.build_job.return_value = {
            "script": "#!/bin/bash\necho test",
            "job": {"name": "test-job"}
        }
        mock_service_manager.group_manager.create_replica_group.return_value = "sg-123"
        mock_service_manager.get_group_info.return_value = {"id": "sg-123", "replicas": []}

        result = orchestrator.start_service(recipe_name, config)

        assert result["status"] == "submitted"
        assert result["group_id"] == "sg-123"
        mock_service_manager.group_manager.create_replica_group.assert_called_once()

    def test_stop_service_group(self, orchestrator, mock_slurm_client, mock_service_manager):
        """Test stopping a service group"""
        mock_service_manager.group_manager.get_group.return_value = {
            "node_jobs": [{"job_id": "job1"}, {"job_id": "job2"}]
        }

        result = orchestrator.stop_service_group("sg-123")

        assert result["status"] == "success"
        assert result["stopped"] == 2
        mock_slurm_client.cancel_job.assert_any_call("job1")
        mock_slurm_client.cancel_job.assert_any_call("job2")

    def test_stop_service_group_missing(self, orchestrator, mock_service_manager):
        """stop_service_group should return error when group not found"""
        mock_service_manager.group_manager.get_group.return_value = None

        result = orchestrator.stop_service_group("sg-missing")

        assert result["status"] == "error"
        assert "sg-missing" in result["message"]

    @pytest.mark.asyncio
    async def test_check_endpoint_healthy(self, orchestrator):
        """Test health check for healthy endpoint"""
        endpoint = VLLMEndpoint("123", "node1", 8001, "gpt2", status="unknown")

        mock_response = MagicMock()
        mock_response.status_code = 200
        orchestrator._http_client.get = AsyncMock(return_value=mock_response)

        await orchestrator._check_endpoint(endpoint)

        assert endpoint.status == "healthy"
        assert endpoint.last_health_check > 0

    @pytest.mark.asyncio
    async def test_check_endpoint_unhealthy(self, orchestrator):
        """Test health check for unhealthy endpoint"""
        endpoint = VLLMEndpoint("123", "node1", 8001, "gpt2", status="healthy")

        mock_response = MagicMock()
        mock_response.status_code = 500
        orchestrator._http_client.get.return_value = mock_response

        await orchestrator._check_endpoint(endpoint)

        assert endpoint.status == "unhealthy"

    def test_get_service_group_status_counts(self, orchestrator, mock_service_manager):
        """Group status summary should aggregate replica states"""
        mock_service_manager.get_group_info.return_value = {"id": "sg-1"}
        mock_service_manager.group_manager.get_all_replicas_flat.return_value = [
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

    def test_get_service_metrics_not_ready(self, orchestrator, mock_service_manager):
        """get_service_metrics should report pending services as unavailable"""
        mock_service_manager.is_group.return_value = False
        mock_service_manager.get_service.return_value = {
            "id": "svc-1",
            "recipe_name": "inference/vllm-single-node",
            "status": "starting"
        }
        orchestrator.service_manager = mock_service_manager

        result = orchestrator.get_service_metrics("svc-1")

        assert result["success"] is False
        assert "starting" in result["error"] or "starting" in result.get("message", "")

    def test_get_metrics(self, orchestrator):
        """Test getting aggregated metrics"""
        orchestrator.metrics["total_requests"] = 100
        orchestrator.metrics["failed_requests"] = 5

        ep = VLLMEndpoint("123", "node1", 8001, "gpt2", status="healthy")
        ep.total_requests = 50
        orchestrator.endpoints["123"] = ep

        metrics = orchestrator.get_metrics()

        assert metrics["global"]["total_requests"] == 100
        assert metrics["global"]["failed_requests"] == 5
        assert metrics["services"]["123"]["total_requests"] == 50

    def test_configure_load_balancer(self, orchestrator):
        """Test configuring load balancer strategy"""
        result = orchestrator.configure_load_balancer("least_loaded")

        assert result["status"] == "configured"
        assert orchestrator.load_balancer.strategy == "least_loaded"

        result = orchestrator.configure_load_balancer("invalid")
        assert result["status"] == "error"
