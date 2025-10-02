"""
Data models for the server service.
"""

from typing import Dict, Any, Optional
from datetime import datetime


class Service:
    """Service model representing a running containerized service."""
    
    def __init__(self, id: str, name: str, recipe_name: str, status: str, 
                 nodes: int = 1, config: Dict[str, Any] = None):
        self.id = id
        self.name = name
        self.recipe_name = recipe_name
        self.status = status
        self.nodes = nodes
        self.config = config or {}
        self.created_at = datetime.now().isoformat()
        self.output: Optional[str] = None
        self.error: Optional[str] = None
        self.return_code: Optional[int] = None


class Recipe:
    """Recipe model representing a service template."""
    
    def __init__(self, name: str, description: str, category: str, version: str):
        self.name = name
        self.description = description
        self.category = category
        self.version = version