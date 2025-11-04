"""
Unit tests for ClientObserver class
"""

import unittest
from unittest.mock import Mock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from client.client_observer import ClientObserver


class TestClientObserver(unittest.TestCase):
    
    def test_base_observer_creation(self):
        """Test creating a base ClientObserver instance"""
        observer = ClientObserver()
        self.assertIsInstance(observer, ClientObserver)
    
    def test_update_method_exists(self):
        """Test that update method exists and can be called"""
        observer = ClientObserver()
        
        # Should not raise an exception
        observer.update({})
        observer.update({"key": "value"})
        observer.update({"complex": {"nested": "data"}})
    
    def test_update_method_signature(self):
        """Test update method signature accepts dict parameter"""
        observer = ClientObserver()
        
        # Test with various dict types
        test_data = [
            {},
            {"simple": "data"},
            {"number": 123},
            {"list": [1, 2, 3]},
            {"nested": {"deep": {"data": "value"}}},
            {"mixed": {"str": "text", "num": 42, "list": [1, 2, 3]}}
        ]
        
        for data in test_data:
            # Should not raise an exception
            observer.update(data)
    
    def test_inheritance_base_class(self):
        """Test that custom observers can inherit from ClientObserver"""
        
        class CustomObserver(ClientObserver):
            def __init__(self):
                super().__init__()
                self.updates_received = []
            
            def update(self, data: dict):
                self.updates_received.append(data)
        
        observer = CustomObserver()
        self.assertIsInstance(observer, ClientObserver)
        self.assertEqual(len(observer.updates_received), 0)
        
        # Test update functionality
        test_data = {"test": "data"}
        observer.update(test_data)
        self.assertEqual(len(observer.updates_received), 1)
        self.assertEqual(observer.updates_received[0], test_data)
    
    def test_multiple_inheritance_observers(self):
        """Test creating multiple observer instances"""
        
        class Observer1(ClientObserver):
            def update(self, data: dict):
                self.last_update = "observer1_" + str(data)
        
        class Observer2(ClientObserver):
            def update(self, data: dict):
                self.last_update = "observer2_" + str(data)
        
        obs1 = Observer1()
        obs2 = Observer2()
        
        self.assertIsInstance(obs1, ClientObserver)
        self.assertIsInstance(obs2, ClientObserver)
        
        # Test that they work independently
        obs1.update({"data": 1})
        obs2.update({"data": 2})
        
        self.assertEqual(obs1.last_update, "observer1_{'data': 1}")
        self.assertEqual(obs2.last_update, "observer2_{'data': 2}")
    
    def test_observer_interface_compliance(self):
        """Test that ClientObserver complies with observer pattern interface"""
        
        class TestObserver(ClientObserver):
            def __init__(self):
                super().__init__()
                self.notification_count = 0
                self.last_data = None
            
            def update(self, data: dict):
                self.notification_count += 1
                self.last_data = data
        
        observer = TestObserver()
        
        # Test multiple updates
        observer.update({"event": "start"})
        self.assertEqual(observer.notification_count, 1)
        self.assertEqual(observer.last_data, {"event": "start"})
        
        observer.update({"event": "progress", "percent": 50})
        self.assertEqual(observer.notification_count, 2)
        self.assertEqual(observer.last_data, {"event": "progress", "percent": 50})
        
        observer.update({"event": "complete"})
        self.assertEqual(observer.notification_count, 3)
        self.assertEqual(observer.last_data, {"event": "complete"})


class TestObserverPatternIntegration(unittest.TestCase):
    """Test observer pattern integration with mock clients"""
    
    def test_observer_with_mock_client(self):
        """Test observer pattern with a mock client"""
        
        class MockClient:
            def __init__(self):
                self._observers = []
            
            def subscribe(self, observer: ClientObserver):
                self._observers.append(observer)
            
            def notify_observers(self, data: dict):
                for observer in self._observers:
                    observer.update(data)
        
        class TrackingObserver(ClientObserver):
            def __init__(self):
                super().__init__()
                self.received_notifications = []
            
            def update(self, data: dict):
                self.received_notifications.append(data)
        
        # Setup
        client = MockClient()
        observer1 = TrackingObserver()
        observer2 = TrackingObserver()
        
        # Subscribe observers
        client.subscribe(observer1)
        client.subscribe(observer2)
        
        # Test notifications
        client.notify_observers({"status": "running"})
        
        self.assertEqual(len(observer1.received_notifications), 1)
        self.assertEqual(len(observer2.received_notifications), 1)
        self.assertEqual(observer1.received_notifications[0], {"status": "running"})
        self.assertEqual(observer2.received_notifications[0], {"status": "running"})
        
        # Test multiple notifications
        client.notify_observers({"status": "completed", "result": "success"})
        
        self.assertEqual(len(observer1.received_notifications), 2)
        self.assertEqual(len(observer2.received_notifications), 2)
        self.assertEqual(observer1.received_notifications[1], {"status": "completed", "result": "success"})
        self.assertEqual(observer2.received_notifications[1], {"status": "completed", "result": "success"})


if __name__ == '__main__':
    unittest.main()