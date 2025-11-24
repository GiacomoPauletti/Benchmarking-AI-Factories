"""
Orchestrator Core Logic Tests

These tests verify the core business logic:
1. ServiceOrchestrator - SLURM job management, service lifecycle
2. VllmService - vLLM-specific operations
3. Recipe building and SLURM script generation

Mock: SLURM Client, Service Manager, HTTP Client
Test: All the business logic that makes decisions
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, AsyncMock, patch

# Add src to path
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from service_orchestration.core.service_orchestrator import ServiceOrchestrator, VLLMEndpoint
from service_orchestration.services.inference import VllmService


# ===========================
# ServiceOrchestrator Core Tests
# ===========================

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
    # Return a valid recipe dict (non-replica group)
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
    # Replace internal dependencies with mocks
    orch.slurm_client = mock_slurm_client
    orch.service_manager = mock_service_manager
    orch.recipe_loader = mock_recipe_loader
    orch.job_builder = mock_job_builder
    
    # Mock async HTTP client properly
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
        recipe_name = "test-recipe"
        config = {"nodes": 1}
        
        result = orchestrator.start_service(recipe_name, config)
        
        assert result["status"] == "submitted"
        assert result["job_id"] == "12345"
        mock_slurm_client.submit_job.assert_called_once()
        mock_service_manager.register_service.assert_called_once()

    def test_start_service_failure(self, orchestrator, mock_slurm_client, mock_recipe_loader, mock_job_builder):
        """Test starting a service with failure"""
        # Ensure recipe loads successfully, then SLURM fails
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
        service_id = "12345"
        
        result = orchestrator.stop_service(service_id)
        
        assert result["status"] == "cancelled"
        mock_slurm_client.cancel_job.assert_called_with(service_id)
        mock_service_manager.update_service_status.assert_called_with(service_id, "cancelled")

    def test_register_service(self, orchestrator, mock_service_manager):
        """Test registering a service"""
        service_id = "12345"
        host = "node1"
        port = 8001
        model = "gpt2"
        
        # Mock asyncio.create_task to avoid needing an event loop
        with patch("asyncio.create_task") as mock_create_task:
            result = orchestrator.register_service(service_id, host, port, model)
            
            assert result["status"] == "registered"
            assert service_id in orchestrator.endpoints
            assert orchestrator.endpoints[service_id].url == f"http://{host}:{port}"
            mock_service_manager.update_service_status.assert_called_with(service_id, "running")
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_completion_success(self, orchestrator):
        """Test forwarding completion request"""
        # Setup endpoint
        endpoint = VLLMEndpoint("123", "node1", 8001, "gpt2", status="healthy")
        orchestrator.endpoints["123"] = endpoint
        
        # Mock async http response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"text": "test"}]}
        
        # Make post return an awaitable
        orchestrator._http_client.post = AsyncMock(return_value=mock_response)
        
        request_data = {"prompt": "Hello"}
        result = await orchestrator.forward_completion(request_data)
        
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
        # Setup endpoints
        ep1 = VLLMEndpoint("1", "node1", 8001, "gpt2", status="healthy")
        ep2 = VLLMEndpoint("2", "node2", 8001, "gpt2", status="healthy")
        
        endpoints = [ep1, ep2]
        
        # We need to run async method
        import asyncio
        
        async def run_test():
            selected1 = await orchestrator.load_balancer.select_endpoint(endpoints)
            selected2 = await orchestrator.load_balancer.select_endpoint(endpoints)
            selected_again = await orchestrator.load_balancer.select_endpoint(endpoints)
            
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
        
        # Mock recipe loader to return a recipe with gpu_per_replica
        mock_recipe_loader.load.return_value = {
            "name": recipe_name, 
            "gpu_per_replica": 1, 
            "resources": {"gpu": 4, "nodes": 2}
        }
        
        # Mock job builder
        mock_job_builder.build_job.return_value = {
            "script": "#!/bin/bash\necho test",
            "job": {"name": "test-job"}
        }
        
        # Mock group manager
        mock_service_manager.group_manager.create_replica_group.return_value = "sg-123"
        mock_service_manager.get_group_info.return_value = {"id": "sg-123", "replicas": []}
        
        result = orchestrator.start_service(recipe_name, config)
        
        assert result["status"] == "submitted"
        assert result["group_id"] == "sg-123"
        mock_service_manager.group_manager.create_replica_group.assert_called_once()

    def test_stop_service_group(self, orchestrator, mock_slurm_client, mock_service_manager):
        """Test stopping a service group"""
        group_id = "sg-123"
        
        # Mock group info
        mock_service_manager.group_manager.get_group.return_value = {
            "node_jobs": [{"job_id": "job1"}, {"job_id": "job2"}]
        }
        
        result = orchestrator.stop_service_group(group_id)
        
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
        
        # Mock async http response
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
        
        # Mock http response
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
        # Setup some metrics
        orchestrator.metrics["total_requests"] = 100
        orchestrator.metrics["failed_requests"] = 5
        
        # Setup an endpoint
        ep = VLLMEndpoint("123", "node1", 8001, "gpt2", status="healthy")
        ep.total_requests = 50
        orchestrator.endpoints["123"] = ep
        
        metrics = orchestrator.get_metrics()
        
        assert metrics["global"]["total_requests"] == 100
        assert metrics["global"]["failed_requests"] == 5
        assert "123" in metrics["services"]
        assert metrics["services"]["123"]["total_requests"] == 50

    def test_configure_load_balancer(self, orchestrator):
        """Test configuring load balancer strategy"""
        result = orchestrator.configure_load_balancer("least_loaded")
        
        assert result["status"] == "configured"
        assert orchestrator.load_balancer.strategy == "least_loaded"
        
        # Test invalid strategy
        result = orchestrator.configure_load_balancer("invalid")
        assert result["status"] == "error"


# ===========================
# VllmService Logic Tests
# ===========================

class TestVLLMServiceLogic:
    """
    Test vLLM-specific service logic including chat template fallback.
    
    These test the internal methods of VllmService that implement
    the inference logic.
    """
    
    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_chat_template_error_detection(self, mock_requests):
        """Test that chat template errors are correctly detected"""
        # Mock response with chat template error
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {
                "message": "default chat template is no longer allowed",
                "type": "BadRequestError"
            }
        }
        
        # Create VllmService with mocked dependencies
        mock_deployer = Mock()
        mock_service_manager = Mock()
        mock_endpoint_resolver = Mock()
        mock_logger = Mock()
        
        vllm_service = VllmService(mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger)
        is_error = vllm_service._is_chat_template_error(mock_response)
        assert is_error is True
        
        # Test with different error
        mock_response.json.return_value = {
            "error": {
                "message": "Invalid parameters",
                "type": "BadRequestError"
            }
        }
        is_error = vllm_service._is_chat_template_error(mock_response)
        assert is_error is False
        
        # Test with non-400 status
        mock_response.status_code = 500
        is_error = vllm_service._is_chat_template_error(mock_response)
        assert is_error is False
    
    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_parse_chat_response_success(self, mock_requests):
        """Test parsing successful chat response"""
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
        
        # Create VllmService with mocked dependencies
        mock_deployer = Mock()
        mock_service_manager = Mock()
        mock_endpoint_resolver = Mock()
        mock_logger = Mock()
        
        vllm_service = VllmService(mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger)
        result = vllm_service._parse_chat_response(mock_response, "http://test:8001", "test-123")
        
        assert result["success"] is True
        assert result["response"] == "This is a test response"
        assert result["service_id"] == "test-123"
        assert result["endpoint_used"] == "chat"
        assert result["usage"]["prompt_tokens"] == 10
    
    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_parse_completions_response_success(self, mock_requests):
        """Test parsing successful completions response"""
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
        
        # Create VllmService with mocked dependencies
        mock_deployer = Mock()
        mock_service_manager = Mock()
        mock_endpoint_resolver = Mock()
        mock_logger = Mock()
        
        vllm_service = VllmService(mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger)
        result = vllm_service._parse_completions_response(mock_response, "http://test:8001", "test-123")
        
        assert result["success"] is True
        assert result["response"] == "This is a completion"
        assert result["service_id"] == "test-123"
        assert result["endpoint_used"] == "completions"
        assert result["usage"]["total_tokens"] == 25


class TestVllmServiceUnit:
    """
    Unit tests for VllmService methods.
    
    These tests exercise VllmService implementation directly with mocked
    dependencies to catch implementation bugs that high-level API tests miss.
    """
    
    @pytest.fixture
    def mock_deployer(self):
        """Create a mock deployer"""
        return Mock()
    
    @pytest.fixture
    def mock_service_manager(self):
        """Create a mock ServiceManager"""
        return Mock()
    
    @pytest.fixture
    def mock_endpoint_resolver(self):
        """Create a mock EndpointResolver"""
        return Mock()
    
    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger"""
        return Mock()
    
    @pytest.fixture
    def vllm_service(self, mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger):
        """Create a VllmService instance with mocked dependencies"""
        service = VllmService(
            deployer=mock_deployer,
            service_manager=mock_service_manager,
            endpoint_resolver=mock_endpoint_resolver,
            logger=mock_logger
        )
        return service
    
    def test_find_services_filters_correctly(self, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that find_services correctly filters VLLM services"""
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

    def test_prompt_service_not_found(self, vllm_service, mock_service_manager):
        """Test that prompt() handles missing service correctly"""
        # Mock service_manager.get_service() to return None
        mock_service_manager.get_service.return_value = None
        mock_service_manager.is_group.return_value = False
        
        # Call prompt
        result = vllm_service.prompt("nonexistent", "test prompt")
        
        # Should return error dict (not raise exception)
        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()
    
    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_get_models_uses_correct_endpoint(self, mock_requests, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that get_models() uses the resolved endpoint correctly"""
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

    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_get_models_handles_errors(self, mock_requests, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that get_models() handles errors gracefully"""
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
