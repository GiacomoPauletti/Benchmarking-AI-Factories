"""
Unit tests for ClientGroup class (client_service)
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import time

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from client_service.client_manager.client_group import ClientGroup


class TestClientGroup(unittest.TestCase):
    
    @patch('client_service.client_manager.client_group.SlurmClientDispatcher')
    def test_client_group_initialization_success(self, mock_dispatcher_class):
        """Test successful ClientGroup initialization"""
        # Setup mock dispatcher
        mock_dispatcher = Mock()
        mock_dispatcher_class.return_value = mock_dispatcher
        
        # Create ClientGroup
        benchmark_id = 123
        num_clients = 5
        server_addr = "http://server:8000"
        client_service_addr = "http://client-service:8001"
        time_limit = 10
        
        group = ClientGroup(
            benchmark_id=benchmark_id,
            num_clients=num_clients,
            server_addr=server_addr,
            client_service_addr=client_service_addr,
            time_limit=time_limit
        )
        
        # Verify initialization
        self.assertEqual(group.get_benchmark_id(), benchmark_id)
        self.assertEqual(group.get_num_clients(), num_clients)
        self.assertIsNone(group.get_client_address())
        self.assertFalse(group.has_client_registered())
        self.assertIsInstance(group.get_created_at(), float)
        self.assertTrue(group.get_created_at() > 0)
        
        # Verify dispatcher was created and called
        mock_dispatcher_class.assert_called_once_with(
            server_addr, client_service_addr, use_container=False
        )
        mock_dispatcher.dispatch.assert_called_once_with(
            num_clients, benchmark_id, time_limit
        )
    
    @patch('client_service.client_manager.client_group.SlurmClientDispatcher')
    def test_client_group_initialization_with_container(self, mock_dispatcher_class):
        """Test ClientGroup initialization with container mode"""
        # Setup mock dispatcher
        mock_dispatcher = Mock()
        mock_dispatcher_class.return_value = mock_dispatcher
        
        # Create ClientGroup with container mode
        group = ClientGroup(
            benchmark_id=456,
            num_clients=3,
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001",
            time_limit=15,
            use_container=True
        )
        
        # Verify dispatcher was created with container mode
        mock_dispatcher_class.assert_called_once_with(
            "http://server:8000", "http://client-service:8001", use_container=True
        )
    
    @patch('client_service.client_manager.client_group.SlurmClientDispatcher')
    def test_client_group_initialization_default_time_limit(self, mock_dispatcher_class):
        """Test ClientGroup initialization with default time limit"""
        # Setup mock dispatcher
        mock_dispatcher = Mock()
        mock_dispatcher_class.return_value = mock_dispatcher
        
        # Create ClientGroup without time_limit (should use default)
        group = ClientGroup(
            benchmark_id=789,
            num_clients=2,
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001"
        )
        
        # Verify dispatcher was called with default time_limit
        mock_dispatcher.dispatch.assert_called_once_with(2, 789, 5)
    
    @patch('client_service.client_manager.client_group.SlurmClientDispatcher')
    def test_client_group_initialization_dispatch_fails(self, mock_dispatcher_class):
        """Test ClientGroup initialization when dispatch fails"""
        # Setup mock dispatcher to raise exception
        mock_dispatcher = Mock()
        mock_dispatcher.dispatch.side_effect = Exception("Dispatch failed")
        mock_dispatcher_class.return_value = mock_dispatcher
        
        # Creating ClientGroup should raise exception
        with self.assertRaises(Exception) as context:
            ClientGroup(
                benchmark_id=999,
                num_clients=1,
                server_addr="http://server:8000",
                client_service_addr="http://client-service:8001"
            )
        
        self.assertEqual(str(context.exception), "Dispatch failed")
    
    @patch('client_service.client_manager.client_group.SlurmClientDispatcher')
    def test_register_client_address(self, mock_dispatcher_class):
        """Test client address registration"""
        # Setup mock dispatcher
        mock_dispatcher = Mock()
        mock_dispatcher_class.return_value = mock_dispatcher
        
        # Create ClientGroup
        group = ClientGroup(
            benchmark_id=123,
            num_clients=2,
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001"
        )
        
        # Register client address
        client_address = "http://client:9000"
        result = group.register_client_address(client_address)
        
        # Verify registration
        self.assertTrue(result)
        self.assertEqual(group.get_client_address(), client_address)
        self.assertTrue(group.has_client_registered())
    
    @patch('client_service.client_manager.client_group.SlurmClientDispatcher')
    def test_register_client_address_with_trailing_slash(self, mock_dispatcher_class):
        """Test client address registration removes trailing slash"""
        # Setup mock dispatcher
        mock_dispatcher = Mock()
        mock_dispatcher_class.return_value = mock_dispatcher
        
        # Create ClientGroup
        group = ClientGroup(
            benchmark_id=123,
            num_clients=2,
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001"
        )
        
        # Register client address with trailing slash
        client_address_with_slash = "http://client:9000/"
        expected_address = "http://client:9000"
        
        result = group.register_client_address(client_address_with_slash)
        
        # Verify trailing slash was removed
        self.assertTrue(result)
        self.assertEqual(group.get_client_address(), expected_address)
    
    @patch('client_service.client_manager.client_group.SlurmClientDispatcher')
    def test_get_info(self, mock_dispatcher_class):
        """Test get_info method"""
        # Setup mock dispatcher
        mock_dispatcher = Mock()
        mock_dispatcher_class.return_value = mock_dispatcher
        
        # Create ClientGroup
        group = ClientGroup(
            benchmark_id=456,
            num_clients=3,
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001"
        )
        
        # Get info before client registration
        info = group.get_info()
        expected_info = {
            "num_clients": 3,
            "client_address": None,
            "created_at": group.get_created_at()
        }
        self.assertEqual(info, expected_info)
        
        # Register client and get info again
        client_address = "http://client:9000"
        group.register_client_address(client_address)
        
        info = group.get_info()
        expected_info = {
            "num_clients": 3,
            "client_address": client_address,
            "created_at": group.get_created_at()
        }
        self.assertEqual(info, expected_info)
    
    @patch('client_service.client_manager.client_group.SlurmClientDispatcher')
    def test_all_getters(self, mock_dispatcher_class):
        """Test all getter methods"""
        # Setup mock dispatcher
        mock_dispatcher = Mock()
        mock_dispatcher_class.return_value = mock_dispatcher
        
        # Create ClientGroup
        benchmark_id = 789
        num_clients = 4
        server_addr = "http://server:8000"
        client_service_addr = "http://client-service:8001"
        
        group = ClientGroup(
            benchmark_id=benchmark_id,
            num_clients=num_clients,
            server_addr=server_addr,
            client_service_addr=client_service_addr
        )
        
        # Test all getters
        self.assertEqual(group.get_benchmark_id(), benchmark_id)
        self.assertEqual(group.get_num_clients(), num_clients)
        self.assertIsNone(group.get_client_address())
        self.assertFalse(group.has_client_registered())
        
        # Test created_at is reasonable
        created_at = group.get_created_at()
        self.assertIsInstance(created_at, float)
        current_time = time.time()
        self.assertTrue(abs(current_time - created_at) < 1.0)  # Should be very recent
    
    @patch('client_service.client_manager.client_group.SlurmClientDispatcher')
    def test_client_registration_status_changes(self, mock_dispatcher_class):
        """Test that registration status changes correctly"""
        # Setup mock dispatcher
        mock_dispatcher = Mock()
        mock_dispatcher_class.return_value = mock_dispatcher
        
        # Create ClientGroup
        group = ClientGroup(
            benchmark_id=123,
            num_clients=1,
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001"
        )
        
        # Initially no client registered
        self.assertFalse(group.has_client_registered())
        self.assertIsNone(group.get_client_address())
        
        # Register client
        group.register_client_address("http://client:9000")
        
        # Now client is registered
        self.assertTrue(group.has_client_registered())
        self.assertIsNotNone(group.get_client_address())
    
    @patch('client_service.client_manager.client_group.SlurmClientDispatcher')
    def test_multiple_client_address_registrations(self, mock_dispatcher_class):
        """Test multiple client address registrations (should overwrite)"""
        # Setup mock dispatcher
        mock_dispatcher = Mock()
        mock_dispatcher_class.return_value = mock_dispatcher
        
        # Create ClientGroup
        group = ClientGroup(
            benchmark_id=123,
            num_clients=1,
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001"
        )
        
        # Register first address
        first_address = "http://client1:9000"
        group.register_client_address(first_address)
        self.assertEqual(group.get_client_address(), first_address)
        
        # Register second address (should overwrite)
        second_address = "http://client2:9000"
        group.register_client_address(second_address)
        self.assertEqual(group.get_client_address(), second_address)


if __name__ == '__main__':
    unittest.main()
