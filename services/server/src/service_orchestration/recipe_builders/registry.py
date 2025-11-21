"""Registry for recipe script builders.

Provides a centralized registry for mapping recipe categories and specific
recipe names to their corresponding script builder implementations.
"""

from typing import Dict, Type, Optional
from .base import RecipeScriptBuilder


class BuilderRegistry:
    """Registry for recipe script builders.
    
    Supports both category-level builders (e.g., 'inference') and
    recipe-specific builders (e.g., 'inference/vllm').
    """
    
    # Category-level builders (fallback)
    _category_builders: Dict[str, Type[RecipeScriptBuilder]] = {}
    
    # Recipe-specific builders (takes precedence)
    _recipe_builders: Dict[str, Type[RecipeScriptBuilder]] = {}
    
    @classmethod
    def register(cls, category: str, builder_class: Type[RecipeScriptBuilder]):
        """Register a builder for a recipe category.
        
        Args:
            category: Recipe category (e.g., 'inference', 'vector-db', 'storage')
            builder_class: Builder class to handle scripts for this category
        """
        cls._category_builders[category] = builder_class
    
    @classmethod
    def register_recipe(cls, recipe_name: str, builder_class: Type[RecipeScriptBuilder]):
        """Register a builder for a specific recipe.
        
        This takes precedence over category-level builders.
        
        Args:
            recipe_name: Full recipe name including category (e.g., 'inference/vllm')
            builder_class: Builder class to handle scripts for this specific recipe
        """
        cls._recipe_builders[recipe_name] = builder_class
    
    @classmethod
    def get_builder(cls, category: str, recipe_name: Optional[str] = None) -> Optional[Type[RecipeScriptBuilder]]:
        """Get the builder class for a recipe.
        
        First checks for recipe-specific builders, then falls back to category builders.
        
        Args:
            category: Recipe category
            recipe_name: Optional specific recipe name (e.g., 'vllm' or 'inference/vllm')
            
        Returns:
            Builder class for the recipe, or None if not registered
        """
        # Try recipe-specific builder first (if recipe_name provided)
        if recipe_name:
            # Try with category prefix
            full_name = f"{category}/{recipe_name}"
            if full_name in cls._recipe_builders:
                return cls._recipe_builders[full_name]
            
            # Try without category prefix (in case it's already included)
            if recipe_name in cls._recipe_builders:
                return cls._recipe_builders[recipe_name]
        
        # Fall back to category builder
        return cls._category_builders.get(category)
    
    @classmethod
    def create_builder(cls, category: str, recipe_name: Optional[str] = None, **kwargs) -> RecipeScriptBuilder:
        """Create a builder instance for a recipe.
        
        Args:
            category: Recipe category
            recipe_name: Optional specific recipe name for recipe-specific builders
            **kwargs: Arguments to pass to the builder constructor
            
        Returns:
            Initialized builder instance
            
        Raises:
            ValueError: If no builder is registered for the category/recipe
        """
        builder_class = cls.get_builder(category, recipe_name)
        if builder_class is None:
            raise ValueError(
                f"No builder registered for category '{category}' or recipe '{recipe_name}'. "
                f"Available categories: {list(cls._category_builders.keys())}, "
                f"Available recipes: {list(cls._recipe_builders.keys())}"
            )
        return builder_class(**kwargs)
    
    @classmethod
    def list_categories(cls) -> list:
        """List all registered recipe categories.
        
        Returns:
            List of registered category names
        """
        return list(cls._category_builders.keys())
    
    @classmethod
    def list_recipes(cls) -> list:
        """List all registered recipe-specific builders.
        
        Returns:
            List of registered recipe names
        """
        return list(cls._recipe_builders.keys())
