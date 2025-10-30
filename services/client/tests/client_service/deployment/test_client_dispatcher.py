"""
Unit tests for client_dispatcher module
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from client_service.deployment.client_dispatcher import AbstractClientDispatcher, SlurmClientDispatcher


class TestAbstractClientDispatcher(unittest.TestCase):
    """Test the abstract base class"""
    
    def test_abstract_dispatcher_creation(self):
        """Test creating abstract dispatcher"""
        dispatcher = AbstractClientDispatcher()
        self.assertIsInstance(dispatcher, AbstractClientDispatcher)
    
    def test_dispatch_method_exists(self):
        """Test that dispatch method exists (base implementation does nothing)"""
        dispatcher = AbstractClientDispatcher()
        
        # Should not raise an exception
        dispatcher.dispatch(num_clients=5, benchmark_id=123, time=10)
    
    def test_dispatch_method_signature(self):
        """Test dispatch method signature"""
        dispatcher = AbstractClientDispatcher()
        
        # Test with various parameter combinations
        dispatcher.dispatch(1, 1)  # minimal parameters
        dispatcher.dispatch(5, 123, 15)  # all parameters
        dispatcher.dispatch(num_clients=3, benchmark_id=456, time=20)  # keyword args


class TestSlurmClientDispatcher(unittest.TestCase):
    """Test the Slurm implementation"""
    
    @patch('client_service.deployment.client_dispatcher.SlurmConfig')
    def test_initialization(self, mock_slurm_config_class):
        """Test SlurmClientDispatcher initialization"""
        # Setup mock
        mock_slurm_config = Mock()
        mock_slurm_config_class.tmp_load_default.return_value = mock_slurm_config
        
        server_addr = "http://server:8000"
        client_service_addr = "http://client-service:8001"
        
        # Test without container mode
        dispatcher = SlurmClientDispatcher(server_addr, client_service_addr)
        
        self.assertEqual(dispatcher._server_addr, server_addr)
        self.assertEqual(dispatcher._client_service_addr, client_service_addr)
        self.assertFalse(dispatcher._use_container)
    
    @patch('client_service.deployment.client_dispatcher.SlurmConfig')
    def test_initialization_with_container(self, mock_slurm_config_class):
        """Test SlurmClientDispatcher initialization with container mode"""
        # Setup mock
        mock_slurm_config = Mock()
        mock_slurm_config_class.tmp_load_default.return_value = mock_slurm_config
        
        server_addr = "http://server:8000"
        client_service_addr = "http://client-service:8001"
        
        # Test with container mode
        dispatcher = SlurmClientDispatcher(
            server_addr, client_service_addr, use_container=True
        )
        
        self.assertEqual(dispatcher._server_addr, server_addr)
        self.assertEqual(dispatcher._client_service_addr, client_service_addr)
        self.assertTrue(dispatcher._use_container)
    
    @patch('client_service.deployment.client_dispatcher.SlurmConfig')
    def test_initialization_with_custom_slurm_config(self, mock_slurm_config_class):
        """Test SlurmClientDispatcher initialization with custom slurm config"""
        # Setup mocks
        default_config = Mock()
        custom_config = Mock()
        mock_slurm_config_class.tmp_load_default.return_value = default_config
        
        # Test with custom config
        dispatcher = SlurmClientDispatcher(
            "http://server:8000", 
            "http://client-service:8001",
            slurm_config=custom_config
        )
        
        # Should use the provided config, not the default
        self.assertEqual(dispatcher._server_addr, "http://server:8000")
        self.assertEqual(dispatcher._client_service_addr, "http://client-service:8001")
    
    # @patch('client_service.deployment.client_dispatcher.requests.post')
    # @patch('client_service.deployment.client_dispatcher.SlurmConfig')
    # def test_dispatch_success(self, mock_slurm_config_class, mock_post):
    #     """Test successful job dispatch"""
    #     # Setup mock config
    #     mock_slurm_config = Mock()
    #     mock_slurm_config.url = "https://slurm.example.com"
    #     mock_slurm_config.api_ver = "v0.0.39"
    #     mock_slurm_config.user_name = "testuser"
    #     mock_slurm_config.token = "test-token"
    #     mock_slurm_config.account = "test-account"
    #     mock_slurm_config_class.tmp_load_default.return_value = mock_slurm_config
        
    #     # Setup mock response
    #     mock_response = Mock()
    #     mock_response.status_code = 200
    #     mock_response.json.return_value = {"job_id": 12345, "status": "submitted"}
    #     mock_response.text = "Success"
    #     mock_post.return_value = mock_response
        
    #     # Create dispatcher
    #     dispatcher = SlurmClientDispatcher("http://server:8000", "http://client-service:8001")
        
    #     # Test dispatch
    #     dispatcher.dispatch(num_clients=3, benchmark_id=123, time=10)
        
    #     # Verify token refresh was called
    #     mock_slurm_config.refresh_token_if_needed.assert_called_once_with(threshold_seconds=300)
        
    #     # Verify request was made correctly
    #     mock_post.assert_called_once()
    #     call_args = mock_post.call_args
        
    #     # Check URL
    #     expected_url = "https://slurm.example.com/slurm/v0.0.39/job/submit"
    #     self.assertEqual(call_args[0][0], expected_url)
        
    #     # Check headers
    #     expected_headers = {
    #         'X-SLURM-USER-NAME': 'testuser',
    #         'X-SLURM-USER-TOKEN': 'test-token'
    #     }
    #     self.assertEqual(call_args[1]['headers'], expected_headers)
        
    #     # Check payload structure
    #     payload = call_args[1]['json']
    #     self.assertIn('script', payload)
    #     self.assertIn('job', payload)
        
    #     # Check script contains expected command (without container flag)
    #     expected_script_content = "./client_service/deployment/start_client.sh 3 http://server:8000 http://client-service:8001 123"
    #     self.assertIn(expected_script_content, payload['script'])
        
    #     # Check job parameters
    #     job = payload['job']
    #     self.assertEqual(job['qos'], 'default')
    #     self.assertEqual(job['time_limit'], 10)
    #     self.assertEqual(job['account'], 'test-account')
    #     self.assertIn('testuser', job['current_working_directory'])
    #     self.assertIn('testuser', job['standard_output'])
    #     self.assertIn('testuser', job['standard_error'])
    #     self.assertEqual(job['environment']['USER'], 'testuser')
    
    # @patch('client_service.deployment.client_dispatcher.requests.post')
    # @patch('client_service.deployment.client_dispatcher.SlurmConfig')
    # def test_dispatch_with_container_flag(self, mock_slurm_config_class, mock_post):
    #     """Test dispatch with container mode enabled"""
    #     # Setup mock config
    #     mock_slurm_config = Mock()
    #     mock_slurm_config.url = "https://slurm.example.com"
    #     mock_slurm_config.api_ver = "v0.0.39"
    #     mock_slurm_config.user_name = "testuser"
    #     mock_slurm_config.token = "test-token"
    #     mock_slurm_config.account = "test-account"
    #     mock_slurm_config_class.tmp_load_default.return_value = mock_slurm_config
        
    #     # Setup mock response
    #     mock_response = Mock()
    #     mock_response.status_code = 200
    #     mock_response.json.return_value = {"job_id": 12345}
    #     mock_post.return_value = mock_response
        
    #     # Create dispatcher with container mode
    #     dispatcher = SlurmClientDispatcher(
    #         "http://server:8000", 
    #         "http://client-service:8001", 
    #         use_container=True
    #     )
        
    #     # Test dispatch
    #     dispatcher.dispatch(num_clients=2, benchmark_id=456, time=15)
        
    #     # Verify request was made
    #     mock_post.assert_called_once()
    #     payload = mock_post.call_args[1]['json']
        
    #     # Check script contains container flag
    #     expected_script_content = "./client_service/deployment/start_client.sh 2 http://server:8000 http://client-service:8001 456 --container"
    #     self.assertIn(expected_script_content, payload['script'])
    
    # @patch('client_service.deployment.client_dispatcher.requests.post')
    # @patch('client_service.deployment.client_dispatcher.SlurmConfig')
    # def test_dispatch_failure(self, mock_slurm_config_class, mock_post):
    #     """Test dispatch when submission fails"""
    #     # Setup mock config
    #     mock_slurm_config = Mock()
    #     mock_slurm_config.url = "https://slurm.example.com"
    #     mock_slurm_config.api_ver = "v0.0.39"
    #     mock_slurm_config.user_name = "testuser"
    #     mock_slurm_config.token = "test-token"
    #     mock_slurm_config.account = "test-account"
    #     mock_slurm_config_class.tmp_load_default.return_value = mock_slurm_config
        
    #     # Setup mock response for failure
    #     mock_response = Mock()
    #     mock_response.status_code = 400
    #     mock_response.text = "Bad Request"
    #     mock_response.json.return_value = {"error": "Invalid job parameters"}
    #     mock_post.return_value = mock_response
        
    #     # Create dispatcher
    #     dispatcher = SlurmClientDispatcher("http://server:8000", "http://client-service:8001")
        
    #     # Test dispatch (should not raise exception, just log error)
    #     dispatcher.dispatch(num_clients=1, benchmark_id=789, time=5)
        
    #     # Verify request was still made
    #     mock_post.assert_called_once()
    
    # @patch('client_service.deployment.client_dispatcher.requests.post')
    # @patch('client_service.deployment.client_dispatcher.SlurmConfig')
    # def test_dispatch_with_default_time(self, mock_slurm_config_class, mock_post):
    #     """Test dispatch with default time parameter"""
    #     # Setup mocks
    #     mock_slurm_config = Mock()
    #     mock_slurm_config.url = "https://slurm.example.com"
    #     mock_slurm_config.api_ver = "v0.0.39"
    #     mock_slurm_config.user_name = "testuser"
    #     mock_slurm_config.token = "test-token"
    #     mock_slurm_config.account = "test-account"
    #     mock_slurm_config_class.tmp_load_default.return_value = mock_slurm_config
        
    #     mock_response = Mock()
    #     mock_response.status_code = 200
    #     mock_response.json.return_value = {"job_id": 12345}
    #     mock_post.return_value = mock_response
        
    #     # Create dispatcher
    #     dispatcher = SlurmClientDispatcher("http://server:8000", "http://client-service:8001")
        
    #     # Test dispatch without time parameter (should use default of 5)
    #     dispatcher.dispatch(num_clients=1, benchmark_id=123)
        
    #     # Verify time_limit in payload is 5 (default)
    #     payload = mock_post.call_args[1]['json']
    #     self.assertEqual(payload['job']['time_limit'], 5)
    
    # @patch('client_service.deployment.client_dispatcher.requests.post')
    # @patch('client_service.deployment.client_dispatcher.SlurmConfig')
    # def test_dispatch_request_exception(self, mock_slurm_config_class, mock_post):
    #     """Test dispatch when request raises exception"""
    #     # Setup mock config
    #     mock_slurm_config = Mock()
    #     mock_slurm_config_class.tmp_load_default.return_value = mock_slurm_config
        
    #     # Setup mock to raise exception
    #     mock_post.side_effect = Exception("Connection error")
        
    #     # Create dispatcher
    #     dispatcher = SlurmClientDispatcher("http://server:8000", "http://client-service:8001")
        
    #     # Test dispatch should raise the exception
    #     with self.assertRaises(Exception) as context:
    #         dispatcher.dispatch(num_clients=1, benchmark_id=123)
        
    #     self.assertEqual(str(context.exception), "Connection error")
    
    @patch('client_service.deployment.client_dispatcher.SlurmConfig')
    def test_inheritance(self, mock_slurm_config_class):
        """Test that SlurmClientDispatcher inherits from AbstractClientDispatcher"""
        mock_slurm_config = Mock()
        mock_slurm_config_class.tmp_load_default.return_value = mock_slurm_config
        
        dispatcher = SlurmClientDispatcher("http://server:8000", "http://client-service:8001")
        
        self.assertIsInstance(dispatcher, AbstractClientDispatcher)
        self.assertIsInstance(dispatcher, SlurmClientDispatcher)


if __name__ == '__main__':
    unittest.main()