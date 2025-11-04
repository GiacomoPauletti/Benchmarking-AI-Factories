"""
Test for ClientGroup singleton pattern
"""

import unittest
import time
from client.client_group import ClientGroup


class TestClientGroup(unittest.TestCase):
    
    def setUp(self):
        # Reset singleton instance for each test
        ClientGroup._instance = None
    
    def test_singleton_pattern(self):
        """Test that ClientGroup is a proper singleton"""
        # Create two instances
        client_group1 = ClientGroup()
        client_group2 = ClientGroup()
        
        # They should be the same instance
        self.assertIs(client_group1, client_group2)
        self.assertEqual(id(client_group1), id(client_group2))
    
    def test_singleton_configuration(self):
        """Test that configuration is shared across instances"""
        client_group1 = ClientGroup()
        client_group1.configure(
            benchmark_id=123,
            clients=["client1", "client2"],
            server_addr="server:8080",
            client_service_addr="service:9090", 
            local_address="local:8080"
        )
        
        # Create another instance
        client_group2 = ClientGroup()
        
        # Should have the same configuration
        self.assertEqual(client_group2.benchmark_id, 123)
        self.assertEqual(len(client_group2.clients), 2)
        self.assertEqual(client_group2.server_addr, "server:8080")
        self.assertEqual(client_group2.client_service_addr, "service:9090")
        self.assertEqual(client_group2.local_address, "local:8080")
    
    def test_properties(self):
        """Test ClientGroup properties"""
        client_group = ClientGroup()
        
        # Test initial state
        self.assertIsNone(client_group.benchmark_id)
        self.assertEqual(len(client_group.clients), 0)
        self.assertEqual(client_group.num_clients, 0)
        self.assertIsNotNone(client_group.created_at)
        
        # Configure and test
        clients = ["client1", "client2", "client3"]
        client_group.configure(
            benchmark_id=456,
            clients=clients,
            server_addr="test_server",
            client_service_addr="test_service",
            local_address="test_local"
        )
        
        self.assertEqual(client_group.benchmark_id, 456)
        self.assertEqual(client_group.num_clients, 3)
        self.assertEqual(client_group.clients, clients)
    
    def test_get_status(self):
        """Test get_status method"""
        client_group = ClientGroup()
        client_group.configure(
            benchmark_id=789,
            clients=["a", "b"],
            server_addr="status_server",
            client_service_addr="status_service",
            local_address="status_local"
        )
        
        status = client_group.get_status()
        
        self.assertIsInstance(status, dict)
        self.assertEqual(status["benchmark_id"], 789)
        self.assertEqual(status["num_clients"], 2)
        self.assertEqual(status["server_addr"], "status_server")
        self.assertEqual(status["client_service_addr"], "status_service")
        self.assertEqual(status["local_address"], "status_local")
        self.assertIn("created_at", status)
    
    def test_add_client(self):
        """Test add_client method"""
        client_group = ClientGroup()
        
        initial_count = client_group.num_clients
        client_group.add_client("new_client")
        
        self.assertEqual(client_group.num_clients, initial_count + 1)
        self.assertIn("new_client", client_group.clients)


if __name__ == "__main__":
    unittest.main()