"""
Unit tests for frontend_router API
"""

import unittest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from client_service.api.frontend_router import frontend_router, AddGroupPayload
from client_service.client_manager.client_manager import ClientManagerResponseStatus


class TestFrontendRouter(unittest.TestCase):
    
    def setUp(self):
        """Set up test client"""
        self.app = FastAPI()
        self.app.include_router(frontend_router)
        self.client = TestClient(self.app)
    
    @patch('client_service.api.frontend_router.client_manager')
    def test_add_client_group_success(self, mock_client_manager):
        """Test successful client group creation"""
        # Setup mock
        mock_client_manager.add_client_group.return_value = ClientManagerResponseStatus.OK
        
        # Prepare payload
        payload = {"num_clients": 5, "time_limit": 10}
        
        # Make request
        response = self.client.post("/client-group/123", json=payload)
        
        # Verify response
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "created")
        self.assertEqual(data["benchmark_id"], 123)
        self.assertEqual(data["num_clients"], 5)
        
        # Verify mock was called correctly
        mock_client_manager.add_client_group.assert_called_once_with(123, 5, 10)
    
    @patch('client_service.api.frontend_router.client_manager')
    def test_add_client_group_default_time_limit(self, mock_client_manager):
        """Test client group creation with default time limit"""
        # Setup mock
        mock_client_manager.add_client_group.return_value = ClientManagerResponseStatus.OK
        
        # Prepare payload without time_limit
        payload = {"num_clients": 3}
        
        # Make request
        response = self.client.post("/client-group/456", json=payload)
        
        # Verify response
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "created")
        self.assertEqual(data["benchmark_id"], 456)
        self.assertEqual(data["num_clients"], 3)
        
        # Verify mock was called with default time_limit
        mock_client_manager.add_client_group.assert_called_once_with(456, 3, 5)
    
    @patch('client_service.api.frontend_router.client_manager')
    def test_add_client_group_already_exists(self, mock_client_manager):
        """Test client group creation when group already exists"""
        # Setup mock to return error
        mock_client_manager.add_client_group.return_value = ClientManagerResponseStatus.ERROR
        
        # Prepare payload
        payload = {"num_clients": 2}
        
        # Make request
        response = self.client.post("/client-group/789", json=payload)
        
        # Verify response
        self.assertEqual(response.status_code, 409)  # Conflict
        data = response.json()
        self.assertEqual(data["detail"], "Group already exists")
    
    @patch('client_service.api.frontend_router.client_manager')
    def test_delete_client_group_success(self, mock_client_manager):
        """Test successful client group deletion"""
        # Make request
        response = self.client.delete("/client-group/123")
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "deleted")
        self.assertEqual(data["benchmark_id"], 123)
        
        # Verify mock was called correctly
        mock_client_manager.remove_client_group.assert_called_once_with(123)
    
    @patch('client_service.api.frontend_router.client_manager')
    def test_run_client_group_success(self, mock_client_manager):
        """Test successful client group run"""
        # Setup mock
        mock_results = [
            {"client_process": "http://client1:9000", "status_code": 200, "body": "started"},
            {"client_process": "http://client2:9000", "status_code": 200, "body": "started"}
        ]
        mock_client_manager.run_client_group.return_value = mock_results
        
        # Make request
        response = self.client.post("/client-group/123/run")
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "dispatched")
        self.assertEqual(data["benchmark_id"], 123)
        self.assertEqual(data["results"], mock_results)
        
        # Verify mock was called correctly
        mock_client_manager.run_client_group.assert_called_once_with(123)
    
    @patch('client_service.api.frontend_router.client_manager')
    def test_run_client_group_not_found(self, mock_client_manager):
        """Test client group run when group doesn't exist"""
        # Setup mock to raise ValueError
        mock_client_manager.run_client_group.side_effect = ValueError("Unknown benchmark id 999")
        
        # Make request
        response = self.client.post("/client-group/999/run")
        
        # Verify response
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["detail"], "Unknown benchmark id 999")
    
    @patch('client_service.api.frontend_router.client_manager')
    def test_run_client_group_internal_error(self, mock_client_manager):
        """Test client group run when internal error occurs"""
        # Setup mock to raise generic exception
        mock_client_manager.run_client_group.side_effect = Exception("Internal error")
        
        # Make request
        response = self.client.post("/client-group/123/run")
        
        # Verify response
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data["detail"], "Internal error")
    
    @patch('client_service.api.frontend_router.client_manager')
    def test_get_client_group_info_success(self, mock_client_manager):
        """Test successful client group info retrieval"""
        # Setup mock
        mock_info = {
            "benchmark_id": 123,
            "num_clients": 3,
            "client_address": "http://client:9000",
            "created_at": 1634567890.123
        }
        mock_client_manager.get_group_info.return_value = mock_info
        
        # Make request
        response = self.client.get("/client-group/123")
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["benchmark_id"], 123)
        self.assertEqual(data["info"], mock_info)
        
        # Verify mock was called correctly
        mock_client_manager.get_group_info.assert_called_once_with(123)
    
    @patch('client_service.api.frontend_router.client_manager')
    def test_get_client_group_info_not_found(self, mock_client_manager):
        """Test client group info when group doesn't exist"""
        # Setup mock to return None
        mock_client_manager.get_group_info.return_value = None
        
        # Make request
        response = self.client.get("/client-group/999")
        
        # Verify response
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["detail"], "Benchmark id not found")
    
    def test_add_group_payload_model(self):
        """Test AddGroupPayload model validation"""
        # Valid data with all fields
        valid_data = {"num_clients": 5, "time_limit": 10}
        payload = AddGroupPayload(**valid_data)
        self.assertEqual(payload.num_clients, 5)
        self.assertEqual(payload.time_limit, 10)
        
        # Valid data with default time_limit
        minimal_data = {"num_clients": 3}
        payload = AddGroupPayload(**minimal_data)
        self.assertEqual(payload.num_clients, 3)
        self.assertEqual(payload.time_limit, 5)  # Default value
    
    def test_router_endpoints_exist(self):
        """Test that all expected endpoints are available"""
        # Test all endpoints with mock data
        with patch('client_service.api.frontend_router.client_manager') as mock_manager:
            mock_manager.add_client_group.return_value = ClientManagerResponseStatus.OK
            mock_manager.get_group_info.return_value = {"info": "test"}
            mock_manager.run_client_group.return_value = []
            
            # Test POST /client-group/{id}
            response = self.client.post("/client-group/1", json={"num_clients": 1})
            self.assertEqual(response.status_code, 201)
            
            # Test DELETE /client-group/{id}
            response = self.client.delete("/client-group/1")
            self.assertEqual(response.status_code, 200)
            
            # Test POST /client-group/{id}/run
            response = self.client.post("/client-group/1/run")
            self.assertEqual(response.status_code, 200)
            
            # Test GET /client-group/{id}
            response = self.client.get("/client-group/1")
            self.assertEqual(response.status_code, 200)
    
    def test_invalid_payload_validation(self):
        """Test request validation with invalid payloads"""
        # Missing required field
        response = self.client.post("/client-group/1", json={})
        self.assertEqual(response.status_code, 422)  # Unprocessable Entity
        
        # Invalid data types
        response = self.client.post("/client-group/1", json={"num_clients": "not_a_number"})
        self.assertEqual(response.status_code, 422)
        
        # Negative values (if validation is added)
        response = self.client.post("/client-group/1", json={"num_clients": -1})
        # Note: This might pass depending on validation rules
    
    def test_invalid_benchmark_id_types(self):
        """Test with invalid benchmark ID types"""
        with patch('client_service.api.frontend_router.client_manager'):
            # String instead of int
            response = self.client.post("/client-group/not_a_number", json={"num_clients": 1})
            self.assertEqual(response.status_code, 422)


class TestFrontendRouterIntegration(unittest.TestCase):
    """Integration tests for frontend router"""
    
    def setUp(self):
        """Set up test client"""
        self.app = FastAPI()
        self.app.include_router(frontend_router)
        self.client = TestClient(self.app)
    
    @patch('client_service.api.frontend_router.client_manager')
    def test_full_client_group_lifecycle(self, mock_client_manager):
        """Test complete client group lifecycle"""
        # Setup mocks
        mock_client_manager.add_client_group.return_value = ClientManagerResponseStatus.OK
        mock_info = {
            "benchmark_id": 123,
            "num_clients": 2,
            "client_address": "http://client:9000"
        }
        mock_client_manager.get_group_info.return_value = mock_info
        mock_client_manager.run_client_group.return_value = [{"status": "started"}]
        
        # 1. Create client group
        create_response = self.client.post("/client-group/123", json={"num_clients": 2})
        self.assertEqual(create_response.status_code, 201)
        
        # 2. Get info
        info_response = self.client.get("/client-group/123")
        self.assertEqual(info_response.status_code, 200)
        
        # 3. Run group
        run_response = self.client.post("/client-group/123/run")
        self.assertEqual(run_response.status_code, 200)
        
        # 4. Delete group
        delete_response = self.client.delete("/client-group/123")
        self.assertEqual(delete_response.status_code, 200)
        
        # Verify all operations were called
        mock_client_manager.add_client_group.assert_called_once_with(123, 2, 5)
        mock_client_manager.get_group_info.assert_called_once_with(123)
        mock_client_manager.run_client_group.assert_called_once_with(123)
        mock_client_manager.remove_client_group.assert_called_once_with(123)


if __name__ == '__main__':
    unittest.main()
