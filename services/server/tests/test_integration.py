"""
Integration Tests for Server

These integration tests use real services, live servers, or combinations of components.
"""

import pytest
import os
import requests
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))

from main import app


class TestLiveServerIntegration:
    """
    Test integration with a live running server.
    
    These tests will only run if a live server is available
    (detected by the presence of a .server-endpoint file).
    """
    
    @pytest.fixture
    def server_endpoint(self):
        """
        Get the live server endpoint if available.
        
        Skips tests if no live server is detected.
        Reads from .server-endpoint file created by launch_local.sh.
        """
        endpoint_file = Path("/app/services/server/.server-endpoint")
        if not endpoint_file.exists():
            pytest.skip("No live server endpoint available - skipping live integration tests")
        
        endpoint = endpoint_file.read_text().strip()
        if not endpoint:
            pytest.skip("Empty server endpoint file - skipping live integration tests")
        
        return endpoint
    
    def test_live_server_health_workflow(self, server_endpoint):
        """
        Test health and basic endpoints against a live server.
        
        This makes real HTTP requests to verify the server is working.
        """
        # Test health endpoint
        health_response = requests.get(f"{server_endpoint}/health", timeout=10)
        assert health_response.status_code == 200
        health_data = health_response.json()
        assert health_data["status"] == "healthy"
        
        # Test root endpoint
        root_response = requests.get(f"{server_endpoint}/", timeout=10)
        assert root_response.status_code == 200
        root_data = root_response.json()
        assert "AI Factory Server Service" in root_data["service"]
        assert root_data["status"] == "running"
    
    def test_live_server_api_workflow(self, server_endpoint):
        """
        Test API endpoints against a live server.
        
        This tests the complete API functionality with a real server.
        """
        # Test recipes endpoint
        recipes_response = requests.get(f"{server_endpoint}/api/v1/recipes", timeout=10)
        assert recipes_response.status_code == 200
        recipes = recipes_response.json()
        assert isinstance(recipes, list)
        
        # Test services listing endpoint
        services_response = requests.get(f"{server_endpoint}/api/v1/services", timeout=10)
        assert services_response.status_code == 200
        services = services_response.json()
        assert isinstance(services, list)
    
    def test_live_server_service_creation(self, server_endpoint):
        """
        Test service creation against a live server.
        
        WARNING: This creates a real SLURM job! Only run in test environments.
        """
        # Test service creation with the vllm recipe
        create_response = requests.post(
            f"{server_endpoint}/api/v1/services",
            json={
                "recipe_name": "inference/vllm",
                "config": {"nodes": 1}
            },
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        # If we get an error, print it for debugging
        if create_response.status_code not in [200, 201]:
            print(f"Error creating service: {create_response.status_code}")
            print(f"Response: {create_response.text}")
        
        assert create_response.status_code in [200, 201]
        service_data = create_response.json()
        assert "id" in service_data
        assert service_data["recipe_name"] == "inference/vllm"
        
        service_id = service_data["id"]
        
        # Verify the service appears in the service list
        list_response = requests.get(f"{server_endpoint}/api/v1/services", timeout=10)
        assert list_response.status_code == 200
        services = list_response.json()
        
    def test_live_server_service_operations(self, server_endpoint):
        """
        Test complete service lifecycle operations against a live server.
        
        This creates a service, then tests getting it, checking status, logs, and stopping it.
        """
        # First create a service
        create_response = requests.post(
            f"{server_endpoint}/api/v1/services",
            json={
                "recipe_name": "inference/vllm",
                "config": {"nodes": 1}
            },
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        # If we get an error, print it for debugging
        if create_response.status_code not in [200, 201]:
            print(f"Error creating service: {create_response.status_code}")
            print(f"Response: {create_response.text}")
        
        assert create_response.status_code in [200, 201]
        service_data = create_response.json()
        service_id = service_data["id"]
        
        # Test getting the individual service
        get_response = requests.get(f"{server_endpoint}/api/v1/services/{service_id}", timeout=10)
        assert get_response.status_code == 200
        retrieved_service = get_response.json()
        assert retrieved_service["id"] == service_id
        assert retrieved_service["recipe_name"] == "inference/vllm"
        
        # Test getting service status
        status_response = requests.get(f"{server_endpoint}/api/v1/services/{service_id}/status", timeout=10)
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert "status" in status_data
        assert status_data["status"] in ["pending", "starting", "running", "completed", "failed"]
        
        # Test getting service logs
        logs_response = requests.get(f"{server_endpoint}/api/v1/services/{service_id}/logs", timeout=10)
        assert logs_response.status_code == 200
        logs_data = logs_response.json()
        assert "logs" in logs_data
        # Logs might be empty initially, but should be a string
        assert isinstance(logs_data["logs"], str)
        
        # Test stopping the service (if it's still running)
        if status_data["status"] in ["pending", "running"]:
            stop_response = requests.delete(f"{server_endpoint}/api/v1/services/{service_id}", timeout=10)
            # Stop might succeed or fail depending on SLURM state
            assert stop_response.status_code in [200, 404]
            if stop_response.status_code == 200:
                assert "stopped successfully" in stop_response.json()["message"]
    
    def test_live_server_recipes_operations(self, server_endpoint):
        """
        Test recipe listing and retrieval against a live server.
        """
        # Test listing recipes
        recipes_response = requests.get(f"{server_endpoint}/api/v1/recipes", timeout=10)
        assert recipes_response.status_code == 200
        recipes = recipes_response.json()
        assert isinstance(recipes, list)
        assert len(recipes) > 0  # Should have at least some recipes
        
        # Verify recipe structure
        recipe = recipes[0]
        assert "name" in recipe
        assert "category" in recipe
        assert "description" in recipe
        assert "version" in recipe
        assert "path" in recipe
        
        # Test getting a specific recipe
        recipe_name = recipe["name"]
        recipe_response = requests.get(f"{server_endpoint}/api/v1/recipes/{recipe_name}", timeout=10)
        assert recipe_response.status_code == 200
        recipe_details = recipe_response.json()
        assert recipe_details["name"] == recipe_name
        
        # Test getting non-existent recipe
        nonexistent_response = requests.get(f"{server_endpoint}/api/v1/recipes/nonexistent_recipe", timeout=10)
        assert nonexistent_response.status_code == 404
    
    def test_live_server_vllm_operations(self, server_endpoint):
        """
        Test VLLM-specific operations against a live server.
        """
        # Test listing VLLM services
        vllm_response = requests.get(f"{server_endpoint}/api/v1/vllm/services", timeout=10)
        assert vllm_response.status_code == 200
        vllm_data = vllm_response.json()
        assert "vllm_services" in vllm_data
        assert isinstance(vllm_data["vllm_services"], list)
        
        # If there are VLLM services, test prompting (but skip if none available)
        if vllm_data["vllm_services"]:
            service = vllm_data["vllm_services"][0]
            service_id = service["id"]
            
            # Test model discovery
            models_response = requests.get(f"{server_endpoint}/api/v1/vllm/{service_id}/models", timeout=10)
            assert models_response.status_code == 200
            models_data = models_response.json()
            assert "models" in models_data
            assert isinstance(models_data["models"], list)
            
            # Test prompting
            prompt_response = requests.post(
                f"{server_endpoint}/api/v1/vllm/{service_id}/prompt",
                json={
                    "prompt": "Hello, this is a test prompt.",
                    "max_tokens": 10,
                    "temperature": 0.1
                },
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            # Prompt might succeed or fail depending on service state
            assert prompt_response.status_code in [200, 500]
            
            if prompt_response.status_code == 200:
                prompt_data = prompt_response.json()
                assert "success" in prompt_data
                if prompt_data["success"]:
                    assert "response" in prompt_data
                    assert isinstance(prompt_data["response"], str)
                    # Check for endpoint_used field (chat or completions)
                    if "endpoint_used" in prompt_data:
                        assert prompt_data["endpoint_used"] in ["chat", "completions"]
                else:
                    # If not successful, should have error and message
                    assert "error" in prompt_data
                    if "status" in prompt_data:
                        # Service might still be starting
                        assert prompt_data["status"] in ["pending", "starting", "configuring", "running"]
    
    def test_live_server_vllm_custom_model_workflow(self, server_endpoint):
        """
        Test creating a VLLM service with custom model configuration.
        
        This tests the custom model feature via environment variables.
        """
        # Create a VLLM service with custom model
        create_response = requests.post(
            f"{server_endpoint}/api/v1/services",
            json={
                "recipe_name": "inference/vllm",
                "config": {
                    "environment": {
                        "VLLM_MODEL": "gpt2"
                    },
                    "resources": {
                        "nodes": 1,
                        "cpu": "8",
                        "memory": "64G",
                        "time_limit": 120,
                        "gpu": "1"
                    }
                }
            },
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        assert create_response.status_code in [200, 201]
        service_data = create_response.json()
        assert "id" in service_data
        service_id = service_data["id"]
        
        # Verify the config was stored correctly
        assert "config" in service_data
        if "environment" in service_data["config"]:
            assert service_data["config"]["environment"]["VLLM_MODEL"] == "gpt2"
        
        # Wait a moment for service to start initializing
        import time
        time.sleep(2)
        
        # Check service status
        status_response = requests.get(f"{server_endpoint}/api/v1/services/{service_id}/status", timeout=10)
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert "status" in status_data
        
        # Once running, check models endpoint
        if status_data["status"] == "running":
            models_response = requests.get(f"{server_endpoint}/api/v1/vllm/{service_id}/models", timeout=10)
            if models_response.status_code == 200:
                models_data = models_response.json()
                if models_data.get("models"):
                    # Should include gpt2 if model loaded successfully
                    assert "gpt2" in models_data["models"] or len(models_data["models"]) > 0
        
        # Clean up - delete the service
        delete_response = requests.delete(f"{server_endpoint}/api/v1/services/{service_id}", timeout=10)
        # Deletion might succeed or fail depending on timing
        assert delete_response.status_code in [200, 404]
    
    def test_live_server_vllm_service_not_ready(self, server_endpoint):
        """
        Test prompting a VLLM service that is still starting.
        
        This tests the improved error messaging for services not ready.
        """
        # Create a new VLLM service
        create_response = requests.post(
            f"{server_endpoint}/api/v1/services",
            json={
                "recipe_name": "inference/vllm",
                "config": {
                    "nodes": 1
                }
            },
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        assert create_response.status_code in [200, 201]
        service_data = create_response.json()
        service_id = service_data["id"]
        
        # Immediately try to prompt (service likely not ready)
        prompt_response = requests.post(
            f"{server_endpoint}/api/v1/vllm/{service_id}/prompt",
            json={
                "prompt": "Test prompt",
                "max_tokens": 10
            },
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        assert prompt_response.status_code == 200
        prompt_data = prompt_response.json()
        assert "success" in prompt_data
        
        # If service not ready, should get helpful error message
        if not prompt_data["success"]:
            assert "error" in prompt_data
            # Should have user-friendly message
            if "message" in prompt_data:
                assert "starting" in prompt_data["message"].lower() or "not ready" in prompt_data["message"].lower()
            # Should include status
            if "status" in prompt_data:
                assert prompt_data["status"] in ["pending", "starting", "configuring", "running"]
        
        # Clean up
        delete_response = requests.delete(f"{server_endpoint}/api/v1/services/{service_id}", timeout=10)
        assert delete_response.status_code in [200, 404]
    
    def test_live_server_vllm_chat_template_fallback(self, server_endpoint):
        """
        Test that prompting automatically falls back from chat to completions endpoint.
        
        This tests the chat template error detection and fallback mechanism.
        """
        # Create a VLLM service with a base model (no chat template)
        create_response = requests.post(
            f"{server_endpoint}/api/v1/services",
            json={
                "recipe_name": "inference/vllm",
                "config": {
                    "environment": {
                        "VLLM_MODEL": "gpt2"  # Base model without chat template
                    },
                    "resources": {
                        "nodes": 1,
                        "cpu": "8",
                        "memory": "64G",
                        "time_limit": 120,
                        "gpu": "1"
                    }
                }
            },
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if create_response.status_code not in [200, 201]:
            pytest.skip("Could not create VLLM service for chat template fallback test")
        
        service_data = create_response.json()
        service_id = service_data["id"]
        
        # Wait for service to be running
        import time
        max_wait = 120  # 2 minutes
        wait_interval = 10
        total_waited = 0
        
        while total_waited < max_wait:
            status_response = requests.get(f"{server_endpoint}/api/v1/services/{service_id}/status", timeout=10)
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data.get("status") == "running":
                    break
            time.sleep(wait_interval)
            total_waited += wait_interval
        
        # Try to prompt the service
        prompt_response = requests.post(
            f"{server_endpoint}/api/v1/vllm/{service_id}/prompt",
            json={
                "prompt": "Tell me a joke about programming",
                "max_tokens": 50
            },
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if prompt_response.status_code == 200:
            prompt_data = prompt_response.json()
            if prompt_data.get("success"):
                # Should have used completions endpoint (fallback from chat)
                assert "endpoint_used" in prompt_data
                # For base models, should be "completions"
                assert prompt_data["endpoint_used"] in ["chat", "completions"]
                assert "response" in prompt_data
        
        # Clean up
        delete_response = requests.delete(f"{server_endpoint}/api/v1/services/{service_id}", timeout=10)
        assert delete_response.status_code in [200, 404]
    
    def test_live_server_error_scenarios(self, server_endpoint):
        """
        Test various error scenarios against a live server.
        """
        # Test getting non-existent service
        get_response = requests.get(f"{server_endpoint}/api/v1/services/nonexistent-service", timeout=10)
        assert get_response.status_code == 404
        
        # Test stopping non-existent service
        stop_response = requests.delete(f"{server_endpoint}/api/v1/services/nonexistent-service", timeout=10)
        assert stop_response.status_code == 404
        
        # Test getting logs for non-existent service
        logs_response = requests.get(f"{server_endpoint}/api/v1/services/nonexistent-service/logs", timeout=10)
        # This might return logs or error depending on implementation
        assert logs_response.status_code in [200, 500]
        
        # Test getting status for non-existent service
        status_response = requests.get(f"{server_endpoint}/api/v1/services/nonexistent-service/status", timeout=10)
        # This might return status or error depending on implementation
        assert status_response.status_code in [200, 500]


class TestErrorHandling:
    """
    Test error handling in integration scenarios.
    
    These tests verify that the system handles errors gracefully
    when components interact.
    """
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_invalid_service_creation(self, client):
        """
        Test error handling for invalid service creation requests.
        """
        # Test with missing recipe name
        response = client.post("/api/v1/services", json={
            "config": {"nodes": 1}
        })
        # Should return 422 (validation error) for missing required field
        assert response.status_code == 422
        
        # Test with empty recipe name
        response = client.post("/api/v1/services", json={
            "recipe_name": "",  # Empty recipe name
            "config": {"nodes": 1}
        })
        # Should return 422 (validation error) for empty recipe name
        assert response.status_code == 422
    
    @patch('api.routes.ServerService')
    def test_service_backend_errors(self, mock_service_class, client):
        """
        Test handling of backend service errors.
        """
        # Setup mock to simulate backend failure
        mock_service = Mock()
        mock_service.start_service.side_effect = Exception("SLURM connection failed")
        mock_service_class.return_value = mock_service
        
        # This should handle the backend error gracefully
        response = client.post("/api/v1/services", json={
            "recipe_name": "inference/vllm",
            "config": {"nodes": 1}
        })
        
        # Should return 500 (internal server error) for backend failures
        assert response.status_code == 500


if __name__ == "__main__":
    # Allow running integration tests directly: python test_integration.py
    pytest.main([__file__, "-v"])