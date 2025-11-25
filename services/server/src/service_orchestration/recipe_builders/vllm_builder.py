"""vLLM-specific inference builder.

Extends InferenceRecipeBuilder with vLLM-specific distributed execution
using tensor parallelism.
"""

from typing import Dict, Any
from .inference_builder import InferenceRecipeBuilder
from .base import ScriptPaths


class VllmInferenceBuilder(InferenceRecipeBuilder):
    """vLLM-specific script builder with replica group support."""
    
    def build_replica_group_run_block(self, paths: ScriptPaths, resources: Dict[str, Any],
                                      recipe: Dict[str, Any],
                                      config: Dict[str, Any]) -> str:
        """Build replica group run block for vLLM.
        
        Supports multiple replicas per node with flexible GPU allocation:
        - Each replica runs as a separate process
        - Each replica bound to specific GPU(s) via CUDA_VISIBLE_DEVICES
        - Each replica listens on unique port (base_port + index)
        
        Args:
            paths: Container and filesystem paths
            resources: Resource requirements (gpu, cpu, memory)
            recipe: Recipe configuration
            config: Combined recipe + user config with gpu_per_replica, base_port, etc.
        """
        project_ws = paths.remote_base_path.rstrip("/")
        hf_cache = f"{project_ws}/{self.remote_hf_cache_dirname}"
        nv_flag = "--nv" if resources.get("gpu") else ""
        
        # Read configuration
        model = config.get("model", recipe.get("environment", {}).get("VLLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct"))
        max_len = config.get("max_model_len", 4096)
        gpu_mem = config.get("gpu_memory_utilization", 0.9)
        
        # Get replica group configuration
        total_gpus = int(resources.get("gpu", 4))
        gpu_per_replica = int(config.get("gpu_per_replica") or recipe.get("gpu_per_replica", 1))
        base_port = int(config.get("base_port") or recipe.get("base_port", 8001))
        
        # Calculate replicas per node
        replicas_per_node = total_gpus // gpu_per_replica
        
        # Build script using srun for proper resource isolation
        script = f"""
echo "=== Starting vLLM replica group ({replicas_per_node} replicas) ==="
export VLLM_MODEL={model}
export VLLM_MAX_MODEL_LEN={max_len}
export VLLM_GPU_MEMORY_UTILIZATION={gpu_mem}

# Setup HuggingFace cache on shared filesystem
export HF_CACHE_HOST="{hf_cache}"
mkdir -p $HF_CACHE_HOST
chmod 755 $HF_CACHE_HOST

echo "Node: $(hostname)"
echo "Starting {replicas_per_node} vLLM replicas using srun for resource isolation..."
echo "Base port: {base_port}"
echo "Model: $VLLM_MODEL"
echo "GPUs per replica: {gpu_per_replica}"
echo "HF Cache: $HF_CACHE_HOST"

# Array to track background PIDs
declare -a REPLICA_PIDS=()

"""
        
        # Generate launch command for each replica using srun
        for i in range(replicas_per_node):
            port = base_port + i
            
            if gpu_per_replica == 1:
                tensor_parallel = 1
            else:
                tensor_parallel = gpu_per_replica
            
            # Use srun --exact for proper resource isolation per replica
            # This ensures SLURM manages GPU binding automatically
            script += f"""
# Replica {i}: Port {port}, {gpu_per_replica} GPU(s)
echo "Launching replica {i} on port {port} (srun task {i})..."
srun --ntasks=1 --exact --gpus-per-task={gpu_per_replica} \\
    apptainer exec {nv_flag} \\
    --bind {paths.log_dir}:/app/logs \\
    --bind {project_ws}:/workspace \\
    --bind $HF_CACHE_HOST:/hf_cache \\
    --env HF_HOME=/hf_cache \\
    --env TRANSFORMERS_CACHE=/hf_cache \\
    --env HF_DATASETS_CACHE=/hf_cache/datasets \\
    {paths.sif_path} bash -lc "
        export HF_HOME=/hf_cache
        export TRANSFORMERS_CACHE=/hf_cache
        export HF_DATASETS_CACHE=/hf_cache/datasets
        
        python3 -m vllm.entrypoints.openai.api_server \\
            --model $VLLM_MODEL \\
            --host 0.0.0.0 \\
            --port {port} \\
            --tensor-parallel-size {tensor_parallel} \\
            --max-model-len $VLLM_MAX_MODEL_LEN \\
            --gpu-memory-utilization $VLLM_GPU_MEMORY_UTILIZATION
    " > {paths.log_dir}/vllm_${{SLURM_JOB_ID}}_replica_{i}.log 2>&1 &

REPLICA_PIDS+=($!)
echo "Replica {i} started with PID ${{REPLICA_PIDS[-1]}} (output: vllm_${{SLURM_JOB_ID}}_replica_{i}.log)"
sleep 2  # Brief delay between launches

"""
        
        # Add wait logic to keep job alive - THIS IS CRITICAL!
        script += f"""
# Wait for all replicas and handle termination
echo "All {replicas_per_node} replicas launched. PIDs: ${{REPLICA_PIDS[@]}}"
echo "Waiting for replicas to complete..."

# Function to cleanup on exit
cleanup() {{
    echo "Received termination signal, stopping all replicas..."
    for pid in "${{REPLICA_PIDS[@]}}"; do
        if kill -0 $pid 2>/dev/null; then
            echo "Stopping PID $pid..."
            kill $pid 2>/dev/null
        fi
    done
    exit 0
}}

trap cleanup SIGTERM SIGINT

# Wait for all background processes - THIS KEEPS THE JOB ALIVE
for pid in "${{REPLICA_PIDS[@]}}"; do
    wait $pid || echo "Process $pid exited with code $?"
done

echo "All replicas completed"
"""
        
        return script
