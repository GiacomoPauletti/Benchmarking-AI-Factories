"""
Service data model.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime


@dataclass
class Service:
    """Represents a running service instance."""
    
    id: str
    name: str
    recipe_name: str
    status: str
    nodes: int
    config: Dict[str, Any]
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    def is_running(self) -> bool:
        """Check if service is currently running."""
        return self.status == "running"
    
    def update_status(self, new_status: str) -> None:
        """Update service status."""
        self.status = new_status
        self.updated_at = datetime.now()