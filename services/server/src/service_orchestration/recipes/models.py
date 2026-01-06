"""
Recipe models with Pydantic schema validation.

This module defines the data models for service recipes with proper validation,
type coercion, and category-specific subclasses.
"""

from enum import Enum
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator
import logging

logger = logging.getLogger(__name__)


class RecipeCategory(str, Enum):
    """Valid recipe categories."""
    INFERENCE = "inference"
    VECTOR_DB = "vector-db"
    STORAGE = "storage"


class DistanceMetric(str, Enum):
    """Valid distance metrics for vector databases."""
    COSINE = "Cosine"
    EUCLID = "Euclid"
    DOT = "Dot"


class RecipeResources(BaseModel):
    """Resource requirements for a recipe."""
    nodes: int = Field(default=1, ge=1, description="Number of compute nodes")
    cpu: int = Field(default=1, ge=1, description="Number of CPUs per node")
    memory: str = Field(default="4G", description="Memory allocation (e.g., '64G', '4Gi')")
    gpu: int = Field(default=0, ge=0, description="Number of GPUs per node")
    time_limit: int = Field(default=60, ge=1, description="Job time limit in minutes")
    storage: Optional[str] = Field(default=None, description="Storage allocation (e.g., '100Gi')")
    
    @field_validator('nodes', 'cpu', 'gpu', 'time_limit', mode='before')
    @classmethod
    def coerce_to_int(cls, v):
        """Coerce string values to integers."""
        if isinstance(v, str):
            return int(v)
        return v
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert to simplified API response format."""
        result = {
            "nodes": self.nodes,
            "cpu": self.cpu,
            "memory": self.memory,
            "gpu": self.gpu,
            "time_limit": self.time_limit,
        }
        if self.storage:
            result["storage"] = self.storage
        return result


class RecipeParameter(BaseModel):
    """Documentation for a recipe parameter."""
    description: str = Field(..., description="Human-readable description")
    type: str = Field(..., description="Parameter type (string, integer, float, boolean)")
    default: Optional[Any] = Field(default=None, description="Default value")
    required: bool = Field(default=False, description="Whether the parameter is required")
    location: str = Field(default="environment", description="Where param is applied (root, resources, environment)")
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert to simplified API response format."""
        return {
            "description": self.description,
            "type": self.type,
            "default": self.default,
            "required": self.required,
            "location": self.location,
        }


class RecipeHealthCheck(BaseModel):
    """Health check configuration for a recipe."""
    endpoint: Optional[str] = Field(default=None, description="Health check HTTP endpoint")
    command: Optional[List[str]] = Field(default=None, description="Health check command")
    interval: int = Field(default=30, ge=1, description="Check interval in seconds")
    timeout: int = Field(default=10, ge=1, description="Check timeout in seconds")
    retries: int = Field(default=3, ge=1, description="Number of retries")
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert to simplified API response format."""
        result = {
            "interval": self.interval,
            "timeout": self.timeout,
            "retries": self.retries,
        }
        if self.endpoint:
            result["endpoint"] = self.endpoint
        if self.command:
            result["command"] = self.command
        return result


class RecipeDeploymentConfig(BaseModel):
    """Deployment configuration for storage recipes."""
    replicas: int = Field(default=1, ge=1, description="Number of replicas")
    storage_class: Optional[str] = Field(default=None, description="Storage class")
    persistence: bool = Field(default=True, description="Enable persistence")
    bucket_policy: Optional[str] = Field(default=None, description="Bucket access policy (MinIO)")
    backup_schedule: Optional[str] = Field(default=None, description="Cron schedule for backups (Postgres)")
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert to simplified API response format."""
        result = {
            "replicas": self.replicas,
            "persistence": self.persistence,
        }
        if self.storage_class:
            result["storage_class"] = self.storage_class
        if self.bucket_policy:
            result["bucket_policy"] = self.bucket_policy
        if self.backup_schedule:
            result["backup_schedule"] = self.backup_schedule
        return result


class Recipe(BaseModel):
    """Base recipe model with common fields and validation."""
    
    # Required fields
    name: str = Field(..., min_length=1, description="Recipe identifier")
    category: RecipeCategory = Field(..., description="Recipe category")
    
    # Optional common fields
    description: Optional[str] = Field(default=None, description="Human-readable description")
    version: Optional[str] = Field(default="1.0.0", description="Version number")
    image: Optional[str] = Field(default=None, description="Container image path")
    container_def: Optional[str] = Field(default=None, description="Container definition file")
    ports: List[int] = Field(default_factory=list, description="Network ports exposed")
    environment: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    resources: RecipeResources = Field(default_factory=RecipeResources)
    parameters: Dict[str, RecipeParameter] = Field(default_factory=dict, description="Parameter documentation")
    
    # Path information (set by loader)
    path: Optional[str] = Field(default=None, description="Recipe path (category/name)")
    
    # For type discrimination in subclasses
    model_config = {"extra": "allow"}  # Allow extra fields for subclasses
    
    @field_validator('ports', mode='before')
    @classmethod
    def ensure_ports_list(cls, v):
        """Ensure ports is always a list."""
        if v is None:
            return []
        if isinstance(v, int):
            return [v]
        return v
    
    @field_validator('parameters', mode='before')
    @classmethod
    def parse_parameters(cls, v):
        """Parse parameters dict into RecipeParameter objects."""
        if not v:
            return {}
        result = {}
        for name, param_data in v.items():
            if isinstance(param_data, dict):
                result[name] = RecipeParameter(**param_data)
            elif isinstance(param_data, RecipeParameter):
                result[name] = param_data
        return result
    
    @property
    def default_port(self) -> Optional[int]:
        """Get the default (first) port from the recipe."""
        return self.ports[0] if self.ports else None
    
    @property
    def is_replica_group(self) -> bool:
        """Check if this recipe supports replica groups."""
        return False  # Override in subclasses
    
    def get_container_paths(self, recipes_dir: str) -> Dict[str, str]:
        """Get container-related paths based on recipe configuration."""
        from pathlib import Path
        base_dir = Path(recipes_dir) / self.category.value
        
        # Determine definition file path
        if self.container_def:
            def_path = str(base_dir / self.container_def)
        else:
            def_path = str(base_dir / f"{self.name}.def")
        
        # Determine image file path
        if self.image:
            sif_path = str(base_dir / self.image)
        else:
            sif_path = str(base_dir / f"{self.name}.sif")
        
        return {
            "def_path": def_path,
            "sif_path": sif_path,
        }
    
    def merge_config(self, config: Dict[str, Any]) -> "Recipe":
        """Create a new recipe with merged configuration.
        
        Args:
            config: User-provided configuration to merge
            
        Returns:
            New Recipe instance with merged values
        """
        # Start with current values as dict
        data = self.model_dump()
        
        # Merge resources
        if "resources" in config:
            for key, value in config["resources"].items():
                data["resources"][key] = value
        
        # Direct resource overrides (legacy support)
        for key in ['nodes', 'cpu', 'memory', 'gpu', 'time_limit']:
            if key in config:
                data["resources"][key] = config[key]
        
        # Merge environment
        if "environment" in config:
            data["environment"].update(config["environment"])
        
        # Handle replica port
        if "replica_port" in config:
            data["environment"]["VLLM_PORT"] = str(config["replica_port"])
            
        # Handle model override (update environment for single-node jobs)
        if "model" in config:
            data["environment"]["VLLM_MODEL"] = config["model"]
            
        # Handle max model len override
        if "max_model_len" in config:
            data["environment"]["VLLM_MAX_MODEL_LEN"] = str(config["max_model_len"])
        
        # Copy other config values to the recipe
        for key in ['gpu_per_replica', 'base_port', 'nproc_per_node', 'master_port',
                    'model', 'max_model_len', 'gpu_memory_utilization']:
            if key in config:
                data[key] = config[key]
        
        return self.__class__(**data)
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert to simplified API response format."""
        result = {
            "name": self.name,
            "category": self.category.value,
            "version": self.version,
            "description": self.description,
            "ports": self.ports,
            "resources": self.resources.to_api_response(),
        }
        if self.path:
            result["path"] = self.path
        if self.image:
            result["image"] = self.image
        return result


class InferenceRecipe(Recipe):
    """Recipe for inference services (vLLM, etc.)."""
    
    # Inference-specific fields
    gpu_per_replica: Optional[int] = Field(default=None, ge=1, description="GPUs per replica for replica groups")
    base_port: int = Field(default=8001, ge=1, description="Starting port for replicas")
    nproc_per_node: Optional[int] = Field(default=None, ge=1, description="Processes per node")
    master_port: Optional[int] = Field(default=None, description="Master port for distributed training")
    
    @field_validator('gpu_per_replica', 'base_port', 'nproc_per_node', 'master_port', mode='before')
    @classmethod
    def coerce_optional_int(cls, v):
        """Coerce string values to integers."""
        if v is None:
            return None
        if isinstance(v, str):
            return int(v)
        return v
    
    @property
    def is_replica_group(self) -> bool:
        """Check if this recipe supports replica groups."""
        return self.gpu_per_replica is not None
    
    @property
    def replicas_per_node(self) -> int:
        """Calculate number of replicas per node."""
        if not self.gpu_per_replica:
            return 1
        total_gpus = self.resources.gpu
        if total_gpus and self.gpu_per_replica:
            return total_gpus // self.gpu_per_replica
        return 1
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert to simplified API response format."""
        result = super().to_api_response()
        if self.gpu_per_replica:
            result["gpu_per_replica"] = self.gpu_per_replica
            result["replicas_per_node"] = self.replicas_per_node
        result["base_port"] = self.base_port
        return result


class VectorDbRecipe(Recipe):
    """Recipe for vector database services (Qdrant, Chroma, etc.)."""
    
    # Vector DB specific fields could be added here
    # For now, inherits everything from base Recipe
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert to simplified API response format."""
        result = super().to_api_response()
        result["type"] = "vector-db"
        return result


class StorageRecipe(Recipe):
    """Recipe for storage services (MinIO, PostgreSQL, etc.)."""
    
    # Storage-specific fields
    deployment_config: Optional[RecipeDeploymentConfig] = Field(default=None)
    health_check: Optional[RecipeHealthCheck] = Field(default=None)
    
    @field_validator('deployment_config', mode='before')
    @classmethod
    def parse_deployment_config(cls, v):
        """Parse deployment config dict."""
        if v is None:
            return None
        if isinstance(v, dict):
            return RecipeDeploymentConfig(**v)
        return v
    
    @field_validator('health_check', mode='before')
    @classmethod
    def parse_health_check(cls, v):
        """Parse health check dict."""
        if v is None:
            return None
        if isinstance(v, dict):
            return RecipeHealthCheck(**v)
        return v
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert to simplified API response format."""
        result = super().to_api_response()
        result["type"] = "storage"
        if self.deployment_config:
            result["deployment"] = self.deployment_config.to_api_response()
        if self.health_check:
            result["health_check"] = self.health_check.to_api_response()
        return result


def create_recipe(data: Dict[str, Any]) -> Recipe:
    """Factory function to create the appropriate Recipe subclass.
    
    Args:
        data: Raw recipe data from YAML
        
    Returns:
        Appropriate Recipe subclass instance
        
    Raises:
        ValueError: If required fields are missing or invalid
    """
    if not data:
        raise ValueError("Recipe data cannot be empty")
    
    if "name" not in data:
        raise ValueError("Recipe must have a 'name' field")
    
    if "category" not in data:
        raise ValueError("Recipe must have a 'category' field")
    
    category = data.get("category")
    
    try:
        if category == "inference":
            return InferenceRecipe(**data)
        elif category == "vector-db":
            return VectorDbRecipe(**data)
        elif category == "storage":
            return StorageRecipe(**data)
        else:
            # Default to base Recipe for unknown categories
            logger.warning(f"Unknown recipe category '{category}', using base Recipe")
            return Recipe(**data)
    except Exception as e:
        raise ValueError(f"Failed to create recipe '{data.get('name')}': {e}")
