"""
Unit tests for VLLMClient class
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import threading
import time
import requests

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from client.client import VLLMClient
from client.client_observer import ClientObserver


class TestVLLMClient(unittest.TestCase):
    
    def setUp(self):
        """Reset static variables before each test"""
        VLLMClient.num_clients = 0
        VLLMClient._service_id = None
        VLLMClient._server_base_url = None
    
    def tearDown(self):
        """Clean up after each test"""
        VLLMClient.num_clients = 0
        VLLMClient._service_id = None
        VLLMClient._server_base_url = None
    
    def test_client_initialization(self):
        """Test client initialization and ID assignment"""
        client1 = VLLMClient()
        self.assertEqual(client1.client_id, 0)
        self.assertEqual(VLLMClient.num_clients, 1)
        self.assertEqual(client1._recipe, "inference/vllm")
        self.assertEqual(len(client1._observers), 0)
        
        client2 = VLLMClient(recipe="custom/recipe")
        self.assertEqual(client2.client_id, 1)
        self.assertEqual(VLLMClient.num_clients, 2)
        self.assertEqual(client2._recipe, "custom/recipe")
    
    def test_client_initialization_with_custom_recipe(self):
        """Test client initialization with custom recipe"""
        custom_recipe = "inference/custom"
        client = VLLMClient(recipe=custom_recipe)
        self.assertEqual(client._recipe, custom_recipe)
    
    def test_multiple_clients_unique_ids(self):
        """Test that multiple clients get unique IDs"""
        clients = [VLLMClient() for _ in range(5)]
        expected_ids = list(range(5))
        actual_ids = [client.client_id for client in clients]
        self.assertEqual(actual_ids, expected_ids)
        self.assertEqual(VLLMClient.num_clients, 5)
    
    @patch('requests.post')
    def test_setup_benchmark_success(self, mock_post):
        """Test successful benchmark setup"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "test-service-123"}
        mock_post.return_value = mock_response
        
        server_url = "http://localhost:8000"
        service_id = VLLMClient.setup_benchmark(server_url)
        
        # Verify the result
        self.assertEqual(service_id, "test-service-123")
        self.assertEqual(VLLMClient._service_id, "test-service-123")
        self.assertEqual(VLLMClient._server_base_url, server_url)
        
        # Verify the request was made correctly
        mock_post.assert_called_once_with(
            f"{server_url}/api/v1/services",
            json={
                "recipe_name": "inference/vllm",
                "config": {"nodes": 1, "cpus": 2, "memory": "8G"}
            }
        )
    
    @patch('requests.post')
    def test_setup_benchmark_http_error(self, mock_post):
        """Test benchmark setup with HTTP error response"""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        server_url = "http://localhost:8000"
        service_id = VLLMClient.setup_benchmark(server_url)
        
        # Verify the result
        self.assertIsNone(service_id)
        self.assertIsNone(VLLMClient._service_id)
        self.assertEqual(VLLMClient._server_base_url, server_url)
    
    @patch('requests.post')
    def test_setup_benchmark_request_exception(self, mock_post):
        """Test benchmark setup with request exception"""
        # Mock request exception
        mock_post.side_effect = requests.ConnectionError("Connection failed")
        
        server_url = "http://localhost:8000"
        service_id = VLLMClient.setup_benchmark(server_url)
        
        # Verify the result
        self.assertIsNone(service_id)
        self.assertIsNone(VLLMClient._service_id)
        self.assertEqual(VLLMClient._server_base_url, server_url)
    
    @patch('requests.post')
    def test_setup_benchmark_no_service_id_in_response(self, mock_post):
        """Test benchmark setup when response doesn't contain service ID"""
        # Mock response without service ID
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "created"}
        mock_post.return_value = mock_response
        
        server_url = "http://localhost:8000"
        service_id = VLLMClient.setup_benchmark(server_url)
        
        # Verify the result
        self.assertIsNone(service_id)
        self.assertIsNone(VLLMClient._service_id)
        self.assertEqual(VLLMClient._server_base_url, server_url)
    
    def test_subscribe_observer(self):
        """Test subscribing observers to client"""
        client = VLLMClient()
        observer1 = Mock(spec=ClientObserver)
        observer2 = Mock(spec=ClientObserver)
        
        client.subscribe(observer1)
        self.assertEqual(len(client._observers), 1)
        self.assertIn(observer1, client._observers)
        
        client.subscribe(observer2)
        self.assertEqual(len(client._observers), 2)
        self.assertIn(observer2, client._observers)
    
    @patch('requests.post')
    def test_run_without_setup(self, mock_post):
        """Test running client without benchmark setup"""
        client = VLLMClient()
        
        # Ensure no setup is done
        VLLMClient._service_id = None
        VLLMClient._server_base_url = None
        
        # Run should return early without making requests
        client.run()
        
        # Verify no HTTP requests were made
        mock_post.assert_not_called()
    
    @patch('requests.post')
    def test_run_with_setup_success(self, mock_post):
        """Test running client with successful setup and prompt request"""
        # Setup benchmark first
        VLLMClient._service_id = "test-service-123"
        VLLMClient._server_base_url = "http://localhost:8000"
        
        # Mock successful prompt response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "test response"}
        mock_post.return_value = mock_response
        
        # Create client with observer
        client = VLLMClient()
        observer = Mock(spec=ClientObserver)
        client.subscribe(observer)
        
        # Run the client
        client.run()
        
        # Verify the prompt request was made
        mock_post.assert_called_once_with(
            "http://localhost:8000/api/v1/vllm/test-service-123/prompt",
            json={
                "prompt": "How many r has the word 'apple'?",
                "max_tokens": 500,
                "temperature": 0.7
            }
        )
        
        # Verify observer was notified
        observer.update.assert_called_once_with({})
    
    @patch('requests.post')
    def test_run_with_setup_http_error(self, mock_post):
        """Test running client with HTTP error during prompt request"""
        # Setup benchmark first
        VLLMClient._service_id = "test-service-123"
        VLLMClient._server_base_url = "http://localhost:8000"
        
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_post.return_value = mock_response
        
        # Create client with observer
        client = VLLMClient()
        observer = Mock(spec=ClientObserver)
        client.subscribe(observer)
        
        # Run the client
        client.run()
        
        # Verify the prompt request was made despite error
        mock_post.assert_called_once()
        
        # Verify observer was still notified
        observer.update.assert_called_once_with({})
    
    @patch('requests.post')
    def test_run_with_setup_request_exception(self, mock_post):
        """Test running client with request exception during prompt request"""
        # Setup benchmark first
        VLLMClient._service_id = "test-service-123"
        VLLMClient._server_base_url = "http://localhost:8000"
        
        # Mock request exception
        mock_post.side_effect = requests.ConnectionError("Connection failed")
        
        # Create client with observer
        client = VLLMClient()
        observer = Mock(spec=ClientObserver)
        client.subscribe(observer)
        
        # Run the client
        client.run()
        
        # Verify the prompt request was attempted
        mock_post.assert_called_once()
        
        # Verify observer was still notified
        observer.update.assert_called_once_with({})
    
    def test_multiple_observers_notification(self):
        """Test that all observers are notified when client runs"""
        # Setup benchmark first
        VLLMClient._service_id = "test-service-123"
        VLLMClient._server_base_url = "http://localhost:8000"
        
        with patch('requests.post') as mock_post:
            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"response": "test"}
            mock_post.return_value = mock_response
            
            # Create client with multiple observers
            client = VLLMClient()
            observer1 = Mock(spec=ClientObserver)
            observer2 = Mock(spec=ClientObserver)
            observer3 = Mock(spec=ClientObserver)
            
            client.subscribe(observer1)
            client.subscribe(observer2)
            client.subscribe(observer3)
            
            # Run the client
            client.run()
            
            # Verify all observers were notified
            observer1.update.assert_called_once_with({})
            observer2.update.assert_called_once_with({})
            observer3.update.assert_called_once_with({})
    
    def test_static_variables_shared_across_instances(self):
        """Test that static variables are shared across all client instances"""
        client1 = VLLMClient()
        client2 = VLLMClient()
        
        # Setup benchmark using class method
        VLLMClient._service_id = "shared-service"
        VLLMClient._server_base_url = "http://shared:8000"
        
        # Both clients should see the same static values
        self.assertEqual(VLLMClient._service_id, "shared-service")
        self.assertEqual(VLLMClient._server_base_url, "http://shared:8000")
        
        # Changing through one client affects all
        VLLMClient._service_id = "new-service"
        self.assertEqual(VLLMClient._service_id, "new-service")


if __name__ == '__main__':
    unittest.main()