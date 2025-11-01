"""Recipe builders for generating SLURM job scripts.

This module provides a plugin-based architecture for generating container
orchestration scripts tailored to different recipe types (inference, vector-db, storage).

Architecture:
- Category-level builders: Generic builders for recipe categories (fallback)
- Recipe-specific builders: Specialized builders for specific recipes (e.g., vLLM, Qdrant)

Adding a new recipe-specific builder:
1. Create a new builder class that extends the appropriate category builder
2. Register it using BuilderRegistry.register_recipe('category/recipe-name', BuilderClass)
"""

from .base import RecipeScriptBuilder, ScriptPaths
from .registry import BuilderRegistry
from .inference_builder import InferenceRecipeBuilder
from .vllm_builder import VllmInferenceBuilder
from .vector_db_builder import VectorDbRecipeBuilder
from .qdrant_builder import QdrantVectorDbBuilder
from .storage_builder import StorageRecipeBuilder

# Register category-level builders (used as fallbacks)
BuilderRegistry.register('inference', InferenceRecipeBuilder)
BuilderRegistry.register('vector-db', VectorDbRecipeBuilder)
BuilderRegistry.register('storage', StorageRecipeBuilder)

# Register recipe-specific builders (take precedence over category builders)
# Inference services
BuilderRegistry.register_recipe('inference/vllm', VllmInferenceBuilder)

# Vector database services
BuilderRegistry.register_recipe('vector-db/qdrant', QdrantVectorDbBuilder)

# Storage services
# (Add specific builders here as needed, e.g., MinioStorageBuilder, PostgresStorageBuilder)

__all__ = [
    'RecipeScriptBuilder',
    'ScriptPaths',
    'BuilderRegistry',
    'InferenceRecipeBuilder',
    'VllmInferenceBuilder',
    'VectorDbRecipeBuilder',
    'QdrantVectorDbBuilder',
    'StorageRecipeBuilder',
]
