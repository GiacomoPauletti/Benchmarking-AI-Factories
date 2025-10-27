"""
Unit tests for ClientGroup singleton class
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import threading
import time

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from client.client_group import ClientGroup


class TestClientGroup(unittest.TestCase):
    
    def setUp(self):
        """Reset singleton before each test"""
        # Reset the singleton instance
        ClientGroup._instance = None
    
    def tearDown(self):
        """Clean up after each test"""
        # Reset the singleton instance
        ClientGroup._instance = None
    
    def test_singleton_pattern(self):
        """Test that ClientGroup follows singleton pattern"""
        group1 = ClientGroup()
        group2 = ClientGroup()
        
        # Should be the same instance
        self.assertIs(group1, group2)
        self.assertEqual(id(group1), id(group2))
    
    def test_singleton_thread_safety(self):
        """Test singleton thread safety"""
        instances = []
        
        def create_instance():
            instances.append(ClientGroup())
        
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
        group1 = ClientGroup()
        initial_time = group1.created_at
        
        # Second creation should not re-initialize
        time.sleep(0.01)  # Small delay
        group2 = ClientGroup()
        
        # Should be same instance and same creation time
        self.assertIs(group1, group2)
        self.assertEqual(group1.created_at, group2.created_at)
        self.assertEqual(initial_time, group2.created_at)
    
    def test_initial_state(self):
        """Test initial state of ClientGroup"""
        group = ClientGroup()
        
        self.assertIsNone(group.benchmark_id)
        self.assertEqual(len(group.clients), 0)
        self.assertEqual(group.num_clients, 0)
        self.assertIsNone(group.server_addr)
        self.assertIsNone(group.client_service_addr)
        self.assertIsNone(group.local_address)
        self.assertIsInstance(group.created_at, float)
        self.assertTrue(group.created_at > 0)
    
    def test_configure_method(self):
        """Test configuration of ClientGroup"""
        group = ClientGroup()
        
        benchmark_id = 123
        clients = [Mock(), Mock(), Mock()]
        server_addr = "http://server:8000"
        client_service_addr = "http://client-service:8001"
        local_address = "http://local:9000"
        
        group.configure(
            benchmark_id=benchmark_id,
            clients=clients,
            server_addr=server_addr,
            client_service_addr=client_service_addr,
            local_address=local_address
        )
        
        self.assertEqual(group.benchmark_id, benchmark_id)
        self.assertEqual(group.clients, clients)
        self.assertEqual(group.num_clients, 3)
        self.assertEqual(group.server_addr, server_addr)
        self.assertEqual(group.client_service_addr, client_service_addr)
        self.assertEqual(group.local_address, local_address)
    
    def test_add_client(self):
        """Test adding clients to the group"""
        group = ClientGroup()
        
        # Initially empty
        self.assertEqual(group.num_clients, 0)
        
        # Add clients
        client1 = Mock()
        client2 = Mock()
        
        group.add_client(client1)
        self.assertEqual(group.num_clients, 1)
        self.assertIn(client1, group.clients)
        
        group.add_client(client2)
        self.assertEqual(group.num_clients, 2)
        self.assertIn(client2, group.clients)
    
    def test_run_all_clients_empty(self):
        """Test running clients when no clients are present"""
        group = ClientGroup()
        
        started_count = group.run_all_clients()
        self.assertEqual(started_count, 0)
    
    def test_run_all_clients_success(self):
        """Test successfully running all clients"""
        group = ClientGroup()
        
        # Create mock clients
        client1 = Mock()
        client2 = Mock()
        client3 = Mock()
        
        # Configure group with clients
        group.configure(
            benchmark_id=123,
            clients=[client1, client2, client3],
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001",
            local_address="http://local:9000"
        )
        
        with patch('threading.Thread') as mock_thread_class:
            mock_threads = [Mock(), Mock(), Mock()]
            mock_thread_class.side_effect = mock_threads
            
            started_count = group.run_all_clients()
            
            # Should have started all clients
            self.assertEqual(started_count, 3)
            
            # Verify threads were created and started
            self.assertEqual(mock_thread_class.call_count, 3)
            for i, mock_thread in enumerate(mock_threads):
                mock_thread.start.assert_called_once()
                # Verify thread was assigned to client
                self.assertEqual(group.clients[i].thread, mock_thread)
    
    def test_run_all_clients_with_exception(self):
        """Test running clients when some fail to start"""
        group = ClientGroup()
        
        # Create mock clients
        client1 = Mock()
        client2 = Mock()
        client3 = Mock()
        
        group.configure(
            benchmark_id=123,
            clients=[client1, client2, client3],
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001",
            local_address="http://local:9000"
        )
        
        with patch('threading.Thread') as mock_thread_class:
            # First thread succeeds, second fails, third succeeds
            mock_thread1 = Mock()
            mock_thread2 = Mock()
            mock_thread2.start.side_effect = Exception("Thread start failed")
            mock_thread3 = Mock()
            
            mock_thread_class.side_effect = [mock_thread1, mock_thread2, mock_thread3]
            
            started_count = group.run_all_clients()
            
            # Should have started 2 out of 3 clients
            self.assertEqual(started_count, 2)
    
    def test_register_observer_empty_clients(self):
        """Test registering observer when no clients are present"""
        group = ClientGroup()
        observer = Mock()
        
        result = group.register_observer(observer)
        self.assertFalse(result)
    
    def test_register_observer_success(self):
        """Test successfully registering observer to all clients"""
        group = ClientGroup()
        
        # Create mock clients
        client1 = Mock()
        client2 = Mock()
        client3 = Mock()
        
        group.configure(
            benchmark_id=123,
            clients=[client1, client2, client3],
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001",
            local_address="http://local:9000"
        )
        
        observer = Mock()
        result = group.register_observer(observer)
        
        self.assertTrue(result)
        
        # Verify observer was subscribed to all clients
        client1.subscribe.assert_called_once_with(observer)
        client2.subscribe.assert_called_once_with(observer)
        client3.subscribe.assert_called_once_with(observer)
    
    def test_register_observer_with_exception(self):
        """Test registering observer when subscription fails"""
        group = ClientGroup()
        
        # Create mock clients, one with failing subscribe
        client1 = Mock()
        client2 = Mock()
        client2.subscribe.side_effect = Exception("Subscribe failed")
        
        group.configure(
            benchmark_id=123,
            clients=[client1, client2],
            server_addr="http://server:8000",
            client_service_addr="http://client-service:8001",
            local_address="http://local:9000"
        )
        
        observer = Mock()
        result = group.register_observer(observer)
        
        self.assertFalse(result)
    
    def test_get_status(self):
        """Test getting status information"""
        group = ClientGroup()
        
        # Configure group
        benchmark_id = 456
        clients = [Mock(), Mock()]
        server_addr = "http://server:8000"
        client_service_addr = "http://client-service:8001"
        local_address = "http://local:9000"
        
        group.configure(
            benchmark_id=benchmark_id,
            clients=clients,
            server_addr=server_addr,
            client_service_addr=client_service_addr,
            local_address=local_address
        )
        
        status = group.get_status()
        
        expected_status = {
            "benchmark_id": benchmark_id,
            "num_clients": 2,
            "server_addr": server_addr,
            "client_service_addr": client_service_addr,
            "local_address": local_address,
            "created_at": group.created_at
        }
        
        self.assertEqual(status, expected_status)
    
    def test_properties(self):
        """Test all property accessors"""
        group = ClientGroup()
        
        # Test initial properties
        self.assertIsNone(group.benchmark_id)
        self.assertEqual(group.clients, [])
        self.assertEqual(group.num_clients, 0)
        self.assertIsNone(group.server_addr)
        self.assertIsNone(group.client_service_addr)
        self.assertIsNone(group.local_address)
        self.assertIsInstance(group.created_at, float)
        
        # Configure and test again
        benchmark_id = 789
        clients = [Mock() for _ in range(4)]
        server_addr = "http://test-server:8000"
        client_service_addr = "http://test-client-service:8001"
        local_address = "http://test-local:9000"
        
        group.configure(
            benchmark_id=benchmark_id,
            clients=clients,
            server_addr=server_addr,
            client_service_addr=client_service_addr,
            local_address=local_address
        )
        
        self.assertEqual(group.benchmark_id, benchmark_id)
        self.assertEqual(group.clients, clients)
        self.assertEqual(group.num_clients, 4)
        self.assertEqual(group.server_addr, server_addr)
        self.assertEqual(group.client_service_addr, client_service_addr)
        self.assertEqual(group.local_address, local_address)


if __name__ == '__main__':
    unittest.main()