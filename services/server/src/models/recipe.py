"""
Recipe data model.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class Recipe:
    """Represents a service deployment recipe."""
    
    name: str
    category: str  # inference, storage, vector-db
    description: str
    version: str
    image: str
    ports: List[int]
    environment: Dict[str, str]
    resources: Dict[str, Any]
    deployment_config: Dict[str, Any]
    health_check: Optional[Dict[str, Any]] = None
    
    def validate(self) -> bool:
        """Validate recipe configuration."""
        required_fields = ["name", "category", "image", "ports"]
        return all(hasattr(self, field) and getattr(self, field) for field in required_fields)
    
    def get_resource_requirements(self) -> Dict[str, Any]:
        """Get resource requirements for the recipe."""
        return self.resources