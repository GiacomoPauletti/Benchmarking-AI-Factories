"""
Request/response schemas for the API.
"""

from pydantic import BaseModel, field_validator
from typing import Dict, Any, List, Optional
from datetime import datetime


class ServiceRequest(BaseModel):
    """Schema for service creation requests."""
    recipe_name: str
    config: Dict[str, Any] = {}

    @field_validator('recipe_name')
    @classmethod
    def recipe_name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('recipe_name must not be empty')
        return v


class ServiceResponse(BaseModel):
    """Schema for service responses."""
    id: str  # This is the SLURM job ID
    name: str
    recipe_name: str
    status: str
    config: Dict[str, Any]
    created_at: str


class RecipeResponse(BaseModel):
    """Schema for recipe responses."""
    name: str
    category: str
    description: str
    version: str
    path: str


class HealthResponse(BaseModel):
    """Schema for health check responses."""
    status: str
    timestamp: datetime
    services: Dict[str, str]