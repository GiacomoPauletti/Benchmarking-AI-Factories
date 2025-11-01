"""Qdrant-specific vector database builder.

Extends VectorDbRecipeBuilder with Qdrant-specific storage configuration.
"""

from typing import Dict, Any
from .vector_db_builder import VectorDbRecipeBuilder
from .base import ScriptPaths


class QdrantVectorDbBuilder(VectorDbRecipeBuilder):
    """Qdrant-specific script builder with proper storage path configuration."""
    
    def build_run_block(self, paths: ScriptPaths, resources: Dict[str, Any],
                       recipe: Dict[str, Any]) -> str:
        """Build run block for Qdrant with job-specific storage."""
        project_ws = paths.remote_base_path
        
        # Qdrant uses job-specific storage path (from environment variable)
        # The QDRANT__STORAGE__STORAGE_PATH env var should already be set
        # to something like "/workspace/qdrant_data_${SLURM_JOB_ID}"
        
        return f"""
echo "Starting Qdrant vector database container..."
echo "Binding project workspace: {project_ws} -> /workspace"

# Create workspace directory if it doesn't exist
mkdir -p {project_ws}

# Debug: Print Qdrant-specific environment variables
echo "Qdrant configuration:"
env | grep '^QDRANT_' || echo "No QDRANT_ vars found"

# The storage path will be created inside the container at runtime
# based on QDRANT__STORAGE__STORAGE_PATH environment variable

apptainer run --bind {paths.log_dir}:/app/logs,{project_ws}:/workspace {paths.sif_path} 2>&1
container_exit_code=$?

echo "Container exited with code: $container_exit_code"
if [ $container_exit_code -ne 0 ]; then
    echo "ERROR: Qdrant container failed to run properly"
fi
"""
