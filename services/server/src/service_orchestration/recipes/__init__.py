"""
Recipe management module.

Provides Recipe models with Pydantic validation and RecipeLoader for loading
recipe YAML files with proper schema validation.
"""

from .models import (
    Recipe,
    InferenceRecipe,
    VectorDbRecipe,
    StorageRecipe,
    RecipeResources,
    RecipeParameter,
    RecipeHealthCheck,
    RecipeDeploymentConfig,
    RecipeCategory,
    DistanceMetric,
    create_recipe,
)
from .loader import RecipeLoader


__all__ = [
    # Main classes
    "Recipe",
    "RecipeLoader",
    
    # Recipe subclasses
    "InferenceRecipe",
    "VectorDbRecipe", 
    "StorageRecipe",
    
    # Sub-models
    "RecipeResources",
    "RecipeParameter",
    "RecipeHealthCheck",
    "RecipeDeploymentConfig",
    
    # Enums
    "RecipeCategory",
    "DistanceMetric",
    
    # Factory function
    "create_recipe",
]
