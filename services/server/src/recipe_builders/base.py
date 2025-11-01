"""Base class for recipe script builders.

Defines the interface that all recipe builders must implement for generating
SLURM job scripts with container orchestration.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from dataclasses import dataclass


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
    def build_run_block(self, paths: ScriptPaths, resources: Dict[str, Any], 
                       recipe: Dict[str, Any]) -> str:
        """Build the bash block that runs the container (single-node).
        
        Args:
            paths: Container and filesystem paths
            resources: Resource requirements (cpu, memory, gpu, etc.)
            recipe: Full recipe configuration
            
        Returns:
            Bash script block for running the container
        """
        pass
    
    def supports_distributed(self) -> bool:
        """Check if this builder supports distributed execution.
        
        Returns:
            True if distributed execution is supported, False otherwise
        """
        return False
    
    def build_distributed_run_block(self, paths: ScriptPaths, resources: Dict[str, Any],
                                   recipe: Dict[str, Any], 
                                   distributed_cfg: Dict[str, Any]) -> str:
        """Build the bash block for distributed multi-node execution.
        
        This is optional - only implement if the recipe type supports distributed execution.
        
        Args:
            paths: Container and filesystem paths
            resources: Resource requirements
            recipe: Full recipe configuration
            distributed_cfg: Distributed execution configuration
            
        Returns:
            Bash script block for distributed execution
            
        Raises:
            NotImplementedError: If distributed execution is not supported
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support distributed execution"
        )
