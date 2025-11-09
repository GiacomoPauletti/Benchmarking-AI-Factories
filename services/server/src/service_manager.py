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
from service_group_manager import ServiceGroupManager


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
        self._last_successful_prompt: Dict[str, float] = {}  # {service_id: timestamp}
        self._instance_lock = threading.RLock()
        
        # Service group manager for replica groups
        self.group_manager = ServiceGroupManager()

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
    
    def mark_service_healthy(self, service_id: str) -> None:
        """
        Mark a service as healthy after successful prompt response.
        
        This is used to skip expensive status checks for recently-used services.
        
        Args:
            service_id: Service ID to mark as healthy
        """
        import time
        with self._instance_lock:
            self._last_successful_prompt[service_id] = time.time()
    
    def is_service_recently_healthy(self, service_id: str, max_age_seconds: int = 300) -> bool:
        """
        Check if a service was successfully used recently.
        
        Args:
            service_id: Service ID to check
            max_age_seconds: Maximum age in seconds to consider "recent" (default: 5 minutes)
        
        Returns:
            True if service was successfully used within max_age_seconds, False otherwise
        """
        import time
        with self._instance_lock:
            if service_id not in self._last_successful_prompt:
                return False
            
            last_success_time = self._last_successful_prompt[service_id]
            age = time.time() - last_success_time
            return age < max_age_seconds
    
    def invalidate_service_health(self, service_id: str) -> None:
        """
        Invalidate health status for a service (e.g., after an error).
        
        Args:
            service_id: Service ID to invalidate
        """
        with self._instance_lock:
            self._last_successful_prompt.pop(service_id, None)
    
    # ========== Service Group Methods ==========
    
    def is_group(self, service_id: str) -> bool:
        """Check if a service ID is actually a service group.
        
        Args:
            service_id: Service ID to check
            
        Returns:
            True if this is a service group, False otherwise
        """
        return self.group_manager.is_group(service_id)
    
    def get_group_info(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get service group information.
        
        Args:
            group_id: Service group ID
            
        Returns:
            Group info dict or None if not found
        """
        return self.group_manager.get_group(group_id)
    
    def get_group_for_replica(self, replica_id: str) -> Optional[str]:
        """Get the group ID that a replica belongs to.
        
        Args:
            replica_id: Replica service ID
            
        Returns:
            Group ID or None if not part of a group
        """
        return self.group_manager.get_group_for_replica(replica_id)
    
    def update_replica_status(self, replica_id: str, status: str) -> None:
        """Update the status of a replica in its group.
        
        Args:
            replica_id: Replica service ID
            status: New status
        """
        # Update in regular service tracking
        self.update_service_status(replica_id, status)
        
        # Update in group manager
        self.group_manager.update_replica_status(replica_id, status)
    
    def get_healthy_replicas(self, group_id: str) -> List[Dict[str, Any]]:
        """Get list of healthy replicas for a group.
        
        Args:
            group_id: Service group ID
            
        Returns:
            List of healthy replica info dicts
        """
        return self.group_manager.get_healthy_replicas(group_id)
    
    def get_all_replica_ids(self, group_id: str) -> List[str]:
        """Get all replica IDs for a group.
        
        Args:
            group_id: Service group ID
            
        Returns:
            List of replica service IDs
        """
        return self.group_manager.get_all_replica_ids(group_id)