"""
Unit tests for ClientManager class
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import time
import threading

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from client_service.client_manager.client_manager import ClientManager, ClientManagerResponseStatus, CMResponse


class TestClientManager(unittest.TestCase):
    
    def setUp(self):
        """Reset ClientManager singleton before each test"""
        ClientManager._instance = None
    
    def tearDown(self):
        """Clean up after each test"""
        ClientManager._instance = None
    
    def test_singleton_pattern(self):
        """Test that ClientManager follows singleton pattern"""
        manager1 = ClientManager()
        manager2 = ClientManager()
        
        # Should be the same instance
        self.assertIs(manager1, manager2)
        self.assertEqual(id(manager1), id(manager2))
    
    def test_singleton_thread_safety(self):
        """Test singleton thread safety"""
        instances = []
        
        def create_instance():
            instances.append(ClientManager())
        
        # Create multiple threads trying to create instances
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=create_instance)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All instances should be the same
        self.assertEqual(len(instances), 10)
        for instance in instances:
            self.assertIs(instance, instances[0])
    
    def test_initialization_once_only(self):
        """Test that initialization only happens once"""
        manager1 = ClientManager()
        
        # Check initial state
        self.assertEqual(len(manager1.list_groups()), 0)
        self.assertEqual(manager1._server_addr, "http://localhost:8002")
        self.assertEqual(manager1._client_service_addr, "http://localhost:8001")
        self.assertFalse(manager1._use_container)
        
        # Second creation should not re-initialize
        manager2 = ClientManager()
        
        # Should be same instance
        self.assertIs(manager1, manager2)
    
    def test_configure_method(self):
        """Test configuration of ClientManager"""
        manager = ClientManager()
        
        # Configure with new values
        server_addr = "http://new-server:8000"
        client_service_addr = "http://new-client-service:8001"
        use_container = True
        
        manager.configure(
            server_addr=server_addr,
            client_service_addr=client_service_addr,
            use_container=use_container
        )
        
        self.assertEqual(manager._server_addr, server_addr)
        self.assertEqual(manager._client_service_addr, client_service_addr)
        self.assertTrue(manager._use_container)
    
    def test_configure_partial(self):
        """Test partial configuration of ClientManager"""
        manager = ClientManager()
        
        # Configure only server address
        manager.configure(server_addr="http://partial-server:8000")
        
        self.assertEqual(manager._server_addr, "http://partial-server:8000")
        self.assertEqual(manager._client_service_addr, "http://localhost:8001")  # Should remain default
        self.assertFalse(manager._use_container)  # Should remain default
    
    @patch('client_service.client_manager.client_manager.ClientGroup')
    def test_add_client_group_success(self, mock_client_group_class):
        """Test successful client group addition"""
        # Setup mock
        mock_client_group = Mock()
        mock_client_group_class.return_value = mock_client_group
        
        manager = ClientManager()
        
        benchmark_id = 123
        num_clients = 5
        time_limit = 10
        
        result = manager.add_client_group(benchmark_id, num_clients, time_limit)
        
        # Verify result
        self.assertEqual(result, ClientManagerResponseStatus.OK)
        
        # Verify ClientGroup was created correctly
        mock_client_group_class.assert_called_once_with(
            benchmark_id, num_clients, "http://localhost:8002", "http://localhost:8001", time_limit, False
        )
        
        # Verify group was added to internal dict
        self.assertIn(benchmark_id, manager._client_groups)
        self.assertEqual(manager._client_groups[benchmark_id], mock_client_group)
    
    @patch('client_service.client_manager.client_manager.ClientGroup')
    def test_add_client_group_already_exists(self, mock_client_group_class):
        """Test adding client group when it already exists"""
        manager = ClientManager()
        
        # First addition should succeed
        result1 = manager.add_client_group(123, 5, 10)
        self.assertEqual(result1, ClientManagerResponseStatus.OK)
        
        # Second addition should fail
        result2 = manager.add_client_group(123, 3, 5)
        self.assertEqual(result2, ClientManagerResponseStatus.ERROR)
        
        # Should only have been called once
        self.assertEqual(mock_client_group_class.call_count, 1)
    
    @patch('client_service.client_manager.client_manager.ClientGroup')
    def test_add_client_group_creation_fails(self, mock_client_group_class):
        """Test adding client group when ClientGroup creation fails"""
        # Setup mock to raise exception
        mock_client_group_class.side_effect = Exception("Creation failed")
        
        manager = ClientManager()
        
        result = manager.add_client_group(123, 5, 10)
        
        # Should return error
        self.assertEqual(result, ClientManagerResponseStatus.ERROR)
        
        # Should not be in groups dict
        self.assertNotIn(123, manager._client_groups)
    
    def test_remove_client_group(self):
        """Test removing client groups"""
        manager = ClientManager()
        
        # Add a mock group manually
        mock_group = Mock()
        manager._client_groups[123] = mock_group
        
        # Verify it exists
        self.assertIn(123, manager._client_groups)
        
        # Remove it
        manager.remove_client_group(123)
        
        # Verify it's gone
        self.assertNotIn(123, manager._client_groups)
    
    def test_remove_nonexistent_client_group(self):
        """Test removing client group that doesn't exist"""
        manager = ClientManager()
        
        # Should not raise exception
        manager.remove_client_group(999)
        
        # Should still have empty dict
        self.assertEqual(len(manager._client_groups), 0)
    
    def test_register_client_success(self):
        """Test successful client registration"""
        manager = ClientManager()
        
        # Add a mock group
        mock_group = Mock()
        mock_group.register_client_address.return_value = True
        manager._client_groups[123] = mock_group
        
        client_address = "http://client:9000"
        result = manager.register_client(123, client_address)
        
        self.assertTrue(result)
        mock_group.register_client_address.assert_called_once_with(client_address)
    
    def test_register_client_unknown_group(self):
        """Test client registration for unknown group"""
        manager = ClientManager()
        
        result = manager.register_client(999, "http://client:9000")
        
        self.assertFalse(result)
    
    def test_list_groups(self):
        """Test listing groups"""
        manager = ClientManager()
        
        # Initially empty
        self.assertEqual(manager.list_groups(), [])
        
        # Add some mock groups
        manager._client_groups[123] = Mock()
        manager._client_groups[456] = Mock()
        manager._client_groups[789] = Mock()
        
        groups = manager.list_groups()
        self.assertEqual(set(groups), {123, 456, 789})
    
    def test_get_group_info_success(self):
        """Test successful group info retrieval"""
        manager = ClientManager()
        
        # Add a mock group
        mock_group = Mock()
        expected_info = {"num_clients": 5, "client_address": "http://client:9000"}
        mock_group.get_info.return_value = expected_info
        manager._client_groups[123] = mock_group
        
        info = manager.get_group_info(123)
        
        self.assertEqual(info, expected_info)
        mock_group.get_info.assert_called_once()
    
    def test_get_group_info_nonexistent(self):
        """Test group info retrieval for nonexistent group"""
        manager = ClientManager()
        
        info = manager.get_group_info(999)
        
        self.assertIsNone(info)
    
    def test_wait_for_clients_success(self):
        """Test successful wait for clients"""
        manager = ClientManager()
        
        # Add a mock group that becomes registered
        mock_group = Mock()
        mock_group.has_client_registered.side_effect = [False, False, True]  # Third call returns True
        manager._client_groups[123] = mock_group
        
        with patch('time.sleep'):  # Speed up the test
            result = manager.wait_for_clients(123, timeout=30.0, poll_interval=0.1)
        
        self.assertTrue(result)
    
    def test_wait_for_clients_timeout(self):
        """Test wait for clients with timeout"""
        manager = ClientManager()
        
        # Add a mock group that never registers
        mock_group = Mock()
        mock_group.has_client_registered.return_value = False
        manager._client_groups[123] = mock_group
        
        with patch('time.time', side_effect=[0, 0.1, 0.2, 31.0]):  # Simulate timeout
            result = manager.wait_for_clients(123, timeout=30.0, poll_interval=0.1)
        
        self.assertFalse(result)
    
    def test_wait_for_clients_unknown_group(self):
        """Test wait for clients with unknown group"""
        manager = ClientManager()
        
        result = manager.wait_for_clients(999, timeout=30.0)
        
        self.assertFalse(result)
    
    @patch('requests.post')
    def test_run_client_group_success(self, mock_post):
        """Test successful client group run"""
        manager = ClientManager()
        
        # Setup mock group
        mock_group = Mock()
        mock_group.get_client_address.return_value = "http://client:9000"
        manager._client_groups[123] = mock_group
        
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "started"
        mock_post.return_value = mock_response
        
        results = manager.run_client_group(123)
        
        # Verify results
        expected_results = [{"client_process": "http://client:9000", "status_code": 200, "body": "started"}]
        self.assertEqual(results, expected_results)
        
        # Verify request was made
        mock_post.assert_called_once_with("http://client:9000/run", timeout=5.0)
    
    def test_run_client_group_unknown_group(self):
        """Test running unknown client group"""
        manager = ClientManager()
        
        with self.assertRaises(ValueError) as context:
            manager.run_client_group(999)
        
        self.assertEqual(str(context.exception), "Unknown benchmark id 999")
    
    def test_run_client_group_no_client_registered(self):
        """Test running client group with no registered client"""
        manager = ClientManager()
        
        # Setup mock group with no client
        mock_group = Mock()
        mock_group.get_client_address.return_value = None
        manager._client_groups[123] = mock_group
        
        results = manager.run_client_group(123)
        
        expected_results = [{"error": "no client process registered", "benchmark_id": 123}]
        self.assertEqual(results, expected_results)
    
    @patch('requests.post')
    def test_run_client_group_request_exception(self, mock_post):
        """Test client group run with request exception"""
        manager = ClientManager()
        
        # Setup mock group
        mock_group = Mock()
        mock_group.get_client_address.return_value = "http://client:9000"
        manager._client_groups[123] = mock_group
        
        # Setup mock to raise exception
        mock_post.side_effect = Exception("Connection failed")
        
        results = manager.run_client_group(123)
        
        # Should return error result
        expected_results = [{"client_process": "http://client:9000", "error": "Connection failed"}]
        self.assertEqual(results, expected_results)


class TestCMResponse(unittest.TestCase):
    """Test CMResponse helper class"""
    
    def test_cm_response_creation(self):
        """Test CMResponse creation"""
        response = CMResponse(ClientManagerResponseStatus.OK, {"data": "test"})
        
        self.assertEqual(response.status, ClientManagerResponseStatus.OK)
        self.assertEqual(response.body, {"data": "test"})
    
    def test_cm_response_without_body(self):
        """Test CMResponse creation without body"""
        response = CMResponse(ClientManagerResponseStatus.ERROR)
        
        self.assertEqual(response.status, ClientManagerResponseStatus.ERROR)
        self.assertIsNone(response.body)


class TestClientManagerResponseStatus(unittest.TestCase):
    """Test ClientManagerResponseStatus constants"""
    
    def test_status_constants(self):
        """Test that status constants are defined correctly"""
        self.assertEqual(ClientManagerResponseStatus.OK, 0)
        self.assertEqual(ClientManagerResponseStatus.ERROR, 1)


if __name__ == '__main__':
    unittest.main()
