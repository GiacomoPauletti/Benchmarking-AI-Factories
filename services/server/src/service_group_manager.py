"""
Service Group Manager

Manages groups of replica services for data-parallel workloads.
Each group represents a logical service composed of multiple independent replicas.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid


class ServiceGroupManager:
    """Manages service groups and their replicas."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Group ID -> Group metadata
        self.groups: Dict[str, Dict[str, Any]] = {}
        # Replica ID -> Group ID mapping
        self.replica_to_group: Dict[str, str] = {}
    
    def create_group(self, recipe_name: str, num_replicas: int, config: Dict[str, Any] = None) -> str:
        """Create a new service group.
        
        Args:
            recipe_name: The recipe name for this group
            num_replicas: Number of replicas in the group
            config: Optional configuration for the group
            
        Returns:
            The group ID (format: "sg-<uuid>")
        """
        group_id = f"sg-{uuid.uuid4().hex[:12]}"
        
        self.groups[group_id] = {
            "id": group_id,
            "name": f"{recipe_name}-group",  # Add name field for API compatibility
            "recipe_name": recipe_name,
            "num_replicas": num_replicas,
            "replicas": [],  # Will be populated as replicas are added
            "config": config or {},
            "created_at": datetime.now().isoformat(),
            "status": "pending"  # Overall group status
        }
        
        self.logger.info(f"Created service group {group_id} with {num_replicas} replicas")
        return group_id
    
    def add_replica(self, group_id: str, replica_id: str, replica_index: int, 
                    status: str = "pending") -> None:
        """Add a replica to a group.
        
        Args:
            group_id: The service group ID
            replica_id: The individual replica service ID (SLURM job ID)
            replica_index: The index of this replica (0, 1, 2, ...)
            status: Initial status of the replica
        """
        if group_id not in self.groups:
            raise ValueError(f"Group {group_id} not found")
        
        replica_info = {
            "id": replica_id,
            "index": replica_index,
            "status": status,
            "added_at": datetime.now().isoformat()
        }
        
        self.groups[group_id]["replicas"].append(replica_info)
        self.replica_to_group[replica_id] = group_id
        
        self.logger.debug(f"Added replica {replica_id} (index {replica_index}) to group {group_id}")
    
    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get group metadata by ID."""
        return self.groups.get(group_id)
    
    def get_group_for_replica(self, replica_id: str) -> Optional[str]:
        """Get the group ID for a given replica ID."""
        return self.replica_to_group.get(replica_id)
    
    def is_group(self, service_id: str) -> bool:
        """Check if a service ID is a group ID."""
        return service_id.startswith("sg-")
    
    def update_replica_status(self, replica_id: str, status: str) -> None:
        """Update the status of a specific replica.
        
        Args:
            replica_id: The replica service ID
            status: The new status
        """
        group_id = self.replica_to_group.get(replica_id)
        if not group_id:
            self.logger.warning(f"Replica {replica_id} not found in any group")
            return
        
        group = self.groups[group_id]
        for replica in group["replicas"]:
            if replica["id"] == replica_id:
                replica["status"] = status
                self.logger.debug(f"Updated replica {replica_id} status to {status}")
                break
        
        # Update overall group status based on replica statuses
        self._update_group_status(group_id)
    
    def _update_group_status(self, group_id: str) -> None:
        """Update the overall group status based on replica statuses.
        
        Logic:
        - If all replicas are 'completed' or 'failed', group is 'completed'
        - If any replica is 'running', group is 'running'
        - If any replica is 'starting', group is 'starting'
        - If all replicas are 'pending'/'building', group is 'pending'
        """
        group = self.groups[group_id]
        replica_statuses = [r["status"] for r in group["replicas"]]
        
        if not replica_statuses:
            group["status"] = "pending"
            return
        
        # Count status types
        running_count = sum(1 for s in replica_statuses if s == "running")
        starting_count = sum(1 for s in replica_statuses if s == "starting")
        completed_count = sum(1 for s in replica_statuses if s in ["completed", "failed", "cancelled"])
        
        # Determine group status
        if completed_count == len(replica_statuses):
            group["status"] = "completed"
        elif running_count > 0:
            group["status"] = "running"
        elif starting_count > 0:
            group["status"] = "starting"
        else:
            group["status"] = "pending"
    
    def get_healthy_replicas(self, group_id: str) -> List[Dict[str, Any]]:
        """Get list of healthy (running) replicas in a group.
        
        Args:
            group_id: The service group ID
            
        Returns:
            List of replica info dicts that are in 'running' status
        """
        group = self.groups.get(group_id)
        if not group:
            return []
        
        healthy = [r for r in group["replicas"] if r["status"] == "running"]
        self.logger.debug(f"Group {group_id} has {len(healthy)}/{len(group['replicas'])} healthy replicas")
        return healthy
    
    def get_all_replica_ids(self, group_id: str) -> List[str]:
        """Get all replica IDs for a group.
        
        Args:
            group_id: The service group ID
            
        Returns:
            List of replica service IDs
        """
        group = self.groups.get(group_id)
        if not group:
            return []
        
        return [r["id"] for r in group["replicas"]]
    
    def list_groups(self) -> List[Dict[str, Any]]:
        """List all service groups."""
        return list(self.groups.values())
    
    def delete_group(self, group_id: str) -> bool:
        """Delete a service group.
        
        Args:
            group_id: The service group ID
            
        Returns:
            True if group was deleted, False if not found
        """
        if group_id not in self.groups:
            return False
        
        # Remove replica mappings
        group = self.groups[group_id]
        for replica in group["replicas"]:
            self.replica_to_group.pop(replica["id"], None)
        
        # Remove group
        del self.groups[group_id]
        self.logger.info(f"Deleted service group {group_id}")
        return True
