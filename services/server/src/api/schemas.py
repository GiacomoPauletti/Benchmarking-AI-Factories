"""
Request/response schemas for the API.
"""

from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime


class ServiceRequest(BaseModel):
    """Schema for service creation requests."""
    recipe_name: str
    nodes: int = 1
    config: Dict[str, Any] = {}


class ServiceResponse(BaseModel):
    """Schema for service responses."""
    id: str
    name: str
    recipe_name: str
    status: str
    nodes: int
    config: Dict[str, Any]
    output: Optional[str] = None
    error: Optional[str] = None
    return_code: Optional[int] = None
    created_at: str


class RecipeResponse(BaseModel):
    """Schema for recipe responses."""
    name: str
    description: str
    category: str
    version: str


class HealthResponse(BaseModel):
    """Schema for health check responses."""
    status: str
    timestamp: datetime
    services: Dict[str, str]