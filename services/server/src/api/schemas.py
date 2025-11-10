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
    """Schema for service responses.
    
    For regular services, this contains basic service information.
    For service groups (replicas), includes additional fields for group management.
    """
    id: str  # This is the SLURM job ID (or group ID for service groups)
    name: str
    recipe_name: str
    status: str
    config: Dict[str, Any]
    created_at: str
    
    # Optional fields for replica groups
    type: Optional[str] = None  # "group" or "replica_group"
    replicas: Optional[List[Dict[str, Any]]] = None  # List of replica info dicts
    num_replicas: Optional[int] = None  # Total number of replicas
    
    # Optional fields for replica groups
    num_nodes: Optional[int] = None  # Number of nodes
    replicas_per_node: Optional[int] = None  # Replicas per node
    total_replicas: Optional[int] = None  # Total replicas across all nodes
    node_jobs: Optional[List[Dict[str, Any]]] = None  # Node job structure
    
    # Optional fields for individual replicas
    group_id: Optional[str] = None  # For replicas: ID of parent group
    replica_index: Optional[int] = None  # For replicas: index within group


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