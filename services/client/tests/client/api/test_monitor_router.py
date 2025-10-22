"""
Unit tests for monitor_router API
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from client.api.monitor_router import monitor_proxy_router, ObserverPayload, ObserverResponse, set_clients


class TestMonitorRouter(unittest.TestCase):
    
    def setUp(self):
        """Set up test client"""
        self.app = FastAPI()
        self.app.include_router(monitor_proxy_router)
        self.client = TestClient(self.app)
    
    @patch('client.api.monitor_router.ClientGroup')
    @patch('client.api.monitor_router.MonitorProxy')
    @patch('client.api.monitor_router.UpdatePreferences')
    def test_add_observer_success(self, mock_update_prefs_class, mock_monitor_proxy_class, mock_client_group_class):
        """Test successful observer addition"""
        # Setup mocks
        mock_client_group = Mock()
        mock_client_group.clients = [Mock(), Mock()]
        mock_client_group.num_clients = 2
        mock_client_group.register_observer.return_value = True
        mock_client_group_class.return_value = mock_client_group
        
        mock_update_prefs = Mock()
        mock_update_prefs_class.return_value = mock_update_prefs
        
        mock_monitor_proxy = Mock()
        mock_monitor_proxy_class.return_value = mock_monitor_proxy
        
        # Prepare payload
        payload = {
            "ip_address": "192.168.1.100",
            "port": "8080",
            "update_preferences": {"frequency": "10s"}
        }
        
        # Make request
        response = self.client.post("/observer", json=payload)
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "observer_added")
        
        # Verify mocks were called correctly
        mock_update_prefs_class.assert_called_once()
        mock_monitor_proxy_class.assert_called_once_with("192.168.1.100", "8080", mock_update_prefs)
        mock_client_group.register_observer.assert_called_once_with(mock_monitor_proxy)
    
    @patch('client.api.monitor_router.ClientGroup')
    def test_add_observer_no_clients(self, mock_client_group_class):
        """Test observer addition when no clients available"""
        # Setup mock with no clients
        mock_client_group = Mock()
        mock_client_group.clients = []
        mock_client_group_class.return_value = mock_client_group
        
        # Prepare payload
        payload = {
            "ip_address": "192.168.1.100",
            "port": "8080"
        }
        
        # Make request
        response = self.client.post("/observer", json=payload)
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "error")
    
    @patch('client.api.monitor_router.ClientGroup')
    @patch('client.api.monitor_router.MonitorProxy')
    @patch('client.api.monitor_router.UpdatePreferences')
    def test_add_observer_registration_fails(self, mock_update_prefs_class, mock_monitor_proxy_class, mock_client_group_class):
        """Test observer addition when registration fails"""
        # Setup mocks
        mock_client_group = Mock()
        mock_client_group.clients = [Mock()]
        mock_client_group.register_observer.return_value = False  # Registration fails
        mock_client_group_class.return_value = mock_client_group
        
        mock_update_prefs = Mock()
        mock_update_prefs_class.return_value = mock_update_prefs
        
        mock_monitor_proxy = Mock()
        mock_monitor_proxy_class.return_value = mock_monitor_proxy
        
        # Prepare payload
        payload = {
            "ip_address": "192.168.1.100",
            "port": "8080"
        }
        
        # Make request
        response = self.client.post("/observer", json=payload)
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "error")
    
    @patch('client.api.monitor_router.ClientGroup')
    @patch('client.api.monitor_router.MonitorProxy')
    @patch('client.api.monitor_router.UpdatePreferences')
    def test_add_observer_exception(self, mock_update_prefs_class, mock_monitor_proxy_class, mock_client_group_class):
        """Test observer addition when exception occurs"""
        # Setup mocks
        mock_client_group = Mock()
        mock_client_group.clients = [Mock()]
        mock_client_group_class.return_value = mock_client_group
        
        # Make UpdatePreferences raise an exception
        mock_update_prefs_class.side_effect = Exception("UpdatePreferences error")
        
        # Prepare payload
        payload = {
            "ip_address": "192.168.1.100",
            "port": "8080"
        }
        
        # Make request
        response = self.client.post("/observer", json=payload)
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "error")
    
    @patch('client.api.monitor_router.ClientGroup')
    def test_set_clients_with_configured_group(self, mock_client_group_class):
        """Test set_clients with already configured ClientGroup"""
        # Setup mock with configured group
        mock_client_group = Mock()
        mock_client_group.benchmark_id = 123  # Already configured
        mock_client_group_class.return_value = mock_client_group
        
        # Test clients
        test_clients = [Mock(), Mock(), Mock()]
        
        # Call set_clients
        set_clients(test_clients)
        
        # Verify clients were set
        self.assertEqual(mock_client_group._clients, test_clients)
    
    @patch('client.api.monitor_router.ClientGroup')
    def test_set_clients_with_unconfigured_group(self, mock_client_group_class):
        """Test set_clients with unconfigured ClientGroup"""
        # Setup mock with unconfigured group
        mock_client_group = Mock()
        mock_client_group.benchmark_id = None  # Not configured
        mock_client_group_class.return_value = mock_client_group
        
        # Test clients
        test_clients = [Mock(), Mock()]
        
        # Call set_clients
        set_clients(test_clients)
        
        # Verify clients were set
        self.assertEqual(mock_client_group._clients, test_clients)
    
    def test_observer_payload_model(self):
        """Test ObserverPayload model validation"""
        # Valid data with all fields
        valid_data = {
            "ip_address": "192.168.1.100",
            "port": "8080",
            "update_preferences": {"frequency": "10s", "format": "json"}
        }
        payload = ObserverPayload(**valid_data)
        self.assertEqual(payload.ip_address, "192.168.1.100")
        self.assertEqual(payload.port, "8080")
        self.assertEqual(payload.update_preferences, {"frequency": "10s", "format": "json"})
        
        # Valid data with minimal fields (update_preferences has default)
        minimal_data = {
            "ip_address": "10.0.0.1",
            "port": "9000"
        }
        payload = ObserverPayload(**minimal_data)
        self.assertEqual(payload.ip_address, "10.0.0.1")
        self.assertEqual(payload.port, "9000")
        self.assertEqual(payload.update_preferences, {})  # Default empty dict
    
    def test_observer_response_model(self):
        """Test ObserverResponse model validation"""
        # Valid data
        valid_data = {"status": "observer_added"}
        response = ObserverResponse(**valid_data)
        self.assertEqual(response.status, "observer_added")
        
        # Test different status values
        for status in ["observer_added", "error", "success"]:
            response = ObserverResponse(status=status)
            self.assertEqual(response.status, status)
    
    def test_router_endpoints_exist(self):
        """Test that all expected endpoints exist"""
        routes = [route.path for route in self.app.routes]
        
        # Check that our endpoints are registered
        self.assertIn("/observer", routes)
    
    def test_router_methods(self):
        """Test that endpoints support correct HTTP methods"""
        # Test POST /observer
        payload = {"ip_address": "127.0.0.1", "port": "8080"}
        response = self.client.post("/observer", json=payload)
        self.assertNotEqual(response.status_code, 405)  # Method not allowed
        
        # Test unsupported methods
        response = self.client.get("/observer")
        self.assertEqual(response.status_code, 405)  # Method not allowed
        
        response = self.client.put("/observer", json=payload)
        self.assertEqual(response.status_code, 405)  # Method not allowed


class TestMonitorRouterIntegration(unittest.TestCase):
    """Integration tests for monitor router"""
    
    def setUp(self):
        """Set up test client"""
        self.app = FastAPI()
        self.app.include_router(monitor_proxy_router)
        self.client = TestClient(self.app)
    
    @patch('client.api.monitor_router.ClientGroup')
    @patch('client.api.monitor_router.MonitorProxy')
    @patch('client.api.monitor_router.UpdatePreferences')
    def test_multiple_observers_workflow(self, mock_update_prefs_class, mock_monitor_proxy_class, mock_client_group_class):
        """Test adding multiple observers"""
        # Setup mocks
        mock_client_group = Mock()
        mock_client_group.clients = [Mock(), Mock(), Mock()]
        mock_client_group.num_clients = 3
        mock_client_group.register_observer.return_value = True
        mock_client_group_class.return_value = mock_client_group
        
        mock_update_prefs_class.return_value = Mock()
        mock_monitor_proxy_class.return_value = Mock()
        
        # Observer payloads
        observers = [
            {"ip_address": "192.168.1.100", "port": "8080"},
            {"ip_address": "192.168.1.101", "port": "8081"},
            {"ip_address": "192.168.1.102", "port": "8082"}
        ]
        
        # Add all observers
        for observer_data in observers:
            response = self.client.post("/observer", json=observer_data)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "observer_added")
        
        # Verify all observers were registered
        self.assertEqual(mock_client_group.register_observer.call_count, 3)
        self.assertEqual(mock_monitor_proxy_class.call_count, 3)
    
    def test_set_clients_function_workflow(self):
        """Test set_clients function in workflow context"""
        with patch('client.api.monitor_router.ClientGroup') as mock_client_group_class:
            mock_client_group = Mock()
            mock_client_group.benchmark_id = None
            mock_client_group_class.return_value = mock_client_group
            
            # Create test clients
            test_clients = [Mock() for _ in range(4)]
            
            # Set clients
            set_clients(test_clients)
            
            # Verify clients were set correctly
            self.assertEqual(mock_client_group._clients, test_clients)
            
            # Now configure group and set again
            mock_client_group.benchmark_id = 456
            new_clients = [Mock() for _ in range(2)]
            
            set_clients(new_clients)
            
            # Verify new clients were set
            self.assertEqual(mock_client_group._clients, new_clients)


if __name__ == '__main__':
    unittest.main()