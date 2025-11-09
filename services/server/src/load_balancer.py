"""
Load Balancer

Implements load balancing strategies for distributing requests across service replicas.
"""

import logging
from typing import Dict, List, Optional, Any
from collections import defaultdict


class LoadBalancer:
    """ Very Simple Round-robin load balancer for service groups."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Track the next replica index to use for each group (round-robin)
        self.next_replica_index: Dict[str, int] = defaultdict(int)
    
    def select_replica(self, group_id: str, healthy_replicas: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Select a replica using round-robin strategy.
        
        Args:
            group_id: The service group ID
            healthy_replicas: List of healthy replica info dicts
            
        Returns:
            Selected replica info dict, or None if no healthy replicas
        """
        if not healthy_replicas:
            self.logger.warning(f"No healthy replicas available for group {group_id}")
            return None
        
        # Get current index and increment for next time
        current_index = self.next_replica_index[group_id]
        self.next_replica_index[group_id] = (current_index + 1) % len(healthy_replicas)
        
        # Select replica
        selected = healthy_replicas[current_index]
        self.logger.debug(f"Selected replica {selected['id']} (index {current_index}/{len(healthy_replicas)-1}) for group {group_id}")
        
        return selected
    
    def reset_group(self, group_id: str) -> None:
        """Reset round-robin state for a group.
        
        Useful when group composition changes (replicas added/removed).
        """
        if group_id in self.next_replica_index:
            del self.next_replica_index[group_id]
            self.logger.debug(f"Reset load balancer state for group {group_id}")
