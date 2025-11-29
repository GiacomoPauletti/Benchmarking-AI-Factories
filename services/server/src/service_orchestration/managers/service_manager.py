"""
In-memory service manager for managing service and job information.
Provides better organization, querying, and lifecycle management within a single server run.

Now includes service group management (previously in ServiceGroupManager).
"""

import logging
import threading
import time
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict


class ServiceManager:
    """In-memory manager for service and job information with service group support.
    
    This class manages:
    - Individual service registration and status tracking
    - Service groups (replica groups for data-parallel workloads)
    - Health tracking for recently-used services
    
    TODO: To be replaced with a database or persistent store in the future.
    """
    
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
        self.logger = logging.getLogger(__name__)
        self._instance_lock = threading.RLock()
        
        # Individual service tracking
        self._services: Dict[str, Dict[str, Any]] = {}
        self._services_by_recipe: Dict[str, List[str]] = defaultdict(list)
        self._services_by_status: Dict[str, List[str]] = defaultdict(list)
        self._last_successful_prompt: Dict[str, float] = {}
        
        # Service group tracking (merged from ServiceGroupManager)
        self._groups: Dict[str, Dict[str, Any]] = {}
        self._replica_to_group: Dict[str, str] = {}

    # ========== Individual Service Methods ==========

    def register_service(self, service_data: Dict[str, Any]) -> None:
        """Register a new service in the manager."""
        with self._instance_lock:
            service_id = service_data['id']
            self._services[service_id] = service_data.copy()

            recipe_name = service_data.get('recipe_name', 'unknown')
            status = service_data.get('status', 'unknown')

            self._services_by_recipe[recipe_name].append(service_id)
            self._services_by_status[status].append(service_id)

    def update_service_status(self, service_id: str, new_status: str) -> bool:
        """Update the status of a service."""
        with self._instance_lock:
            if service_id not in self._services:
                return False

            old_status = self._services[service_id].get('status', 'unknown')
            self._services[service_id]['status'] = new_status
            self._services[service_id]['last_updated'] = datetime.now()

            if old_status in self._services_by_status and service_id in self._services_by_status[old_status]:
                self._services_by_status[old_status].remove(service_id)

            self._services_by_status[new_status].append(service_id)
            return True

    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get service information by ID."""
        with self._instance_lock:
            return self._services.get(service_id)

    def list_services(self, status_filter: Optional[str] = None,
                     recipe_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List services with optional filtering."""
        with self._instance_lock:
            if status_filter and recipe_filter:
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
        """Remove a service from the manager."""
        with self._instance_lock:
            if service_id not in self._services:
                return False

            service_data = self._services[service_id]
            recipe_name = service_data.get('recipe_name', 'unknown')
            status = service_data.get('status', 'unknown')

            if service_id in self._services_by_recipe[recipe_name]:
                self._services_by_recipe[recipe_name].remove(service_id)
            if service_id in self._services_by_status[status]:
                self._services_by_status[status].remove(service_id)

            del self._services[service_id]
            return True

    def get_services_by_recipe(self, recipe_name: str) -> List[Dict[str, Any]]:
        """Get all services using a specific recipe."""
        return self.list_services(recipe_filter=recipe_name)

    def get_active_services(self) -> List[Dict[str, Any]]:
        """Get all currently active (running or pending) services."""
        return self.list_services(status_filter='running') + self.list_services(status_filter='pending')

    def get_completed_services(self) -> List[Dict[str, Any]]:
        """Get all completed services."""
        return self.list_services(status_filter='completed')

    def bulk_update_statuses(self, status_updates: Dict[str, str]) -> Dict[str, bool]:
        """Bulk update statuses for multiple services."""
        with self._instance_lock:
            return {sid: self.update_service_status(sid, status) for sid, status in status_updates.items()}

    def find_services_by_pattern(self, name_pattern: str = None,
                               recipe_pattern: str = None) -> List[Dict[str, Any]]:
        """Find services by name or recipe pattern (case-insensitive substring match)."""
        with self._instance_lock:
            matches = []
            for service_data in self._services.values():
                name_match = not name_pattern or name_pattern.lower() in service_data.get('name', '').lower()
                recipe_match = not recipe_pattern or recipe_pattern.lower() in service_data.get('recipe_name', '').lower()
                if name_match and recipe_match:
                    matches.append(service_data.copy())
            return matches

    # ========== Health Tracking Methods ==========
    
    def mark_service_healthy(self, service_id: str) -> None:
        """Mark a service as healthy after successful prompt response."""
        with self._instance_lock:
            self._last_successful_prompt[service_id] = time.time()
    
    def is_service_recently_healthy(self, service_id: str, max_age_seconds: int = 300) -> bool:
        """Check if a service was successfully used recently (default: 5 minutes)."""
        with self._instance_lock:
            if service_id not in self._last_successful_prompt:
                return False
            age = time.time() - self._last_successful_prompt[service_id]
            return age < max_age_seconds
    
    def invalidate_service_health(self, service_id: str) -> None:
        """Invalidate health status for a service (e.g., after an error)."""
        with self._instance_lock:
            self._last_successful_prompt.pop(service_id, None)

    # ========== Service Group Methods ==========
    
    def is_group(self, service_id: str) -> bool:
        """Check if a service ID is a service group."""
        return service_id.startswith("sg-")
    
    def create_replica_group(self, recipe_name: str, num_nodes: int, 
                             replicas_per_node: int, total_replicas: int,
                             config: Dict[str, Any] = None,
                             job_id: str = None) -> str:
        """Create a new replica group.
        
        Args:
            recipe_name: The recipe name for this group
            num_nodes: Number of nodes to allocate
            replicas_per_node: Number of replicas per node
            total_replicas: Total number of replicas
            config: Optional configuration for the group
            job_id: Optional SLURM job ID (if provided, group_id = "sg-{job_id}")
            
        Returns:
            The group ID
        """
        with self._instance_lock:
            group_id = f"sg-{job_id}" if job_id else f"sg-{uuid.uuid4().hex[:12]}"
            
            self._groups[group_id] = {
                "id": group_id,
                "name": f"{recipe_name}-group",
                "type": "replica_group",
                "recipe_name": recipe_name,
                "num_nodes": num_nodes,
                "replicas_per_node": replicas_per_node,
                "total_replicas": total_replicas,
                "node_jobs": [],
                "config": config or {},
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            }
            
            self.logger.info(f"Created replica group {group_id}: {num_nodes} nodes × {replicas_per_node} replicas = {total_replicas} total")
            return group_id
    
    def add_replica(self, group_id: str, job_id: str, node_index: int,
                    replica_index: int, port: int, gpu_id: int,
                    status: str = "pending") -> None:
        """Add a replica to a replica group."""
        with self._instance_lock:
            if group_id not in self._groups:
                raise ValueError(f"Group {group_id} not found")
            
            group = self._groups[group_id]
            if group.get("type") != "replica_group":
                raise ValueError(f"Group {group_id} is not a replica group")
            
            # Find or create node_job entry
            node_job = next((nj for nj in group["node_jobs"] if nj["job_id"] == job_id), None)
            if not node_job:
                node_job = {"job_id": job_id, "node_index": node_index, "node": None, "replicas": []}
                group["node_jobs"].append(node_job)
            
            replica_id = f"{job_id}:{port}"
            replica_info = {
                "id": replica_id,
                "job_id": job_id,
                "replica_index": replica_index,
                "port": port,
                "gpu_id": gpu_id,
                "status": status,
                "added_at": datetime.now().isoformat()
            }
            node_job["replicas"].append(replica_info)
            self._replica_to_group[replica_id] = group_id
            
            self.logger.debug(f"Added replica {replica_id} (GPU {gpu_id}, port {port}) to group {group_id}")
    
    def get_all_replicas_flat(self, group_id: str) -> List[Dict[str, Any]]:
        """Get all replicas in a group as a flat list."""
        with self._instance_lock:
            group = self._groups.get(group_id)
            if not group:
                return []
            
            all_replicas = []
            for node_job in group.get("node_jobs", []):
                all_replicas.extend(node_job["replicas"])
            return all_replicas
    
    def get_group_info(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get group metadata by ID."""
        with self._instance_lock:
            return self._groups.get(group_id)
    
    def get_group_for_replica(self, replica_id: str) -> Optional[str]:
        """Get the group ID for a given replica ID."""
        with self._instance_lock:
            return self._replica_to_group.get(replica_id)
    
    def update_replica_status(self, replica_id: str, status: str) -> None:
        """Update the status of a specific replica."""
        with self._instance_lock:
            # Update in regular service tracking if it exists
            self.update_service_status(replica_id, status)
            
            # Update in group tracking
            group_id = self._replica_to_group.get(replica_id)
            if not group_id:
                self.logger.warning(f"Replica {replica_id} not found in any group")
                return
            
            group = self._groups.get(group_id)
            if not group:
                return
            
            for node_job in group.get("node_jobs", []):
                for replica in node_job["replicas"]:
                    if replica["id"] == replica_id:
                        replica["status"] = status
                        replica["updated_at"] = datetime.now().isoformat()
                        self._update_group_status(group_id)
                        return
    
    def update_node_info(self, group_id: str, job_id: str, node: str) -> None:
        """Update the node hostname for a job in a group."""
        with self._instance_lock:
            group = self._groups.get(group_id)
            if not group:
                return
            
            for node_job in group.get("node_jobs", []):
                if node_job["job_id"] == job_id and not node_job.get("node"):
                    node_job["node"] = node
                    self.logger.debug(f"Updated node info for job {job_id} in group {group_id}: {node}")
                    return
    
    def _update_group_status(self, group_id: str) -> None:
        """Update the overall group status based on replica statuses."""
        group = self._groups.get(group_id)
        if not group:
            return
        
        all_replicas = self.get_all_replicas_flat(group_id)
        replica_statuses = [r["status"] for r in all_replicas]
        
        if not replica_statuses:
            group["status"] = "pending"
            return
        
        ready_or_running = sum(1 for s in replica_statuses if s in ["running", "ready"])
        starting = sum(1 for s in replica_statuses if s == "starting")
        completed = sum(1 for s in replica_statuses if s in ["completed", "failed", "cancelled"])
        
        if completed == len(replica_statuses):
            group["status"] = "completed"
        elif ready_or_running > 0:
            group["status"] = "running"
        elif starting > 0:
            group["status"] = "starting"
        else:
            group["status"] = "pending"

    def update_group_status(self, group_id: str, status: str) -> None:
        """Forcefully set the overall group status."""
        with self._instance_lock:
            group = self._groups.get(group_id)
            if not group:
                self.logger.warning(f"Attempted to update status for missing group {group_id}")
                return
            group["status"] = status
            group["updated_at"] = datetime.now().isoformat()
    
    def get_healthy_replicas(self, group_id: str) -> List[str]:
        """Get list of healthy replica IDs for a group."""
        with self._instance_lock:
            all_replicas = self.get_all_replicas_flat(group_id)
            return [r["id"] for r in all_replicas if r.get("status") in ["ready", "running", "healthy"]]
    
    def get_all_replica_ids(self, group_id: str) -> List[str]:
        """Get all replica IDs for a group."""
        with self._instance_lock:
            return [r["id"] for r in self.get_all_replicas_flat(group_id)]
    
    def list_groups(self) -> List[Dict[str, Any]]:
        """List all service groups."""
        with self._instance_lock:
            return list(self._groups.values())
    
    def delete_group(self, group_id: str) -> bool:
        """Delete a service group."""
        with self._instance_lock:
            if group_id not in self._groups:
                return False
            
            for replica in self.get_all_replicas_flat(group_id):
                self._replica_to_group.pop(replica["id"], None)
            
            del self._groups[group_id]
            self.logger.info(f"Deleted service group {group_id}")
            return True