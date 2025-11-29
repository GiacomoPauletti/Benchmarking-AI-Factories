"""
Recipe loader utility for managing service recipes.

Centralizes recipe loading, parsing, validation, and path resolution.
Returns validated Recipe objects with proper typing.
"""

from pathlib import Path
from typing import List, Optional, Tuple, Union
import yaml
import logging

from .models import Recipe, InferenceRecipe, VectorDbRecipe, StorageRecipe, create_recipe


logger = logging.getLogger(__name__)


class RecipeLoader:
    """Handles loading and parsing of service recipe YAML files.
    
    Returns validated Recipe objects with proper type coercion and validation.
    """
    
    def __init__(self, recipes_dir: Union[str, Path]):
        """
        Initialize the recipe loader.
        
        Args:
            recipes_dir: Path to the recipes directory
        """
        self.recipes_dir = Path(recipes_dir)
        self.logger = logging.getLogger(__name__)
        self._cache: dict[str, Recipe] = {}
    
    def load(self, recipe_name: str) -> Optional[Recipe]:
        """
        Load and validate a recipe by name.
        
        Args:
            recipe_name: Recipe name (e.g., "inference/vllm-single-node" or "vllm-single-node")
        
        Returns:
            Validated Recipe object, or None if not found
        """
        # Check cache first
        if recipe_name in self._cache:
            return self._cache[recipe_name]
        
        # Resolve to canonical name and path
        canonical_name, recipe_path = self._resolve_recipe_path(recipe_name)
        
        # Also check cache with canonical name
        if canonical_name in self._cache:
            # Cache under original name too for faster lookup
            self._cache[recipe_name] = self._cache[canonical_name]
            return self._cache[canonical_name]
        
        if not recipe_path or not recipe_path.exists():
            self.logger.warning("Recipe not found: %s", recipe_name)
            return None
        
        try:
            with open(recipe_path, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data:
                self.logger.error("Recipe file is empty: %s", recipe_path)
                return None
            
            # Add path information using canonical name
            data['path'] = canonical_name
            
            # Create validated recipe
            recipe = create_recipe(data)
            
            # Cache under both original and canonical names
            self._cache[recipe_name] = recipe
            if canonical_name != recipe_name:
                self._cache[canonical_name] = recipe
            
            return recipe
            
        except yaml.YAMLError as e:
            self.logger.error("Failed to parse recipe YAML %s: %s", recipe_name, e)
            return None
        except ValueError as e:
            self.logger.error("Recipe validation failed for %s: %s", recipe_name, e)
            return None
        except Exception as e:
            self.logger.error("Failed to load recipe %s: %s", recipe_name, e)
            return None
    
    def _resolve_recipe_path(self, recipe_name: str) -> Tuple[str, Optional[Path]]:
        """
        Resolve recipe name to canonical name and full path.
        
        Handles both formats:
        - "category/name" (e.g., "inference/vllm-single-node")
        - "name" (searches all categories)
        
        Args:
            recipe_name: Recipe name with or without category
        
        Returns:
            Tuple of (canonical_name, path) where path may be None if not found
        """
        # If recipe_name includes category (e.g., "inference/vllm")
        if '/' in recipe_name:
            candidate = self.recipes_dir / f"{recipe_name}.yaml"
            if candidate.exists():
                return recipe_name, candidate
            return recipe_name, None
        
        # Search all category directories for the recipe
        if not self.recipes_dir.exists():
            return recipe_name, None
        
        for category_dir in self.recipes_dir.iterdir():
            if category_dir.is_dir():
                candidate = category_dir / f"{recipe_name}.yaml"
                if candidate.exists():
                    canonical_name = f"{category_dir.name}/{recipe_name}"
                    return canonical_name, candidate
        
        return recipe_name, None
    
    def list_all(self) -> List[Recipe]:
        """
        List all available recipes.
        
        Returns:
            List of validated Recipe objects
        """
        if not self.recipes_dir.exists():
            self.logger.warning("Directory folder %s does not exist", self.recipes_dir)
            return []
        
        recipes = []
        for category_dir in self.recipes_dir.iterdir():
            self.logger.debug(f"Listing recipes in directory {category_dir}")
            if not category_dir.is_dir():
                continue
            
            for recipe_file in category_dir.glob("*.yaml"):
                try:
                    recipe_name = f"{category_dir.name}/{recipe_file.stem}"
                    recipe = self.load(recipe_name)
                    if recipe:
                        recipes.append(recipe)
                except Exception as e:
                    self.logger.error("Failed to load recipe %s: %s", recipe_file, e)
        
        self.logger.debug(f"Found recipes: {recipes}")
        return recipes
    
    def list_by_category(self, category: str) -> List[Recipe]:
        """
        List all recipes in a specific category.
        
        Args:
            category: Category name (e.g., "inference", "vector-db")
        
        Returns:
            List of validated Recipe objects
        """
        recipes = []
        category_dir = self.recipes_dir / category
        
        if not category_dir.exists() or not category_dir.is_dir():
            return recipes
        
        for recipe_file in category_dir.glob("*.yaml"):
            try:
                recipe_name = f"{category}/{recipe_file.stem}"
                recipe = self.load(recipe_name)
                if recipe:
                    recipes.append(recipe)
            except Exception as e:
                self.logger.error("Failed to load recipe %s: %s", recipe_file, e)
        
        return recipes
    
    def get_recipe_port(self, recipe_name: str) -> Optional[int]:
        """
        Get the default port from a recipe.
        
        Args:
            recipe_name: Recipe name
        
        Returns:
            Port number, or None if not specified
        """
        recipe = self.load(recipe_name)
        if not recipe:
            return None
        return recipe.default_port
    
    def clear_cache(self):
        """Clear the recipe cache."""
        self._cache.clear()
    
    def reload(self, recipe_name: str) -> Optional[Recipe]:
        """
        Force reload a recipe from disk, bypassing cache.
        
        Args:
            recipe_name: Recipe name
            
        Returns:
            Freshly loaded Recipe object
        """
        if recipe_name in self._cache:
            del self._cache[recipe_name]
        return self.load(recipe_name)
