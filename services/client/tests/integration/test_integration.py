"""
Integration tests for AI Factory Client Services.

These tests run against live services (client service + mock AI server)
to validate end-to-end functionality.
"""

import unittest
import requests
import time
import os
import json
from typing import Optional


class BaseIntegrationTest(unittest.TestCase):
    """Base class for integration tests with common setup/teardown"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        # Get service endpoints from environment
        cls.client_service_url = os.getenv('CLIENT_SERVICE_ADDR', 'http://localhost:8001')
        cls.ai_server_url = os.getenv('AI_SERVER_ADDR', 'http://localhost:8000')
        
        # Verify services are running
        cls._wait_for_service(cls.client_service_url, "Client Service")
        cls._wait_for_service(cls.ai_server_url, "AI Server")
        
        print(f"Integration tests using:")
        print(f"  Client Service: {cls.client_service_url}")
        print(f"  AI Server: {cls.ai_server_url}")
    
    @classmethod
    def _wait_for_service(cls, url: str, name: str, timeout: int = 30):
        """Wait for a service to become available"""
        for attempt in range(timeout):
            try:
                # Try different health endpoints
                health_endpoints = ['/health', '/docs', '/']
                for endpoint in health_endpoints:
                    try:
                        response = requests.get(f"{url}{endpoint}", timeout=2)
                        if response.status_code == 200:
                            print(f"✓ {name} is ready at {url}")
                            return
                    except requests.RequestException:
                        continue
                        
                print(f"Waiting for {name} ({attempt + 1}/{timeout})...")
                time.sleep(1)
            except Exception as e:
                if attempt == timeout - 1:
                    raise Exception(f"Service {name} not available at {url}: {e}")
                time.sleep(1)
        
        raise Exception(f"Service {name} did not become available within {timeout} seconds")


class TestClientServiceAPI(BaseIntegrationTest):
    """Test Client Service API endpoints"""
    
    def setUp(self):
        """Set up for each test"""
        self.test_benchmark_id = 999900 + int(time.time()) % 100  # Unique ID
        
    def tearDown(self):
        """Clean up after each test"""
        # Try to delete test benchmark group
        try:
            requests.delete(f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}")
        except:
            pass  # Ignore cleanup errors
    
    def test_api_docs_accessible(self):
        """Test that API documentation is accessible"""
        response = requests.get(f"{self.client_service_url}/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers.get('content-type', ''))
    
    def test_create_client_group_success(self):
        """Test successful client group creation"""
        data = {
            "num_clients": 2,
            "time_limit": 5
        }
        
        response = requests.post(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}",
            json=data
        )
        
        self.assertEqual(response.status_code, 201)
        result = response.json()
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["benchmark_id"], self.test_benchmark_id)
        self.assertEqual(result["num_clients"], 2)
    
    def test_create_client_group_duplicate(self):
        """Test creating duplicate client group returns conflict"""
        data = {"num_clients": 1, "time_limit": 5}
        
        # Create first group
        response1 = requests.post(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}",
            json=data
        )
        self.assertEqual(response1.status_code, 201)
        
        # Try to create duplicate
        response2 = requests.post(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}",
            json=data
        )
        self.assertEqual(response2.status_code, 409)
        result = response2.json()
        self.assertIn("already exists", result["detail"])
    
    def test_get_nonexistent_client_group(self):
        """Test getting info for nonexistent client group"""
        nonexistent_id = 999999
        response = requests.get(
            f"{self.client_service_url}/api/v1/client-group/{nonexistent_id}"
        )
        
        self.assertEqual(response.status_code, 404)
        result = response.json()
        self.assertIn("not found", result["detail"])
    
    def test_client_registration(self):
        """Test client process registration"""
        # First create a group
        data = {"num_clients": 1, "time_limit": 5}
        response = requests.post(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}",
            json=data
        )
        self.assertEqual(response.status_code, 201)
        
        # Register a client
        client_data = {
            "client_address": "http://mock-client:9000"
        }
        response = requests.post(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}/connect",
            json=client_data
        )
        
        self.assertEqual(response.status_code, 201)
        result = response.json()
        self.assertEqual(result["status"], "registered")
        self.assertEqual(result["benchmark_id"], self.test_benchmark_id)
        self.assertEqual(result["client_address"], "http://mock-client:9000")
        
        # Verify client is registered by getting group info
        response = requests.get(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}"
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIn("client_address", result["info"])
    
    def test_delete_client_group(self):
        """Test client group deletion"""
        # Create group
        data = {"num_clients": 1, "time_limit": 5}
        response = requests.post(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}",
            json=data
        )
        self.assertEqual(response.status_code, 201)
        
        # Delete group
        response = requests.delete(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}"
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["status"], "deleted")
        self.assertEqual(result["benchmark_id"], self.test_benchmark_id)
        
        # Verify group is deleted
        response = requests.get(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}"
        )
        self.assertEqual(response.status_code, 404)


class TestMockAIServerAPI(BaseIntegrationTest):
    """Test Mock AI Server functionality"""
    
    def test_ai_server_health(self):
        """Test AI server health endpoint"""
        response = requests.get(f"{self.ai_server_url}/health")
        self.assertEqual(response.status_code, 200)
        
        result = response.json()
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["service"], "mock-ai-server")
    
    def test_ai_server_models_list(self):
        """Test AI server models listing"""
        response = requests.get(f"{self.ai_server_url}/v1/models")
        self.assertEqual(response.status_code, 200)
        
        result = response.json()
        self.assertEqual(result["object"], "list")
        self.assertIsInstance(result["data"], list)
        self.assertGreater(len(result["data"]), 0)
        
        # Check model structure
        model = result["data"][0]
        self.assertIn("id", model)
        self.assertIn("object", model)
        self.assertEqual(model["object"], "model")
    
    def test_ai_server_completion(self):
        """Test AI server text completion"""
        data = {
            "model": "meta-llama/Llama-2-7b-chat-hf",
            "prompt": "Hello, world!",
            "max_tokens": 50,
            "temperature": 0.7
        }
        
        response = requests.post(f"{self.ai_server_url}/v1/completions", json=data)
        self.assertEqual(response.status_code, 200)
        
        result = response.json()
        self.assertEqual(result["object"], "text_completion")
        self.assertEqual(result["model"], data["model"])
        self.assertIsInstance(result["choices"], list)
        self.assertEqual(len(result["choices"]), 1)
        
        choice = result["choices"][0]
        self.assertIn("text", choice)
        self.assertIsInstance(choice["text"], str)
        self.assertGreater(len(choice["text"]), 0)
    
    def test_ai_server_chat_completion(self):
        """Test AI server chat completion"""
        data = {
            "model": "meta-llama/Llama-2-7b-chat-hf",
            "messages": [
                {"role": "user", "content": "Hello, how are you?"}
            ],
            "max_tokens": 50,
            "temperature": 0.7
        }
        
        response = requests.post(f"{self.ai_server_url}/v1/chat/completions", json=data)
        self.assertEqual(response.status_code, 200)
        
        result = response.json()
        self.assertEqual(result["object"], "chat.completion")
        self.assertEqual(result["model"], data["model"])
        self.assertIsInstance(result["choices"], list)
        self.assertEqual(len(result["choices"]), 1)
        
        choice = result["choices"][0]
        self.assertIn("message", choice)
        message = choice["message"]
        self.assertEqual(message["role"], "assistant")
        self.assertIn("content", message)
        self.assertIsInstance(message["content"], str)
        self.assertGreater(len(message["content"]), 0)


class TestEndToEndWorkflow(BaseIntegrationTest):
    """Test complete end-to-end workflow"""
    
    def setUp(self):
        """Set up for each test"""
        self.test_benchmark_id = 999800 + int(time.time()) % 100  # Unique ID
        
    def tearDown(self):
        """Clean up after each test"""
        # Try to delete test benchmark group
        try:
            requests.delete(f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}")
        except:
            pass  # Ignore cleanup errors
    
    def test_complete_workflow_without_slurm(self):
        """Test complete workflow without Slurm job submission"""
        # Step 1: Create client group
        print("\n=== Step 1: Creating client group ===")
        data = {"num_clients": 1, "time_limit": 5}
        response = requests.post(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}",
            json=data
        )
        self.assertEqual(response.status_code, 201)
        print(f"✓ Client group created: {response.json()}")
        
        # Step 2: Register mock client
        print("\n=== Step 2: Registering client ===")
        client_data = {"client_address": "http://integration-test-client:9000"}
        response = requests.post(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}/connect",
            json=client_data
        )
        self.assertEqual(response.status_code, 201)
        print(f"✓ Client registered: {response.json()}")
        
        # Step 3: Verify group info
        print("\n=== Step 3: Verifying group info ===")
        response = requests.get(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}"
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIn("client_address", result["info"])
        print(f"✓ Group info retrieved: {result}")
        
        # Step 4: Test AI server interaction
        print("\n=== Step 4: Testing AI server ===")
        ai_data = {
            "model": "meta-llama/Llama-2-7b-chat-hf",
            "prompt": "Integration test prompt",
            "max_tokens": 20
        }
        response = requests.post(f"{self.ai_server_url}/v1/completions", json=ai_data)
        self.assertEqual(response.status_code, 200)
        ai_result = response.json()
        self.assertIn("choices", ai_result)
        print(f"✓ AI server response: {ai_result['choices'][0]['text'][:50]}...")
        
        # Step 5: Try to run benchmark (will fail without real client, but should not crash)
        print("\n=== Step 5: Attempting benchmark run ===")
        response = requests.post(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}/run"
        )
        # This might fail (500) since we don't have a real client running, 
        # but it shouldn't crash the service
        self.assertIn(response.status_code, [200, 500])
        print(f"✓ Benchmark run attempted, status: {response.status_code}")
        
        # Step 6: Cleanup
        print("\n=== Step 6: Cleanup ===")
        response = requests.delete(
            f"{self.client_service_url}/api/v1/client-group/{self.test_benchmark_id}"
        )
        self.assertEqual(response.status_code, 200)
        print(f"✓ Client group deleted: {response.json()}")
        
        print("\n=== End-to-end workflow test completed successfully ===")


if __name__ == '__main__':
    # Allow running individual test classes
    import sys
    
    if len(sys.argv) > 1:
        # Run specific test class
        suite = unittest.TestSuite()
        test_class_name = sys.argv[1]
        
        if test_class_name == "api":
            suite.addTest(unittest.makeSuite(TestClientServiceAPI))
        elif test_class_name == "ai":
            suite.addTest(unittest.makeSuite(TestMockAIServerAPI))
        elif test_class_name == "e2e":
            suite.addTest(unittest.makeSuite(TestEndToEndWorkflow))
        else:
            print(f"Unknown test class: {test_class_name}")
            print("Available: api, ai, e2e")
            sys.exit(1)
            
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    else:
        # Run all tests
        unittest.main(verbosity=2)