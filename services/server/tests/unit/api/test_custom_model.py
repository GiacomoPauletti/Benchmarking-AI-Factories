
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from api.routes import router
from service_orchestration.core.service_orchestrator import ServiceOrchestrator

def test_create_service_custom_model():
    # Mock orchestrator
    mock_orchestrator = MagicMock()
    
    # Return a full ServiceResponse compatible dictionary
    mock_orchestrator.start_service.return_value = {
        "id": "vllm-replicas-123",
        "name": "vllm-replicas",
        "recipe_name": "inference/vllm-single-node",
        "status": "submitted",
        "job_id": "123",
        "config": {"model": "meta-llama/Llama-2-7b-chat-hf"},
        "created_at": "2024-01-01T00:00:00Z"
    }
    
    from main import app
    from api.routes import get_orchestrator_proxy
    
    # Use dependency override
    app.dependency_overrides[get_orchestrator_proxy] = lambda: mock_orchestrator
    
    try:
        client = TestClient(app)
        
        payload = {
            "recipe_name": "inference/vllm-single-node",
            "config": {
                "model": "meta-llama/Llama-2-7b-chat-hf",
                "resources": {"gpu": 1}
            }
        }
        
        response = client.post("/api/v1/services", json=payload)
        
        assert response.status_code == 200
        
        # Verify start_service was called with the correct config
        mock_orchestrator.start_service.assert_called_once()
        call_args = mock_orchestrator.start_service.call_args
        assert call_args.kwargs["recipe_name"] == "inference/vllm-single-node"
        assert call_args.kwargs["config"]["model"] == "meta-llama/Llama-2-7b-chat-hf"
    finally:
        # Clean up override
        app.dependency_overrides.pop(get_orchestrator_proxy, None)

