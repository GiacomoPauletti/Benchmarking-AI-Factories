"""
Unit tests for client_service_router API
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from client.api.client_service_router import client_service_router, RunResponse, StatusResponse


class TestClientServiceRouter(unittest.TestCase):
    
    def setUp(self):
        """Set up test client"""
        self.app = FastAPI()
        self.app.include_router(client_service_router)
        self.client = TestClient(self.app)
    
    @patch('client.api.client_service_router.ClientGroup')
    @patch('client.api.client_service_router.VLLMClient')
    def test_run_clients_success(self, mock_vllm_client, mock_client_group_class):
        """Test successful client run"""
        # Setup mocks
        mock_client_group = Mock()
        mock_client_group.clients = [Mock(), Mock(), Mock()]  # 3 clients
        mock_client_group.num_clients = 3
        mock_client_group.benchmark_id = 123
        mock_client_group.server_addr = "http://server:8000"
        mock_client_group.run_all_clients.return_value = 3
        mock_client_group_class.return_value = mock_client_group
        
        mock_vllm_client.setup_benchmark.return_value = "service-123"
        
        # Make request
        response = self.client.post("/run")
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "started")
        self.assertEqual(data["num_clients"], 3)
        
        # Verify mocks were called correctly
        mock_vllm_client.setup_benchmark.assert_called_once_with("http://server:8000")
        mock_client_group.run_all_clients.assert_called_once()
    
    @patch('client.api.client_service_router.ClientGroup')
    def test_run_clients_no_clients(self, mock_client_group_class):
        """Test run with no clients available"""
        # Setup mock with no clients
        mock_client_group = Mock()
        mock_client_group.clients = []
        mock_client_group.num_clients = 0
        mock_client_group_class.return_value = mock_client_group
        
        # Make request
        response = self.client.post("/run")
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["num_clients"], 0)
    
    @patch('client.api.client_service_router.ClientGroup')
    @patch('client.api.client_service_router.VLLMClient')
    def test_run_clients_setup_benchmark_fails(self, mock_vllm_client, mock_client_group_class):
        """Test run when benchmark setup fails"""
        # Setup mocks
        mock_client_group = Mock()
        mock_client_group.clients = [Mock(), Mock()]
        mock_client_group.server_addr = "http://server:8000"
        mock_client_group_class.return_value = mock_client_group
        
        # Setup benchmark fails
        mock_vllm_client.setup_benchmark.return_value = None
        
        # Make request
        response = self.client.post("/run")
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["num_clients"], 0)
        
        # Verify setup was attempted
        mock_vllm_client.setup_benchmark.assert_called_once_with("http://server:8000")
        # run_all_clients should not be called
        mock_client_group.run_all_clients.assert_not_called()
    
    @patch('client.api.client_service_router.ClientGroup')
    def test_run_clients_no_server_address(self, mock_client_group_class):
        """Test run when server address is not configured"""
        # Setup mock with no server address
        mock_client_group = Mock()
        mock_client_group.clients = [Mock(), Mock()]
        mock_client_group.server_addr = None
        mock_client_group_class.return_value = mock_client_group
        
        # Make request
        response = self.client.post("/run")
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["num_clients"], 0)
    
    @patch('client.api.client_service_router.ClientGroup')
    def test_get_status_success(self, mock_client_group_class):
        """Test successful status retrieval"""
        # Setup mock
        mock_client_group = Mock()
        status_data = {
            "benchmark_id": 456,
            "num_clients": 5,
            "server_addr": "http://server:8000",
            "client_service_addr": "http://client-service:8001",
            "local_address": "http://local:9000",
            "created_at": 1634567890.123
        }
        mock_client_group.get_status.return_value = status_data
        mock_client_group_class.return_value = mock_client_group
        
        # Make request
        response = self.client.get("/status")
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        expected_response = {
            "benchmark_id": 456,
            "num_clients": 5,
            "server_addr": "http://server:8000",
            "client_service_addr": "http://client-service:8001",
            "local_address": "http://local:9000",
            "created_at": 1634567890.123
        }
        
        self.assertEqual(data, expected_response)
        mock_client_group.get_status.assert_called_once()
    
    def test_run_response_model(self):
        """Test RunResponse model validation"""
        # Valid data
        valid_data = {"status": "started", "num_clients": 3}
        response = RunResponse(**valid_data)
        self.assertEqual(response.status, "started")
        self.assertEqual(response.num_clients, 3)
        
        # Test serialization
        self.assertEqual(response.dict(), valid_data)
    
    def test_status_response_model(self):
        """Test StatusResponse model validation"""
        # Valid data
        valid_data = {
            "benchmark_id": 123,
            "num_clients": 2,
            "server_addr": "http://server:8000",
            "client_service_addr": "http://client-service:8001",
            "local_address": "http://local:9000",
            "created_at": 1634567890.123
        }
        
        response = StatusResponse(**valid_data)
        self.assertEqual(response.benchmark_id, 123)
        self.assertEqual(response.num_clients, 2)
        self.assertEqual(response.server_addr, "http://server:8000")
        self.assertEqual(response.client_service_addr, "http://client-service:8001")
        self.assertEqual(response.local_address, "http://local:9000")
        self.assertEqual(response.created_at, 1634567890.123)
        
        # Test serialization
        self.assertEqual(response.dict(), valid_data)
    
    def test_router_endpoints_exist(self):
        """Test that all expected endpoints exist"""
        routes = [route.path for route in self.app.routes]
        
        # Check that our endpoints are registered
        self.assertIn("/run", routes)
        self.assertIn("/status", routes)
    
    @patch('client.api.client_service_router.ClientGroup')
    def test_router_methods(self, mock_client_group_class):
        """Test that endpoints support correct HTTP methods"""
        # Setup mock for successful responses
        mock_client_group = Mock()
        mock_client_group.clients = [Mock()]
        mock_client_group.num_clients = 1
        mock_client_group.server_addr = "http://server:8000"
        mock_client_group.run_all_clients.return_value = 1
        
        status_data = {
            "benchmark_id": 123,
            "num_clients": 1,
            "server_addr": "http://server:8000",
            "client_service_addr": "http://client-service:8001",
            "local_address": "http://local:9000",
            "created_at": 1634567890.123
        }
        mock_client_group.get_status.return_value = status_data
        mock_client_group_class.return_value = mock_client_group
        
        # Test POST /run
        with patch('client.api.client_service_router.VLLMClient') as mock_vllm_client:
            mock_vllm_client.setup_benchmark.return_value = "service-123"
            response = self.client.post("/run")
            self.assertNotEqual(response.status_code, 405)  # Method not allowed
        
        # Test GET /status
        response = self.client.get("/status")
        self.assertNotEqual(response.status_code, 405)  # Method not allowed
        
        # Test unsupported methods
        response = self.client.get("/run")
        self.assertEqual(response.status_code, 405)  # Method not allowed
        
        response = self.client.post("/status")
        self.assertEqual(response.status_code, 405)  # Method not allowed


class TestClientServiceRouterIntegration(unittest.TestCase):
    """Integration tests for client service router"""
    
    def setUp(self):
        """Set up test client"""
        self.app = FastAPI()
        self.app.include_router(client_service_router)
        self.client = TestClient(self.app)
    
    @patch('client.api.client_service_router.ClientGroup')
    @patch('client.api.client_service_router.VLLMClient')
    def test_full_run_workflow(self, mock_vllm_client, mock_client_group_class):
        """Test complete workflow from status check to run"""
        # Setup mocks
        mock_client_group = Mock()
        mock_client_group.clients = [Mock(), Mock()]
        mock_client_group.num_clients = 2
        mock_client_group.benchmark_id = 789
        mock_client_group.server_addr = "http://test-server:8000"
        mock_client_group.run_all_clients.return_value = 2
        
        status_data = {
            "benchmark_id": 789,
            "num_clients": 2,
            "server_addr": "http://test-server:8000",
            "client_service_addr": "http://test-client-service:8001",
            "local_address": "http://test-local:9000",
            "created_at": 1634567890.123
        }
        mock_client_group.get_status.return_value = status_data
        mock_client_group_class.return_value = mock_client_group
        
        mock_vllm_client.setup_benchmark.return_value = "test-service-id"
        
        # First check status
        status_response = self.client.get("/status")
        self.assertEqual(status_response.status_code, 200)
        status_data_response = status_response.json()
        self.assertEqual(status_data_response["benchmark_id"], 789)
        self.assertEqual(status_data_response["num_clients"], 2)
        
        # Then run clients
        run_response = self.client.post("/run")
        self.assertEqual(run_response.status_code, 200)
        run_data = run_response.json()
        self.assertEqual(run_data["status"], "started")
        self.assertEqual(run_data["num_clients"], 2)
        
        # Verify all calls were made
        mock_client_group.get_status.assert_called_once()
        mock_vllm_client.setup_benchmark.assert_called_once_with("http://test-server:8000")
        mock_client_group.run_all_clients.assert_called_once()


if __name__ == '__main__':
    # Note: This test requires pytest-asyncio for async testing
    unittest.main()