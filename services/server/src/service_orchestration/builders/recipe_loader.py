"""
Recipe loader utility for managing service recipes.

Centralizes recipe loading, parsing, and path resolution.
"""

from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import yaml
import logging


class RecipeLoader:
    """Handles loading and parsing of service recipe YAML files."""
    
    def __init__(self, recipes_dir: Path):
        """
        Initialize the recipe loader.
        
        Args:
            recipes_dir: Path to the recipes directory
        """
        self.recipes_dir = Path(recipes_dir)
        self.logger = logging.getLogger(__name__)
    
    def load(self, recipe_name: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Load a recipe by name with smart path resolution.
        
        Args:
            recipe_name: Recipe name (e.g., "inference/vllm" or "vllm")
        
        Returns:
            Recipe data as dict, or None if not found
        """
        canonical_recipe_name, recipe_path = self._resolve_recipe_path(recipe_name)
        
        if not recipe_path or not recipe_path.exists():
            self.logger.warning("Recipe not found: %s", recipe_name)
            return canonical_recipe_name, None
        
        try:
            with open(recipe_path, 'r') as f:
                return canonical_recipe_name, yaml.safe_load(f)
        except Exception as e:
            self.logger.error("Failed to load recipe %s: %s", recipe_name, e)
            return canonical_recipe_name, None
    
    def _resolve_recipe_path(self, recipe_name: str) -> Tuple[str, Optional[Path]]:
        """
        Resolve recipe name to full path.
        
        Handles both formats:
        - "category/name" (e.g., "inference/vllm")
        - "name" (searches all categories)
        
        Args:
            recipe_name: Recipe name with or without category
        
        Returns:
            Path to recipe YAML file, or None if not found
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
                    return f"{category_dir.parts[-1]}/{recipe_name}", candidate
        
        return recipe_name, None
    
    def list_all(self) -> List[Dict[str, Any]]:
        """
        List all available recipes.
        
        Returns:
            List of recipe metadata dicts
        """
        if not self.recipes_dir.exists():
            self.logger.warning("Directory folder %s does not exist", self.recipes_dir)
            return []
        
        recipes = []
        for category_dir in self.recipes_dir.iterdir():
            self.logger.debug(f"Listing recipes in directory {category_dir}")
            if not category_dir.is_dir():
                self.logger.warning("Not a directory")
                continue
            
            for recipe_file in category_dir.glob("*.yaml"):
                try:
                    self.logger.debug(f"Found file {recipe_file}")
                    with open(recipe_file, 'r') as f:
                        recipe_data = yaml.safe_load(f)
                    
                    # Add path information
                    recipe_data['path'] = f"{category_dir.name}/{recipe_file.stem}"
                    recipes.append(recipe_data)
                    
                except Exception as e:
                    self.logger.error("Failed to load recipe %s: %s", recipe_file, e)
        
        self.logger.debug(f"Found recipes: {recipes}")
        return recipes
    
    def list_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        List all recipes in a specific category.
        
        Args:
            category: Category name (e.g., "inference", "vector-db")
        
        Returns:
            List of recipe metadata dicts
        """
        recipes = []
        category_dir = self.recipes_dir / category
        
        if not category_dir.exists() or not category_dir.is_dir():
            return recipes
        
        for recipe_file in category_dir.glob("*.yaml"):
            try:
                with open(recipe_file, 'r') as f:
                    recipe_data = yaml.safe_load(f)
                
                recipe_data['path'] = f"{category}/{recipe_file.stem}"
                recipes.append(recipe_data)
                
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
        recipe_data = self.load(recipe_name)
        if not recipe_data:
            return None
        
        ports = recipe_data.get('ports', [])
        if ports and len(ports) > 0:
            return ports[0]
        
        return None
