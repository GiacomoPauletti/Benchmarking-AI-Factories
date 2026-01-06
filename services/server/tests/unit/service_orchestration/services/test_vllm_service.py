"""
VLLM Service Logic Tests

These tests verify the VllmService helper that performs inference-specific
operations.
"""

from unittest.mock import Mock, patch

import pytest

from service_orchestration.services.inference import VllmService


class TestVLLMServiceLogic:
    """
    Test vLLM-specific service logic including chat template fallback.
    
    These test the internal methods of VllmService that implement
    the inference logic.
    """

    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_chat_template_error_detection(self, mock_requests):
        """Test that chat template errors are correctly detected"""
        error_body = {
            "error": {
                "message": "default chat template is no longer allowed",
                "type": "BadRequestError"
            }
        }

        mock_deployer = Mock()
        mock_service_manager = Mock()
        mock_endpoint_resolver = Mock()
        mock_logger = Mock()

        vllm_service = VllmService(mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger)
        assert vllm_service._is_chat_template_error(False, 400, error_body) is True

        other_error_body = {
            "error": {
                "message": "Invalid parameters",
                "type": "BadRequestError"
            }
        }
        assert vllm_service._is_chat_template_error(False, 400, other_error_body) is False

        assert vllm_service._is_chat_template_error(False, 500, error_body) is False

    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_parse_chat_response_success(self, mock_requests):
        """Test parsing successful chat response"""
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

        mock_deployer = Mock()
        mock_service_manager = Mock()
        mock_endpoint_resolver = Mock()
        mock_logger = Mock()

        vllm_service = VllmService(mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger)
        result = vllm_service._parse_chat_response(True, 200, response_body, "http://test:8001", "test-123")

        assert result["success"] is True
        assert result["response"] == "This is a test response"
        assert result["service_id"] == "test-123"
        assert result["endpoint_used"] == "chat"
        assert result["usage"]["prompt_tokens"] == 10

    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_parse_completions_response_success(self, mock_requests):
        """Test parsing successful completions response"""
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

        mock_deployer = Mock()
        mock_service_manager = Mock()
        mock_endpoint_resolver = Mock()
        mock_logger = Mock()

        vllm_service = VllmService(mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger)
        result = vllm_service._parse_completions_response(True, 200, response_body, "http://test:8001", "test-123")

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
        return VllmService(
            deployer=mock_deployer,
            service_manager=mock_service_manager,
            endpoint_resolver=mock_endpoint_resolver,
            logger=mock_logger
        )

    def test_find_services_filters_correctly(self, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that find_services correctly filters VLLM services"""
        mock_service_manager.list_services.return_value = [
            {"id": "123", "name": "vllm-service", "recipe_name": "inference/vllm-single-node", "status": "running"},
            {"id": "456", "name": "postgres-db", "recipe_name": "database/postgres", "status": "running"},
            {"id": "789", "name": "my-inference", "recipe_name": "inference/vllm-single-node", "status": "running"},
        ]

        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", "test-model"))
        mock_endpoint_resolver.resolve.side_effect = [
            "http://node1:8000",
            "http://node2:8000"
        ]

        result = vllm_service.find_services()

        assert len(result) == 2
        assert result[0]["id"] == "123"
        assert result[1]["id"] == "789"

    def test_prompt_service_not_found(self, vllm_service, mock_service_manager):
        """Test that prompt() handles missing service correctly"""
        mock_service_manager.get_service.return_value = None
        mock_service_manager.is_group.return_value = False
        mock_service_manager.get_group_info.return_value = None  # No group exists

        result = vllm_service.prompt("nonexistent", "test prompt")

        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_prompt_maps_job_id_to_group_id(self, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that prompt() maps plain job ID to sg-{job_id} when group exists"""
        job_id = "3793899"
        group_id = f"sg-{job_id}"
        
        # is_group returns False for plain job ID (no sg- prefix)
        mock_service_manager.is_group.return_value = False
        # But get_group_info finds the group with sg- prefix
        mock_service_manager.get_group_info.return_value = {
            "id": group_id,
            "recipe_name": "inference/vllm-single-node",
            "status": "running"
        }
        # get_all_replicas_flat returns replicas for load balancing
        mock_service_manager.get_all_replicas_flat.return_value = [
            {"id": f"{job_id}:8001", "status": "running", "port": 8001}
        ]
        # get_replica_info returns replica info for _prompt_single_service
        mock_service_manager.get_replica_info.return_value = {
            "id": f"{job_id}:8001",
            "port": 8001,
            "recipe_name": "inference/vllm-single-node",
            "group_id": group_id
        }
        
        # Mock endpoint resolution to fail (to get early return)
        mock_endpoint_resolver.resolve.return_value = None
        
        # Create a mock load balancer
        vllm_service.load_balancer.select_replica = Mock(return_value={"id": f"{job_id}:8001", "status": "running"})
        
        result = vllm_service.prompt(job_id, "test prompt")
        
        # Should have called get_group_info with sg-{job_id}
        mock_service_manager.get_group_info.assert_called_with(group_id)

    def test_prompt_single_service_handles_replica_id(self, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that _prompt_single_service correctly handles replica IDs (containing ':')"""
        replica_id = "12345:8001"
        
        mock_service_manager.get_replica_info.return_value = {
            "id": replica_id,
            "port": 8001,
            "job_id": "12345",
            "gpu_id": 0,
            "status": "running",
            "group_id": "sg-12345",
            "recipe_name": "inference/vllm-single-node",
            "node": "compute-node-001"
        }
        
        mock_endpoint_resolver.resolve.return_value = None
        
        result = vllm_service._prompt_single_service(replica_id, "test prompt")
        
        mock_service_manager.get_replica_info.assert_called_once_with(replica_id)
        mock_service_manager.get_service.assert_not_called()
        
        assert result["success"] is False
        assert "endpoint" in result["error"].lower()

    def test_prompt_single_service_handles_regular_service_id(self, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that _prompt_single_service uses get_service for non-replica IDs"""
        service_id = "12345"
        
        mock_service_manager.get_service.return_value = {
            "id": service_id,
            "name": "vllm-test",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }
        
        mock_endpoint_resolver.resolve.return_value = None
        
        result = vllm_service._prompt_single_service(service_id, "test prompt")
        
        mock_service_manager.get_service.assert_called_once_with(service_id)
        mock_service_manager.get_replica_info.assert_not_called()

    def test_prompt_single_service_replica_not_found(self, vllm_service, mock_service_manager):
        """Test that _prompt_single_service handles missing replica correctly"""
        replica_id = "99999:8001"
        
        mock_service_manager.get_replica_info.return_value = None
        
        result = vllm_service._prompt_single_service(replica_id, "test prompt")
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()
        assert replica_id in result["error"]

    def test_prompt_single_service_replica_not_vllm(self, vllm_service, mock_service_manager):
        """Test that _prompt_single_service rejects non-vLLM replicas"""
        replica_id = "12345:8001"
        
        mock_service_manager.get_replica_info.return_value = {
            "id": replica_id,
            "port": 8001,
            "job_id": "12345",
            "group_id": "sg-12345",
            "recipe_name": "database/postgres",  # Not a vLLM service
        }
        
        result = vllm_service._prompt_single_service(replica_id, "test prompt")
        
        assert result["success"] is False
        assert "not a vLLM service" in result["error"]

    @patch('service_orchestration.services.base_service.requests')
    def test_get_models_uses_correct_endpoint(self, mock_requests, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that get_models() uses the resolved endpoint correctly.
        
        Note: We patch base_service.requests because get_models() uses _make_request()
        from BaseService which imports requests there.
        """
        mock_service_manager.get_service.return_value = {
            "id": "123",
            "name": "vllm-test",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }

        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", None))
        mock_endpoint_resolver.resolve.return_value = "http://node1:8000"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [{"id": "model1"}, {"id": "model2"}]}'
        mock_response.json.return_value = {"data": [{"id": "model1"}, {"id": "model2"}]}
        mock_requests.request.return_value = mock_response

        result = vllm_service.get_models("123")

        assert result["success"] is True
        assert "models" in result
        assert len(result["models"]) == 2
        assert "model1" in result["models"]

    @patch('service_orchestration.services.base_service.requests')
    def test_get_models_handles_errors(self, mock_requests, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that get_models() handles errors gracefully.
        
        Note: We patch base_service.requests because get_models() uses _make_request()
        from BaseService which imports requests there.
        """
        mock_service_manager.get_service.return_value = {
            "id": "123",
            "name": "vllm-test",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }

        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", None))
        mock_endpoint_resolver.resolve.return_value = "http://node1:8000"

        # Simulate a connection error - _make_request catches this and returns error response
        import requests as real_requests
        mock_requests.request.side_effect = real_requests.exceptions.ConnectionError("Connection refused")
        mock_requests.exceptions = real_requests.exceptions

        result = vllm_service.get_models("123")

        assert result["success"] is False
        assert "error" in result
        # The error message is standardized to "Connection failed" by _make_request
        assert "Connection" in result["error"]

    @patch('service_orchestration.services.inference.vllm_service.requests.get')
    def test_check_ready_replica_forces_http_check(self, mock_requests_get, vllm_service, mock_deployer):
        service_id = "12345:8001"
        vllm_service._resolve_endpoint_parts = Mock(return_value=("node01", 8001))

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "gpt2"}]}
        mock_requests_get.return_value = mock_response

        is_ready, status, model = vllm_service._check_ready_and_discover_model(service_id, {"status": "starting"})

        assert is_ready is True
        assert status == "running"
        assert model == "gpt2"
        mock_deployer.get_job_status.assert_not_called()
        mock_requests_get.assert_called_once_with("http://node01:8001/v1/models", timeout=8)

    @patch('service_orchestration.services.inference.vllm_service.requests.get')
    def test_check_ready_pending_service_skips_http(self, mock_requests_get, vllm_service, mock_deployer):
        mock_deployer.get_job_status.return_value = "pending"

        is_ready, status, model = vllm_service._check_ready_and_discover_model("12345", {"status": "pending"})

        assert is_ready is False
        assert status == "pending"
        assert model is None
        mock_requests_get.assert_not_called()
        mock_deployer.get_job_status.assert_called_once_with("12345")


class TestVllmServiceModelsListCache:
    """Tests for the get_models() caching functionality.
    
    The models list cache improves UI responsiveness by avoiding redundant
    network requests to the vLLM service when querying available models.
    """

    @pytest.fixture
    def mock_deployer(self):
        return Mock()

    @pytest.fixture
    def mock_service_manager(self):
        return Mock()

    @pytest.fixture
    def mock_endpoint_resolver(self):
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        return Mock()

    @pytest.fixture
    def vllm_service(self, mock_deployer, mock_service_manager, mock_endpoint_resolver, mock_logger):
        return VllmService(
            deployer=mock_deployer,
            service_manager=mock_service_manager,
            endpoint_resolver=mock_endpoint_resolver,
            logger=mock_logger
        )

    def test_cache_initialization(self, vllm_service):
        """Test that cache is properly initialized"""
        assert hasattr(vllm_service, '_models_list_cache')
        assert isinstance(vllm_service._models_list_cache, dict)
        assert vllm_service._models_list_cache_ttl == 120  # 2 minutes

    def test_cache_stores_and_retrieves_response(self, vllm_service):
        """Test that caching stores and retrieves model list responses"""
        service_id = "12345"
        response = {
            "success": True,
            "models": ["model1", "model2"],
            "service_id": service_id,
            "endpoint": "http://node1:8000"
        }
        
        # Cache should be empty initially
        assert vllm_service._get_cached_models_list(service_id) is None
        
        # Store in cache
        vllm_service._cache_models_list(service_id, response)
        
        # Should retrieve from cache
        cached = vllm_service._get_cached_models_list(service_id)
        assert cached is not None
        assert cached["models"] == ["model1", "model2"]
        assert cached["success"] is True

    def test_cache_expires_after_ttl(self, vllm_service):
        """Test that cache entries expire after TTL"""
        import time
        
        service_id = "12345"
        response = {"success": True, "models": ["model1"]}
        
        # Set a very short TTL for testing
        vllm_service._models_list_cache_ttl = 0.1  # 100ms
        
        # Cache the response
        vllm_service._cache_models_list(service_id, response)
        
        # Should be available immediately
        assert vllm_service._get_cached_models_list(service_id) is not None
        
        # Wait for TTL to expire
        time.sleep(0.15)
        
        # Should be expired now
        assert vllm_service._get_cached_models_list(service_id) is None
        
        # Reset TTL
        vllm_service._models_list_cache_ttl = 120

    @patch('service_orchestration.services.base_service.requests')
    def test_get_models_uses_cache(self, mock_requests, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that get_models() uses cache and avoids redundant network requests"""
        service_id = "12345"
        
        # Setup mocks for the first call
        mock_service_manager.get_service.return_value = {
            "id": service_id,
            "name": "vllm-test",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }
        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", None))
        mock_endpoint_resolver.resolve.return_value = "http://node1:8000"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [{"id": "model1"}]}'
        mock_response.json.return_value = {"data": [{"id": "model1"}]}
        mock_requests.request.return_value = mock_response
        
        # First call should hit the network
        result1 = vllm_service.get_models(service_id)
        assert result1["success"] is True
        assert result1["models"] == ["model1"]
        assert mock_requests.request.call_count == 1
        
        # Second call should use cache (no additional network calls)
        result2 = vllm_service.get_models(service_id)
        assert result2["success"] is True
        assert result2["models"] == ["model1"]
        assert mock_requests.request.call_count == 1  # Still 1, not 2

    @patch('service_orchestration.services.base_service.requests')
    def test_get_models_cache_is_per_service(self, mock_requests, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that cache entries are per-service-id"""
        # Setup mocks
        mock_service_manager.get_service.side_effect = lambda sid: {
            "id": sid,
            "name": f"vllm-{sid}",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }
        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", None))
        mock_endpoint_resolver.resolve.return_value = "http://node1:8000"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [{"id": "model1"}]}'
        mock_response.json.return_value = {"data": [{"id": "model1"}]}
        mock_requests.request.return_value = mock_response
        
        # Call for service 1
        vllm_service.get_models("service1")
        assert mock_requests.request.call_count == 1
        
        # Call for service 2 should also hit network (different cache key)
        vllm_service.get_models("service2")
        assert mock_requests.request.call_count == 2
        
        # Call for service 1 again should use cache
        vllm_service.get_models("service1")
        assert mock_requests.request.call_count == 2  # Still 2

    def test_get_models_does_not_cache_errors(self, vllm_service, mock_service_manager):
        """Test that error responses are not cached"""
        service_id = "nonexistent"
        
        mock_service_manager.get_service.return_value = None
        
        # First call should return error
        result1 = vllm_service.get_models(service_id)
        assert result1["success"] is False
        
        # Cache should still be empty (errors not cached)
        assert vllm_service._get_cached_models_list(service_id) is None
