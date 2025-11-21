"""Builder for storage recipes (MinIO, PostgreSQL, etc.).

Handles container orchestration for storage services with persistent volumes.

This is a generic base builder for storage services. Service-specific builders
can override methods to customize behavior (e.g., MinioStorageBuilder, PostgresStorageBuilder).
"""

from typing import Dict, Any
from .base import RecipeScriptBuilder, ScriptPaths


class StorageRecipeBuilder(RecipeScriptBuilder):
    """Generic script builder for storage recipes.
    
    Provides sensible defaults for storage services. Can be subclassed
    for service-specific customization (e.g., MinIO, PostgreSQL, MySQL).
    """
    
    def __init__(self, remote_base_path: str):
        """Initialize the storage builder.
        
        Args:
            remote_base_path: Base path on remote filesystem for persistent storage
        """
        self.remote_base_path = remote_base_path
    
    def build_environment_section(self, recipe_env: Dict[str, str]) -> str:
        """Build environment variable exports for storage containers."""
        env_vars = []
        
        # Export recipe-specific environment variables
        for key, value in (recipe_env or {}).items():
            # Don't quote values that contain shell variables
            if '${' in value or '$(' in value:
                env_vars.append(f'export {key}="{value}"')
            else:
                env_vars.append(f"export {key}='{value}'")
        
        # Add APPTAINERENV_ prefixed versions for Apptainer to pick up
        for key, value in (recipe_env or {}).items():
            if '${' in value or '$(' in value:
                env_vars.append(f'export APPTAINERENV_{key}="{value}"')
            else:
                env_vars.append(f"export APPTAINERENV_{key}='{value}'")
        
        return "\n".join(env_vars) if env_vars else "# No environment variables"
    
    def build_container_build_block(self, paths: ScriptPaths) -> str:
        """Build the container image build/check block."""
        return f"""
# Build container if needed
if [ ! -f {paths.sif_path} ]; then
    echo 'Building Apptainer image: {paths.sif_path}'
    
    # Set up user-writable directories to avoid permission issues
    export APPTAINER_TMPDIR=/tmp/apptainer-$USER-$$
    export APPTAINER_CACHEDIR=/tmp/apptainer-cache-$USER
    export HOME=/tmp/fake-home-$USER
    
    mkdir -p $APPTAINER_TMPDIR $APPTAINER_CACHEDIR $HOME/.apptainer
    
    # Create empty docker config to bypass authentication
    echo '{{}}' > $HOME/.apptainer/docker-config.json
    
    # Build container
    apptainer build --disable-cache --no-https {paths.sif_path} {paths.def_path}
    build_result=$?
    
    # Clean up
    rm -rf $APPTAINER_TMPDIR $APPTAINER_CACHEDIR $HOME
    
    if [ $build_result -ne 0 ]; then
        echo "ERROR: Failed to build container (exit code: $build_result)"
        exit 1
    fi
    
    echo "Container build successful!"
fi
"""
    
    def build_run_block(self, paths: ScriptPaths, resources: Dict[str, Any],
                       recipe: Dict[str, Any]) -> str:
        """Build single-node container run block for storage services (generic).
        
        This provides a generic implementation. Override this method in subclasses
        for service-specific behavior (e.g., MinIO's data/config paths, PostgreSQL's
        PGDATA directory, etc.).
        """
        project_ws = paths.remote_base_path
        
        # Generic storage data directory
        data_dir = f"{project_ws}/storage_data"
        
        return f"""
echo "Starting storage service container..."
echo "Binding project workspace: {project_ws} -> /workspace"
echo "Binding data directory: {data_dir} -> /data"

# Create data directory if it doesn't exist
mkdir -p {data_dir}

# Debug: Print environment variables
echo "Environment variables for container:"
env | grep -E '^MINIO_|^POSTGRES_|^MYSQL_|^MONGODB_' || echo "No storage vars found"

apptainer run --bind {paths.log_dir}:/app/logs,{project_ws}:/workspace,{data_dir}:/data {paths.sif_path} 2>&1
container_exit_code=$?

echo "Container exited with code: $container_exit_code"
if [ $container_exit_code -ne 0 ]; then
    echo "ERROR: Container failed to run properly"
fi
"""
    
    def supports_distributed(self) -> bool:
        """Storage services typically don't support distributed execution in this context."""
        return False
