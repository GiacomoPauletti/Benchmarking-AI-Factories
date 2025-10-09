"""
In-memory service manager for managing service and job information.
Provides better organization, querying, and lifecycle management within a single server run.
"""

import threading
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict


"""
In-memory service manager for managing service and job information.
Provides better organization, querying, and lifecycle management within a single server run.
"""

import threading
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict


class ServiceManager:
    """Simple in-memory manager for service and job information with better organization.
    TODO: To be replaced with a database or persistent store in the future."""
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern to ensure only one ServiceManager instance exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ServiceManager, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the singleton instance."""
        self._services: Dict[str, Dict[str, Any]] = {}
        self._services_by_recipe: Dict[str, List[str]] = defaultdict(list)
        self._services_by_status: Dict[str, List[str]] = defaultdict(list)
        self._instance_lock = threading.RLock()

    def register_service(self, service_data: Dict[str, Any]) -> None:
        """
        Register a new service in the manager.

        Args:
            service_data: Complete service information dictionary
        """
        with self._instance_lock:
            service_id = service_data['id']

            # Store the service
            self._services[service_id] = service_data.copy()

            # Update indexes
            recipe_name = service_data.get('recipe_name', 'unknown')
            status = service_data.get('status', 'unknown')

            self._services_by_recipe[recipe_name].append(service_id)
            self._services_by_status[status].append(service_id)

    def update_service_status(self, service_id: str, new_status: str) -> bool:
        """
        Update the status of a service.

        Args:
            service_id: Service ID to update
            new_status: New status

        Returns:
            True if service was found and updated, False otherwise
        """
        with self._instance_lock:
            if service_id not in self._services:
                return False

            old_status = self._services[service_id].get('status', 'unknown')

            # Update status
            self._services[service_id]['status'] = new_status
            self._services[service_id]['last_updated'] = datetime.now()

            # Update status index
            if old_status in self._services_by_status and service_id in self._services_by_status[old_status]:
                self._services_by_status[old_status].remove(service_id)

            self._services_by_status[new_status].append(service_id)

            return True

    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """
        Get service information by ID.

        Args:
            service_id: Service ID to retrieve

        Returns:
            Service data dictionary or None if not found
        """
        with self._instance_lock:
            return self._services.get(service_id)

    def list_services(self, status_filter: Optional[str] = None,
                     recipe_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List services with optional filtering.

        Args:
            status_filter: If provided, only return services with this status
            recipe_filter: If provided, only return services with this recipe

        Returns:
            List of service data dictionaries
        """
        with self._instance_lock:
            if status_filter and recipe_filter:
                # Both filters - find intersection
                status_services = set(self._services_by_status.get(status_filter, []))
                recipe_services = set(self._services_by_recipe.get(recipe_filter, []))
                service_ids = status_services & recipe_services
            elif status_filter:
                service_ids = self._services_by_status.get(status_filter, [])
            elif recipe_filter:
                service_ids = self._services_by_recipe.get(recipe_filter, [])
            else:
                service_ids = list(self._services.keys())

            return [self._services[sid].copy() for sid in service_ids if sid in self._services]

    def remove_service(self, service_id: str) -> bool:
        """
        Remove a service from the manager.

        Args:
            service_id: Service ID to remove

        Returns:
            True if service was found and removed, False otherwise
        """
        with self._instance_lock:
            if service_id not in self._services:
                return False

            service_data = self._services[service_id]

            # Remove from indexes
            recipe_name = service_data.get('recipe_name', 'unknown')
            status = service_data.get('status', 'unknown')

            if service_id in self._services_by_recipe[recipe_name]:
                self._services_by_recipe[recipe_name].remove(service_id)
            if service_id in self._services_by_status[status]:
                self._services_by_status[status].remove(service_id)

            # Remove service
            del self._services[service_id]

            return True

    def get_services_by_recipe(self, recipe_name: str) -> List[Dict[str, Any]]:
        """
        Get all services using a specific recipe.

        Args:
            recipe_name: Recipe name to filter by

        Returns:
            List of matching service data dictionaries
        """
        return self.list_services(recipe_filter=recipe_name)

    def get_active_services(self) -> List[Dict[str, Any]]:
        """
        Get all currently active (running or pending) services.

        Returns:
            List of active service data dictionaries
        """
        return self.list_services(status_filter='running') + self.list_services(status_filter='pending')

    def get_completed_services(self) -> List[Dict[str, Any]]:
        """
        Get all completed services.

        Returns:
            List of completed service data dictionaries
        """
        return self.list_services(status_filter='completed')

    def bulk_update_statuses(self, status_updates: Dict[str, str]) -> Dict[str, bool]:
        """
        Bulk update statuses for multiple services.

        Args:
            status_updates: Dictionary mapping service_id to new_status

        Returns:
            Dictionary mapping service_id to success boolean
        """
        with self._instance_lock:
            results = {}
            for service_id, new_status in status_updates.items():
                results[service_id] = self.update_service_status(service_id, new_status)
            return results

    def find_services_by_pattern(self, name_pattern: str = None,
                               recipe_pattern: str = None) -> List[Dict[str, Any]]:
        """
        Find services by name or recipe pattern (case-insensitive substring match).

        Args:
            name_pattern: Pattern to match in service names
            recipe_pattern: Pattern to match in recipe names

        Returns:
            List of matching service data dictionaries
        """
        with self._instance_lock:
            matches = []

            for service_data in self._services.values():
                name_match = not name_pattern or name_pattern.lower() in service_data.get('name', '').lower()
                recipe_match = not recipe_pattern or recipe_pattern.lower() in service_data.get('recipe_name', '').lower()

                if name_match and recipe_match:
                    matches.append(service_data.copy())

            return matches