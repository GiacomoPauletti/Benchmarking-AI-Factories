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
    
    def create_replica_group(self, recipe_name: str, num_nodes: int, 
                             replicas_per_node: int, total_replicas: int,
                             config: Dict[str, Any] = None) -> str:
        """Create a new replica group.
        
        Args:
            recipe_name: The recipe name for this group
            num_nodes: Number of nodes to allocate
            replicas_per_node: Number of replicas per node
            total_replicas: Total number of replicas (num_nodes * replicas_per_node)
            config: Optional configuration for the group
            
        Returns:
            The group ID (format: "sg-<uuid>")
        """
        group_id = f"sg-{uuid.uuid4().hex[:12]}"
        
        self.groups[group_id] = {
            "id": group_id,
            "name": f"{recipe_name}-group",
            "type": "replica_group",
            "recipe_name": recipe_name,
            "num_nodes": num_nodes,
            "replicas_per_node": replicas_per_node,
            "total_replicas": total_replicas,
            "node_jobs": [],  # List of {job_id, node_index, node, replicas: [...]}
            "config": config or {},
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }
        
        self.logger.info(f"Created replica group {group_id}: {num_nodes} nodes × {replicas_per_node} replicas = {total_replicas} total")
        return group_id
    
    def add_replica(self, group_id: str, job_id: str, node_index: int,
                    replica_index: int, port: int, gpu_id: int,
                    status: str = "pending") -> None:
        """Add a replica to a replica group.
        
        Args:
            group_id: The service group ID
            job_id: The SLURM job ID for this node
            node_index: Index of the node (0, 1, 2, ...)
            replica_index: Global replica index across all nodes
            port: Port this replica listens on
            gpu_id: GPU ID within the node
            status: Initial status
        """
        if group_id not in self.groups:
            raise ValueError(f"Group {group_id} not found")
        
        group = self.groups[group_id]
        
        if group.get("type") != "replica_group":
            raise ValueError(f"Group {group_id} is not a replica group")
        
        # Find or create node_job entry
        node_job = None
        for nj in group["node_jobs"]:
            if nj["job_id"] == job_id:
                node_job = nj
                break
        
        if not node_job:
            node_job = {
                "job_id": job_id,
                "node_index": node_index,
                "node": None,  # Will be filled when job starts
                "replicas": []
            }
            group["node_jobs"].append(node_job)
        
        # Create composite replica ID: job_id:port
        replica_id = f"{job_id}:{port}"
        
        # Add replica
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
        
        # Map replica_id to group
        self.replica_to_group[replica_id] = group_id
        
        self.logger.debug(f"Added replica {replica_id} (GPU {gpu_id}, port {port}) to group {group_id}")
    
    def get_all_replicas_flat(self, group_id: str) -> List[Dict[str, Any]]:
        """Get all replicas in a group as a flat list (works for both group types).
        
        Args:
            group_id: The service group ID
            
        Returns:
            List of replica info dicts
        """
        group = self.groups.get(group_id)
        if not group:
            return []
        
        # All groups use the replica group structure
        all_replicas = []
        for node_job in group.get("node_jobs", []):
            all_replicas.extend(node_job["replicas"])
        return all_replicas
    
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
            replica_id: The replica ID (simple or composite "job_id:port")
            status: New status
        """
        group_id = self.replica_to_group.get(replica_id)
        if not group_id:
            self.logger.warning(f"Replica {replica_id} not found in any group")
            return
        
        group = self.groups.get(group_id)
        if not group:
            return
        
        # All groups use the replica group structure
        for node_job in group.get("node_jobs", []):
            for replica in node_job["replicas"]:
                if replica["id"] == replica_id:
                    replica["status"] = status
                    replica["updated_at"] = datetime.now().isoformat()
                    self.logger.debug(f"Updated replica {replica_id} status to {status}")
                    self._update_group_status(group_id)
                    return
        
        self.logger.warning(f"Replica {replica_id} not found in group {group_id}")
    
    def _update_group_status(self, group_id: str) -> None:
        """Update the overall group status based on replica statuses.
        
        Logic:
        - If all replicas are 'completed' or 'failed', group is 'completed'
        - If any replica is 'running', group is 'running'
        - If any replica is 'starting', group is 'starting'
        - If all replicas are 'pending'/'building', group is 'pending'
        """
        group = self.groups[group_id]
        
        # Get all replicas as flat list
        all_replicas = self.get_all_replicas_flat(group_id)
        replica_statuses = [r["status"] for r in all_replicas]
        
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
    
    def get_healthy_replicas(self, group_id: str) -> List[str]:
        """Get list of healthy replica IDs for a group.
        
        Args:
            group_id: The service group ID
            
        Returns:
            List of replica IDs with status "running" or "healthy"
        """
        all_replicas = self.get_all_replicas_flat(group_id)
        
        healthy_replicas = []
        for replica in all_replicas:
            if replica.get("status") in ["running", "healthy"]:
                healthy_replicas.append(replica["id"])
        
        return healthy_replicas
    
    def get_all_replica_ids(self, group_id: str) -> List[str]:
        """Get all replica IDs for a group.
        
        Args:
            group_id: The service group ID
            
        Returns:
            List of replica service IDs
        """
        all_replicas = self.get_all_replicas_flat(group_id)
        return [r["id"] for r in all_replicas]
    
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
        all_replicas = self.get_all_replicas_flat(group_id)
        for replica in all_replicas:
            self.replica_to_group.pop(replica["id"], None)
        
        # Remove group
        del self.groups[group_id]
        self.logger.info(f"Deleted service group {group_id}")
        return True
