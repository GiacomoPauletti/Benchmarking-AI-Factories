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
        """Inference recipes support distributed execution."""
        return True
    
    def build_distributed_run_block(self, paths: ScriptPaths, resources: Dict[str, Any],
                                   recipe: Dict[str, Any],
                                   distributed_cfg: Dict[str, Any]) -> str:
        """Build distributed multi-node run block for inference (generic).
        
        This provides a generic implementation. Override this method in subclasses
        for service-specific distributed execution (e.g., vLLM's tensor parallelism,
        TGI's sharding, etc.).
        """
        project_ws = paths.remote_base_path
        hf_cache = f"{project_ws}/huggingface_cache"
        nv_flag = "--nv" if resources.get("gpu") else ""
        
        # Generic distributed configuration
        nproc_per_node = int(distributed_cfg.get("nproc_per_node", 1))
        master_port = distributed_cfg.get("master_port", 29500)
        
        return f"""
echo "Starting distributed inference container..."
MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n1)
export MASTER_ADDR
export MASTER_PORT={master_port}
export NPROC_PER_NODE={nproc_per_node}

# Use persistent shared HuggingFace cache (survives across jobs, shared by all nodes)
# HF_HOME on host (for mkdir), APPTAINERENV_HF_HOME is container-side path
export HF_HOME="{hf_cache}"
mkdir -p $HF_HOME
export APPTAINERENV_HF_HOME="/root/.cache/huggingface"

echo "Launching distributed inference:"
echo "- Nodes: $SLURM_NNODES"
echo "- Processes per node: $NPROC_PER_NODE"
echo "- Master node: $MASTER_ADDR:$MASTER_PORT"
echo "- HF_HOME: $HF_HOME"

TOTAL_PROCS=$(( SLURM_NNODES * NPROC_PER_NODE ))

# Generic distributed launch using srun
# The container's runscript should handle distributed coordination
srun --nodes=$SLURM_NNODES --ntasks=$TOTAL_PROCS --ntasks-per-node=$NPROC_PER_NODE \
    apptainer run {nv_flag} --bind {paths.log_dir}:/app/logs,{project_ws}:/workspace,{hf_cache}:/root/.cache/huggingface {paths.sif_path} &

INFERENCE_PID=$!

echo "Inference server started with PID: $INFERENCE_PID"
echo "Server will run until job is cancelled or time limit is reached"

# Wait for the background process
wait $INFERENCE_PID
container_exit_code=$?

echo "Distributed inference job exited with code: $container_exit_code"
[ $container_exit_code -ne 0 ] && echo "ERROR: Distributed container run failed"
"""
