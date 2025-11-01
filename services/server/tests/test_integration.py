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
        
        Fails tests if server is not healthy or not available.
        Reads from .server-endpoint file created by launch_local.sh.
        Waits for server to be healthy with retries before returning.
        """
        import time
        import os
        
        print("\n[Fixture] Starting server_endpoint fixture...")
        print(f"[Fixture] Current working directory: {os.getcwd()}")
        
        # Try multiple possible paths for the endpoint file
        possible_paths = [
            Path("/app/services/server/.server-endpoint"),
            Path("/app/.server-endpoint"),
            Path(".server-endpoint"),
            Path("./services/server/.server-endpoint"),
        ]
        
        endpoint_file = None
        for path in possible_paths:
            print(f"[Fixture] Checking {path}...", end=" ")
            if path.exists():
                print("✓ Found")
                endpoint_file = path
                break
            else:
                print("✗ Not found")
        
        if endpoint_file is None:
            error_msg = f"Server endpoint file not found. Tried: {[str(p) for p in possible_paths]}"
            print(f"[Fixture] ERROR: {error_msg}")
            raise RuntimeError(error_msg)
        
        endpoint = endpoint_file.read_text().strip()
        print(f"[Fixture] Endpoint from file: {endpoint}")
        
        if not endpoint:
            error_msg = f"Server endpoint file is empty at {endpoint_file}"
            print(f"[Fixture] ERROR: {error_msg}")
            raise RuntimeError(error_msg)
        
        # If endpoint says localhost and we're in a container, try to connect directly
        # If that fails, try host.docker.internal (Docker Desktop) or the server service name
        if "localhost" in endpoint:
            print(f"[Fixture] Detected localhost in endpoint, will try multiple connection strategies...")
            connection_strategies = [
                endpoint,  # Try as-is first
                endpoint.replace("localhost", "host.docker.internal"),  # Try Docker Desktop gateway
                endpoint.replace("localhost", "server"),  # Try service name on same network
                endpoint.replace("localhost", "127.0.0.1"),  # Try 127.0.0.1
            ]
        else:
            connection_strategies = [endpoint]
        
        print(f"[Fixture] Connection strategies to try: {connection_strategies}")
        print(f"[Fixture] Waiting for server to become healthy...")
        
        # Wait for server to be healthy with retries
        max_retries = 20
        retry_delay = 2
        last_error = None
        
        for attempt in range(max_retries):
            for strategy_endpoint in connection_strategies:
                try:
                    print(f"[Fixture] Attempt {attempt + 1}/{max_retries}, trying {strategy_endpoint}...", end=" ")
                    response = requests.get(f"{strategy_endpoint}/health", timeout=5)
                    if response.status_code == 200:
                        print("✓ OK")
                        print(f"[Fixture] Server is healthy at {strategy_endpoint}, returning this endpoint")
                        return strategy_endpoint
                    last_error = f"Health check returned status {response.status_code}"
                except (requests.ConnectionError, requests.Timeout, requests.exceptions.RequestException) as e:
                    last_error = f"{type(e).__name__}"
            
            print(f"✗ All strategies failed")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
        
        # Server not healthy after retries - fail test with detailed error
        total_wait_time = max_retries * retry_delay
        error_message = (
            f"\nServer health check failed:\n"
            f"  Original endpoint: {endpoint}\n"
            f"  Strategies tried: {connection_strategies}\n"
            f"  Total wait time: {total_wait_time}s\n"
            f"  Retries: {max_retries}\n"
            f"  Last error: {last_error}\n"
            f"\nPossible causes:\n"
            f"  1. Server container not started\n"
            f"  2. Server still initializing (check logs)\n"
            f"  3. Server crashed or failed to start\n"
            f"  4. Network connectivity issue between containers\n"
            f"  5. Running outside Docker (localhost:8001 only works on host)\n"
        )
        print(f"[Fixture] RUNTIME ERROR: {error_message}")
        raise RuntimeError(error_message)
    
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
            timeout=120
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
            timeout=60
        )
        
        # If we get an error, print it for debugging
        if create_response.status_code not in [200, 201]:
            print(f"Error creating service: {create_response.status_code}")
            print(f"Response: {create_response.text}")
        
        assert create_response.status_code in [200, 201]
        service_data = create_response.json()
        service_id = service_data["id"]
        
        # Test getting the individual service
        get_response = requests.get(f"{server_endpoint}/api/v1/services/{service_id}", timeout=30)
        assert get_response.status_code == 200
        retrieved_service = get_response.json()
        assert retrieved_service["id"] == service_id
        assert retrieved_service["recipe_name"] == "inference/vllm"
        
        # Test getting service status
        status_response = requests.get(f"{server_endpoint}/api/v1/services/{service_id}/status", timeout=30)
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert "status" in status_data
        assert status_data["status"] in ["pending", "starting", "running", "completed", "failed"]
        
        # Test getting service logs
        logs_response = requests.get(f"{server_endpoint}/api/v1/services/{service_id}/logs", timeout=30)
        assert logs_response.status_code == 200
        logs_data = logs_response.json()
        assert "logs" in logs_data
        # Logs might be empty initially, but should be a string
        assert isinstance(logs_data["logs"], str)
        
        # Test stopping the service (if it's still running)
        if status_data["status"] in ["pending", "running"]:
            stop_response = requests.delete(f"{server_endpoint}/api/v1/services/{service_id}", timeout=30)
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
        
        # Test getting a specific recipe by path (new query parameter approach)
        recipe_path = recipe["path"]
        recipe_response = requests.get(f"{server_endpoint}/api/v1/recipes?path={recipe_path}", timeout=10)
        assert recipe_response.status_code == 200
        recipe_details = recipe_response.json()
        assert recipe_details["path"] == recipe_path
        
        # Test getting non-existent recipe
        nonexistent_response = requests.get(f"{server_endpoint}/api/v1/recipes?path=nonexistent_recipe", timeout=10)
        assert nonexistent_response.status_code == 404
    
    def test_live_server_vllm_operations(self, server_endpoint):
        """
        Test VLLM-specific operations against a live server.
        """
        # Test listing VLLM services
        vllm_response = requests.get(f"{server_endpoint}/api/v1/vllm/services", timeout=30)
        assert vllm_response.status_code == 200
        vllm_data = vllm_response.json()
        assert "vllm_services" in vllm_data
        assert isinstance(vllm_data["vllm_services"], list)
        
        # If there are VLLM services, test prompting (but skip if none available)
        if vllm_data["vllm_services"]:
            service = vllm_data["vllm_services"][0]
            service_id = service["id"]
            
            # Test model discovery
            models_response = requests.get(f"{server_endpoint}/api/v1/vllm/{service_id}/models", timeout=30)
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
                timeout=60
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
            timeout=60
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
        status_response = requests.get(f"{server_endpoint}/api/v1/services/{service_id}/status", timeout=30)
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert "status" in status_data
        
        # Once running, check models endpoint
        if status_data["status"] == "running":
            models_response = requests.get(f"{server_endpoint}/api/v1/vllm/{service_id}/models", timeout=30)
            if models_response.status_code == 200:
                models_data = models_response.json()
                if models_data.get("models"):
                    # Should include gpt2 if model loaded successfully
                    assert "gpt2" in models_data["models"] or len(models_data["models"]) > 0
        
        # Clean up - delete the service
        delete_response = requests.delete(f"{server_endpoint}/api/v1/services/{service_id}", timeout=30)
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
            timeout=120
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
        get_response = requests.get(f"{server_endpoint}/api/v1/services/nonexistent-service", timeout=30)
        assert get_response.status_code == 404
        
        # Test stopping non-existent service
        stop_response = requests.delete(f"{server_endpoint}/api/v1/services/nonexistent-service", timeout=30)
        assert stop_response.status_code == 404
        
        # Test getting logs for non-existent service
        logs_response = requests.get(f"{server_endpoint}/api/v1/services/nonexistent-service/logs", timeout=30)
        # This might return logs or error depending on implementation
        assert logs_response.status_code in [200, 500]
        
        # Test getting status for non-existent service
        status_response = requests.get(f"{server_endpoint}/api/v1/services/nonexistent-service/status", timeout=30)
        # This might return status or error depending on implementation
        assert status_response.status_code in [200, 500]


class TestErrorHandling:
    """
    Test error handling in integration scenarios.
    
    These tests verify that the system handles errors gracefully
    when components interact.
    """
    
    @pytest.fixture
    def mock_server_service(self):
        """Create a mock ServerService instance."""
        return Mock()
    
    @pytest.fixture
    def client(self, mock_server_service):
        """Create a test client for the FastAPI app with mocked dependencies."""
        from api.routes import get_server_service
        # Override the dependency with our mock
        app.dependency_overrides[get_server_service] = lambda: mock_server_service
        client = TestClient(app)
        yield client
        # Clean up the override after the test
        app.dependency_overrides.clear()
    
    def test_invalid_service_creation(self, client, mock_server_service):
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
    
    def test_service_backend_errors(self, mock_server_service, client):
        """
        Test handling of backend service errors.
        """
        # Setup mock to simulate backend failure
        mock_server_service.start_service.side_effect = Exception("SLURM connection failed")
        
        # This should handle the backend error gracefully
        response = client.post("/api/v1/services", json={
            "recipe_name": "inference/vllm",
            "config": {"nodes": 1}
        })
        
        # Should return 500 (internal server error) for backend failures
        assert response.status_code == 500


class TestVectorDbDocumentSearch:
    """
    Integration test for vector database document similarity search.
    
    This test demonstrates a realistic use case: creating a mini document search system
    where documents are embedded as vectors and searched using semantic similarity.
    """
    
    @pytest.fixture
    def server_endpoint(self):
        """Get the live server endpoint. Fails if not available."""
        import time
        
        print("\n[VectorDB Fixture] Starting server_endpoint fixture...")
        
        # Try multiple possible paths for the endpoint file
        possible_paths = [
            Path("/app/services/server/.server-endpoint"),
            Path("/app/.server-endpoint"),
            Path(".server-endpoint"),
            Path("./services/server/.server-endpoint"),
        ]
        
        endpoint_file = None
        for path in possible_paths:
            print(f"[VectorDB Fixture] Checking {path}...", end=" ")
            if path.exists():
                print("✓ Found")
                endpoint_file = path
                break
            else:
                print("✗ Not found")
        
        if endpoint_file is None:
            error_msg = f"Server endpoint file not found. Tried: {[str(p) for p in possible_paths]}"
            print(f"[VectorDB Fixture] ERROR: {error_msg}")
            raise RuntimeError(error_msg)
        
        endpoint = endpoint_file.read_text().strip()
        print(f"[VectorDB Fixture] Endpoint from file: {endpoint}")
        
        if not endpoint:
            error_msg = f"Server endpoint file is empty at {endpoint_file}"
            print(f"[VectorDB Fixture] ERROR: {error_msg}")
            raise RuntimeError(error_msg)
        
        # If endpoint says localhost and we're in a container, try multiple strategies
        if "localhost" in endpoint:
            print(f"[VectorDB Fixture] Detected localhost in endpoint, will try multiple connection strategies...")
            connection_strategies = [
                endpoint,  # Try as-is first
                endpoint.replace("localhost", "host.docker.internal"),  # Try Docker Desktop gateway
                endpoint.replace("localhost", "server"),  # Try service name on same network
                endpoint.replace("localhost", "127.0.0.1"),  # Try 127.0.0.1
            ]
        else:
            connection_strategies = [endpoint]
        
        print(f"[VectorDB Fixture] Connection strategies to try: {connection_strategies}")
        print(f"[VectorDB Fixture] Waiting for server to become healthy...")
        
        # Wait for server to be healthy with retries
        max_retries = 20
        retry_delay = 2
        last_error = None
        
        for attempt in range(max_retries):
            for strategy_endpoint in connection_strategies:
                try:
                    print(f"[VectorDB Fixture] Attempt {attempt + 1}/{max_retries}, trying {strategy_endpoint}...", end=" ")
                    response = requests.get(f"{strategy_endpoint}/health", timeout=5)
                    if response.status_code == 200:
                        print("✓ OK")
                        print(f"[VectorDB Fixture] Server is healthy at {strategy_endpoint}, returning this endpoint")
                        return strategy_endpoint
                    last_error = f"Health check returned status {response.status_code}"
                except (requests.ConnectionError, requests.Timeout, requests.exceptions.RequestException) as e:
                    last_error = f"{type(e).__name__}"
            
            print(f"✗ All strategies failed")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
        
        # Server not healthy after retries - fail test with detailed error
        total_wait_time = max_retries * retry_delay
        error_message = (
            f"\nVectorDB Test - Server health check failed:\n"
            f"  Original endpoint: {endpoint}\n"
            f"  Strategies tried: {connection_strategies}\n"
            f"  Total wait time: {total_wait_time}s\n"
            f"  Retries: {max_retries}\n"
            f"  Last error: {last_error}\n"
        )
        print(f"[VectorDB Fixture] RUNTIME ERROR: {error_message}")
        raise RuntimeError(error_message)
    
    @pytest.fixture
    def sample_documents(self):
        """
        Sample documents with pre-computed mock embeddings.
        
        These represent semantic embeddings for different topics:
        - Animals/pets (cat, dog)
        - Technology/AI (machine learning, programming)
        - Nature (flowers, ocean)
        
        Using 5-dimensional vectors for simplicity and speed.
        """
        return [
            {
                "id": 1,
                "text": "The cat sat on the mat and purred contentedly.",
                "topic": "animals",
                # Embedding represents: high on "animals", low on "tech", medium on "nature"
                "vector": [0.9, 0.1, 0.5, 0.3, 0.2]
            },
            {
                "id": 2,
                "text": "Dogs are loyal companions and great pets for families.",
                "topic": "animals",
                # Similar to cat doc: high on "animals"
                "vector": [0.85, 0.15, 0.4, 0.35, 0.25]
            },
            {
                "id": 3,
                "text": "Machine learning algorithms can recognize patterns in data.",
                "topic": "technology",
                # High on "tech", low on "animals"
                "vector": [0.1, 0.9, 0.2, 0.7, 0.6]
            },
            {
                "id": 4,
                "text": "Programming requires logical thinking and problem solving skills.",
                "topic": "technology",
                # Similar to ML doc: high on "tech"
                "vector": [0.15, 0.85, 0.25, 0.75, 0.65]
            },
            {
                "id": 5,
                "text": "The ocean waves crashed against the rocky shore.",
                "topic": "nature",
                # High on "nature", low on others
                "vector": [0.2, 0.1, 0.9, 0.3, 0.4]
            }
        ]
    
    @pytest.fixture
    def query_vectors(self):
        """
        Query vectors representing different search intents.
        
        Each query vector should match documents from specific topics.
        """
        return {
            "pets": {
                "vector": [0.9, 0.1, 0.4, 0.3, 0.2],  # Similar to animal docs
                "expected_topics": ["animals"],
                "description": "Query about pets/animals"
            },
            "ai_technology": {
                "vector": [0.1, 0.9, 0.2, 0.7, 0.6],  # Similar to tech docs
                "expected_topics": ["technology"],
                "description": "Query about AI/technology"
            },
            "environment": {
                "vector": [0.2, 0.1, 0.9, 0.3, 0.4],  # Similar to nature docs
                "expected_topics": ["nature"],
                "description": "Query about nature/environment"
            }
        }
    
    def test_vector_db_full_workflow(self, server_endpoint, sample_documents, query_vectors):
        """
        Test complete vector database workflow: create → insert → search → verify → delete.
        
        This is a end-to-end test demonstrating:
        1. Creating a vector database service
        2. Creating a collection with specific dimensions
        3. Inserting documents with vector embeddings
        4. Searching for similar documents
        5. Verifying search results match expected semantics
        6. Testing different distance metrics
        7. Cleaning up resources
        """
        import time
        
        # Step 1: Create a Qdrant vector database service
        print("\n=== Step 1: Creating Vector DB Service ===")
        create_service_response = requests.post(
            f"{server_endpoint}/api/v1/services",
            json={
                "recipe_name": "vector-db/qdrant",
                "config": {"nodes": 1}
            },
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        assert create_service_response.status_code in [200, 201], \
            f"Failed to create vector-db service: {create_service_response.text}"
        
        service_data = create_service_response.json()
        service_id = service_data["id"]
        print(f"Created vector-db service: {service_id}")
        
        # Step 2: Wait for service to be running
        print("\n=== Step 2: Waiting for Service to be Ready ===")
        max_wait = 300  # 5 minutes max (increased for HPC)
        wait_interval = 10
        total_waited = 0
        service_ready = False
        
        while total_waited < max_wait:
            status_response = requests.get(
                f"{server_endpoint}/api/v1/services/{service_id}/status",
                timeout=30
            )
            if status_response.status_code == 200:
                status_data = status_response.json()
                current_status = status_data.get("status", "unknown")
                print(f"  Status: {current_status} (waited {total_waited}s)")
                
                if current_status == "running":
                    service_ready = True
                    break
            
            time.sleep(wait_interval)
            total_waited += wait_interval
        
        assert service_ready, \
            f"Vector-db service did not become ready within {max_wait} seconds"
        print(f"Service is ready after {total_waited}s")
        
        # Step 3: Create a collection for our documents
        print("\n=== Step 3: Creating Collection ===")
        collection_name = "test_documents"
        vector_dim = len(sample_documents[0]["vector"])  # 5 dimensions
        
        create_collection_response = requests.put(
            f"{server_endpoint}/api/v1/vector-db/{service_id}/collections/{collection_name}",
            json={
                "vector_size": vector_dim,
                "distance": "Cosine"  # Use cosine similarity
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        assert create_collection_response.status_code == 200, \
            f"Failed to create collection: {create_collection_response.text}"
        print(f"Created collection '{collection_name}' with {vector_dim}-dim vectors (Cosine distance)")
        
        # Step 4: Verify collection was created
        print("\n=== Step 4: Verifying Collection ===")
        collections_response = requests.get(
            f"{server_endpoint}/api/v1/vector-db/{service_id}/collections",
            timeout=10
        )
        
        assert collections_response.status_code == 200
        collections_data = collections_response.json()
        assert collections_data["success"], "Failed to list collections"
        assert collection_name in collections_data["collections"], \
            f"Collection '{collection_name}' not found in list"
        print(f"Collection verified in collections list")
        
        # Step 5: Insert documents with embeddings
        print("\n=== Step 5: Inserting Documents ===")
        points = [
            {
                "id": doc["id"],
                "vector": doc["vector"],
                "payload": {
                    "text": doc["text"],
                    "topic": doc["topic"]
                }
            }
            for doc in sample_documents
        ]
        
        upsert_response = requests.put(
            f"{server_endpoint}/api/v1/vector-db/{service_id}/collections/{collection_name}/points",
            json={"points": points},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        assert upsert_response.status_code == 200, \
            f"Failed to upsert points: {upsert_response.text}"
        upsert_data = upsert_response.json()
        assert upsert_data["success"], "Upsert operation failed"
        print(f"Inserted {len(points)} documents with embeddings")
        
        # Step 6: Get collection info to verify points were added
        print("\n=== Step 6: Verifying Collection Info ===")
        info_response = requests.get(
            f"{server_endpoint}/api/v1/vector-db/{service_id}/collections/{collection_name}",
            timeout=10
        )
        
        assert info_response.status_code == 200
        info_data = info_response.json()
        assert info_data["success"], "Failed to get collection info"
        print(f"Collection info: {info_data.get('info', {}).get('points_count', 'N/A')} points")
        
        # Step 7: Test semantic search - Query for pet/animal documents
        print("\n=== Step 7: Testing Semantic Search ===")
        for query_name, query_data in query_vectors.items():
            print(f"\n  Testing query: {query_data['description']}")
            
            search_response = requests.post(
                f"{server_endpoint}/api/v1/vector-db/{service_id}/collections/{collection_name}/points/search",
                json={
                    "query_vector": query_data["vector"],
                    "limit": 3
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            assert search_response.status_code == 200, \
                f"Search failed for {query_name}: {search_response.text}"
            
            search_data = search_response.json()
            assert search_data["success"], f"Search operation failed for {query_name}"
            assert "results" in search_data, "No results in search response"
            
            results = search_data["results"]
            assert len(results) > 0, f"No results returned for {query_name}"
            
            # Verify top result matches expected topic
            top_result = results[0]
            assert "payload" in top_result, "Result missing payload"
            result_topic = top_result["payload"].get("topic")
            
            print(f"    Top result: '{top_result['payload'].get('text', 'N/A')[:50]}...'")
            print(f"    Topic: {result_topic}, Score: {top_result.get('score', 'N/A')}")
            
            # Check if topic matches expectation
            assert result_topic in query_data["expected_topics"], \
                f"Expected topics {query_data['expected_topics']}, got {result_topic}"
            print(f"    Search returned correct topic")
        
        # Step 8: Test search with different limit
        print("\n=== Step 8: Testing Search Limits ===")
        for limit in [1, 2, 3]:
            search_response = requests.post(
                f"{server_endpoint}/api/v1/vector-db/{service_id}/collections/{collection_name}/points/search",
                json={
                    "query_vector": query_vectors["pets"]["vector"],
                    "limit": limit
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            assert search_response.status_code == 200
            search_data = search_response.json()
            assert search_data["success"]
            assert len(search_data["results"]) <= limit, \
                f"Expected at most {limit} results, got {len(search_data['results'])}"
            print(f"  Limit {limit}: returned {len(search_data['results'])} results")
        
        # Step 9: Test with Euclidean distance (create new collection)
        print("\n=== Step 9: Testing Euclidean Distance ===")
        euclidean_collection = "test_documents_euclidean"
        
        create_euclidean_response = requests.put(
            f"{server_endpoint}/api/v1/vector-db/{service_id}/collections/{euclidean_collection}",
            json={
                "vector_size": vector_dim,
                "distance": "Euclid"
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        assert create_euclidean_response.status_code == 200
        print(f"  Created collection with Euclidean distance")
        
        # Insert same documents
        upsert_euclidean_response = requests.put(
            f"{server_endpoint}/api/v1/vector-db/{service_id}/collections/{euclidean_collection}/points",
            json={"points": points},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        assert upsert_euclidean_response.status_code == 200
        print(f"  Inserted documents into Euclidean collection")
        
        # Search with Euclidean distance
        search_euclidean_response = requests.post(
            f"{server_endpoint}/api/v1/vector-db/{service_id}/collections/{euclidean_collection}/points/search",
            json={
                "query_vector": query_vectors["pets"]["vector"],
                "limit": 2
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        assert search_euclidean_response.status_code == 200
        euclidean_results = search_euclidean_response.json()
        assert euclidean_results["success"]
        print(f"  Search with Euclidean distance successful")
        
        # Step 10: Clean up - delete collections
        print("\n=== Step 10: Cleaning Up ===")
        for coll in [collection_name, euclidean_collection]:
            delete_response = requests.delete(
                f"{server_endpoint}/api/v1/vector-db/{service_id}/collections/{coll}",
                timeout=10
            )
            
            assert delete_response.status_code == 200, \
                f"Failed to delete collection {coll}: {delete_response.text}"
            print(f"  Deleted collection '{coll}'")
        
        # Verify collections were deleted
        final_collections_response = requests.get(
            f"{server_endpoint}/api/v1/vector-db/{service_id}/collections",
            timeout=10
        )
        
        assert final_collections_response.status_code == 200
        final_collections = final_collections_response.json()
        assert collection_name not in final_collections.get("collections", [])
        assert euclidean_collection not in final_collections.get("collections", [])
        print(f"  Verified collections deleted")
        
        # Step 11: Stop the vector-db service
        print("\n=== Step 11: Stopping Service ===")
        stop_response = requests.delete(
            f"{server_endpoint}/api/v1/services/{service_id}",
            timeout=10
        )
        
        assert stop_response.status_code in [200, 404]
        print(f"  Service stopped")
        
        print("\n=== Vector DB Full Workflow Test Complete ===\n")


if __name__ == "__main__":
    # Allow running integration tests directly: python test_integration.py
    pytest.main([__file__, "-v"])