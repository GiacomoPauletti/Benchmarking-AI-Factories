"""Base class for recipe script builders.

Defines the interface that all recipe builders must implement for generating
SLURM job scripts with container orchestration.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from service_orchestration.recipes import Recipe, RecipeResources


@dataclass
class ScriptPaths:
    """Container paths needed for script generation."""
    def_path: str      # Path to Apptainer .def file
    sif_path: str      # Path to Apptainer .sif image
    log_dir: str       # Directory for job logs
    remote_base_path: str  # Base path on remote filesystem
    

class RecipeScriptBuilder(ABC):
    """Abstract base class for recipe-specific script builders.
    
    Each recipe category (inference, vector-db, storage) implements this interface
    to provide category-specific container orchestration logic while keeping
    the SLURM deployer generic and reusable.
    """
    
    @abstractmethod
    def build_environment_section(self, recipe_env: Dict[str, str]) -> str:
        """Build the environment variable export section for the job script.
        
        Args:
            recipe_env: Environment variables from recipe definition
            
        Returns:
            Bash script section with environment variable exports
        """
        pass
    
    @abstractmethod
    def build_container_build_block(self, paths: ScriptPaths) -> str:
        """Build the bash block that ensures the container image exists.
        
        Args:
            paths: Container and filesystem paths
            
        Returns:
            Bash script block for building/checking container image
        """
        pass
    
    @abstractmethod
    def build_run_block(self, paths: ScriptPaths, resources: "RecipeResources", 
                       recipe: "Recipe") -> str:
        """Build the bash block that runs the container (single-node).
        
        Args:
            paths: Container and filesystem paths
            resources: RecipeResources object with cpu, memory, gpu, etc.
            recipe: Recipe object with full configuration
            
        Returns:
            Bash script block for running the container
        """
        pass
    
    def supports_distributed(self) -> bool:
        """Check if this builder supports replica group execution.
        
        Returns:
            True if replica group execution is supported, False otherwise
        """
        return False
    
    def build_replica_group_run_block(self, paths: ScriptPaths, resources: "RecipeResources",
                                      recipe: "Recipe", 
                                      config: Dict[str, Any]) -> str:
        """Build the bash block for replica group execution.
        
        This is optional - only implement if the recipe type supports replica groups.
        
        Args:
            paths: Container and filesystem paths
            resources: RecipeResources object with resource requirements
            recipe: Recipe object with full configuration
            config: User-provided configuration overrides
            
        Returns:
            Bash script block for replica group execution
            
        Raises:
            NotImplementedError: If replica groups are not supported
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support replica group execution"
        )
