"""Builder for inference recipes (vLLM, TGI, etc.).

Handles container orchestration for inference services including distributed
multi-node execution with tensor parallelism.

This is a generic base builder for inference services. Recipe-specific builders
can override methods to customize behavior (e.g., VllmInferenceBuilder).
"""

from typing import Dict, Any
from .base import RecipeScriptBuilder, ScriptPaths


class InferenceRecipeBuilder(RecipeScriptBuilder):
    """Generic script builder for inference recipes.
    
    Provides sensible defaults for inference services. Can be subclassed
    for service-specific customization (e.g., vLLM, TGI, vLLM-specific features).
    """
    
    def __init__(self, remote_base_path: str):
        """Initialize the inference builder.
        
        Args:
            remote_base_path: Base path on remote filesystem for persistent storage
        """
        self.remote_base_path = remote_base_path
    
    def build_environment_section(self, recipe_env: Dict[str, str]) -> str:
        """Build environment variable exports for inference containers."""
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
        """Build single-node container run block for inference."""
        project_ws = paths.remote_base_path
        hf_cache = f"{project_ws}/huggingface_cache"
        nv_flag = "--nv" if resources.get('gpu') else ""
        
        return f"""
echo "Starting container..."
echo "Running inference container (no network binding, unprivileged user)..."
echo "Binding project workspace: {project_ws} -> /workspace"
echo "Binding HF cache: {hf_cache} -> /root/.cache/huggingface"

# Set persistent HuggingFace cache location
# HF_HOME on host (for mkdir), APPTAINERENV_HF_HOME is container-side path
export HF_HOME="{hf_cache}"
mkdir -p $HF_HOME
export APPTAINERENV_HF_HOME="/root/.cache/huggingface"

# Determine apptainer flags (e.g. use --nv when GPUs are requested)
APPTAINER_FLAGS="{nv_flag}"
echo "Apptainer flags: $APPTAINER_FLAGS"

# Debug: Print environment variables that should be passed to container
echo "Environment variables for container:"
env | grep -E '^VLLM_|^HF_|^CUDA_' || echo "No VLLM/HF/CUDA vars found"

apptainer run $APPTAINER_FLAGS --bind {paths.log_dir}:/app/logs,{project_ws}:/workspace,{hf_cache}:/root/.cache/huggingface {paths.sif_path} 2>&1
container_exit_code=$?

echo "Container exited with code: $container_exit_code"
if [ $container_exit_code -ne 0 ]; then
    echo "ERROR: Container failed to run properly"
fi
"""
    
    def supports_distributed(self) -> bool:
        """Inference recipes support replica group execution."""
        return True
    
    # Subclasses should override build_replica_group_run_block for their specific needs
    # (e.g., VllmInferenceBuilder implements vLLM-specific replica group logic)
