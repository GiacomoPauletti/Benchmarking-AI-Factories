"""vLLM-specific inference builder.

Extends InferenceRecipeBuilder with vLLM-specific distributed execution
using tensor parallelism and Ray.
"""

from typing import Dict, Any
from .inference_builder import InferenceRecipeBuilder
from .base import ScriptPaths


class VllmInferenceBuilder(InferenceRecipeBuilder):
    """vLLM-specific script builder with tensor parallelism support."""
    
    def build_distributed_run_block(self, paths: ScriptPaths, resources: Dict[str, Any],
                                   recipe: Dict[str, Any],
                                   distributed_cfg: Dict[str, Any]) -> str:
        """Build distributed multi-node run block for vLLM with tensor parallelism."""
        project_ws = paths.remote_base_path
        hf_cache = f"{project_ws}/huggingface_cache"
        nv_flag = "--nv" if resources.get("gpu") else ""
        
        # vLLM-specific distributed configuration
        nproc_per_node = int(distributed_cfg.get("nproc_per_node", 1))
        master_port = distributed_cfg.get("master_port", 29500)
        model = distributed_cfg.get("model", "Qwen/Qwen2.5-0.5B-Instruct")
        max_len = distributed_cfg.get("max_model_len", 4096)
        gpu_mem = distributed_cfg.get("gpu_memory_utilization", 0.9)
        
        return f"""
echo "Starting distributed vLLM container with tensor parallelism..."
MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n1)
export MASTER_ADDR
export MASTER_PORT={master_port}
export NPROC_PER_NODE={nproc_per_node}
export VLLM_MODEL={model}
export VLLM_MAX_MODEL_LEN={max_len}
export VLLM_GPU_MEMORY_UTILIZATION={gpu_mem}
export VLLM_TENSOR_PARALLEL_SIZE=$(( SLURM_NNODES * NPROC_PER_NODE ))

# Use persistent shared HuggingFace cache (survives across jobs, shared by all nodes)
# HF_HOME on host (for mkdir), APPTAINERENV_HF_HOME is container-side path
export HF_HOME="{hf_cache}"
mkdir -p $HF_HOME
export APPTAINERENV_HF_HOME="/root/.cache/huggingface"

echo "Launching distributed vLLM with tensor parallelism:"
echo "- Nodes: $SLURM_NNODES"
echo "- GPUs per node: $NPROC_PER_NODE"
echo "- Total tensor parallel size: $VLLM_TENSOR_PARALLEL_SIZE"
echo "- Master node: $MASTER_ADDR:$MASTER_PORT"
echo "- Model: $VLLM_MODEL"
echo "- HF_HOME: $HF_HOME"

TOTAL_GPUS=$(( SLURM_NNODES * NPROC_PER_NODE ))

# Launch vLLM server with explicit tensor parallelism configuration
srun --nodes=$SLURM_NNODES --ntasks=$TOTAL_GPUS --ntasks-per-node=$NPROC_PER_NODE \
    apptainer exec {nv_flag} --bind {paths.log_dir}:/app/logs,{project_ws}:/workspace,{hf_cache}:/root/.cache/huggingface {paths.sif_path} bash -lc "\
        python3 -m vllm.entrypoints.openai.api_server \
            --model $VLLM_MODEL \
            --host 0.0.0.0 \
            --port 8001 \
            --tensor-parallel-size $TOTAL_GPUS \
            --gpu-memory-utilization $VLLM_GPU_MEMORY_UTILIZATION \
            --max-model-len $VLLM_MAX_MODEL_LEN \
            --distributed-executor-backend ray
    " &

VLLM_PID=$!

echo "vLLM server started with PID: $VLLM_PID"
echo "Server will run until job is cancelled or time limit is reached"

# Wait for the background process
wait $VLLM_PID
container_exit_code=$?

echo "Distributed vLLM job exited with code: $container_exit_code"
[ $container_exit_code -ne 0 ] && echo "ERROR: Distributed vLLM container run failed"
"""
