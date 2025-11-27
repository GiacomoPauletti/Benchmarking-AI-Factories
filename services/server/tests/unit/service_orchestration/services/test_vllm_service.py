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
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
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
        assert vllm_service._is_chat_template_error(mock_response) is True

        mock_response.json.return_value = {
            "error": {
                "message": "Invalid parameters",
                "type": "BadRequestError"
            }
        }
        assert vllm_service._is_chat_template_error(mock_response) is False

        mock_response.status_code = 500
        assert vllm_service._is_chat_template_error(mock_response) is False

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

        result = vllm_service.prompt("nonexistent", "test prompt")

        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()

    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_get_models_uses_correct_endpoint(self, mock_requests, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that get_models() uses the resolved endpoint correctly"""
        mock_service_manager.get_service.return_value = {
            "id": "123",
            "name": "vllm-test",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }

        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", None))
        mock_endpoint_resolver.resolve.return_value = "http://node1:8000"

        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"data": [{"id": "model1"}, {"id": "model2"}]}
        mock_requests.get.return_value = mock_response

        result = vllm_service.get_models("123")

        assert result["success"] is True
        assert "models" in result
        assert len(result["models"]) == 2
        assert "model1" in result["models"]

    @patch('service_orchestration.services.inference.vllm_service.requests')
    def test_get_models_handles_errors(self, mock_requests, vllm_service, mock_service_manager, mock_endpoint_resolver):
        """Test that get_models() handles errors gracefully"""
        mock_service_manager.get_service.return_value = {
            "id": "123",
            "name": "vllm-test",
            "status": "running",
            "recipe_name": "inference/vllm-single-node"
        }

        vllm_service._check_ready_and_discover_model = Mock(return_value=(True, "running", None))
        mock_endpoint_resolver.resolve.return_value = "http://node1:8000"

        mock_requests.get.side_effect = Exception("Connection refused")

        result = vllm_service.get_models("123")

        assert result["success"] is False
        assert "error" in result
        assert "Connection refused" in result["error"]
