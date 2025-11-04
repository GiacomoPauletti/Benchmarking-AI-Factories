"""vLLM-specific inference builder.

Extends InferenceRecipeBuilder with vLLM-specific distributed execution
using tensor parallelism.
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
        
        nproc_per_node = int(distributed_cfg.get("nproc_per_node", 1))
        master_port = distributed_cfg.get("master_port", 29500)
        model = distributed_cfg.get("model", "Qwen/Qwen2.5-0.5B-Instruct")
        max_len = distributed_cfg.get("max_model_len", 4096)
        gpu_mem = distributed_cfg.get("gpu_memory_utilization", 0.9)

        return f"""
echo "=== Starting distributed vLLM (HPC-native mode) ==="
MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n1)
export MASTER_ADDR
export MASTER_PORT={master_port}
export NPROC_PER_NODE={nproc_per_node}
export VLLM_MODEL={model}
export VLLM_MAX_MODEL_LEN={max_len}
export VLLM_GPU_MEMORY_UTILIZATION={gpu_mem}
export VLLM_TENSOR_PARALLEL_SIZE=$(( SLURM_NNODES * NPROC_PER_NODE ))

# Setup HuggingFace cache on shared filesystem
export HF_CACHE_HOST="{hf_cache}"
mkdir -p $HF_CACHE_HOST
chmod 755 $HF_CACHE_HOST

echo "Launching vLLM distributed server:"
echo "- Master node: $MASTER_ADDR:$MASTER_PORT"
echo "- Nodes: $SLURM_NNODES"
echo "- GPUs per node: $NPROC_PER_NODE"
echo "- Total GPUs: $VLLM_TENSOR_PARALLEL_SIZE"
echo "- Model: $VLLM_MODEL"
echo "- HF Cache: $HF_CACHE_HOST"

srun --nodes=$SLURM_NNODES --ntasks=$((SLURM_NNODES * NPROC_PER_NODE)) \\
    --ntasks-per-node=$NPROC_PER_NODE \\
    --gpus-per-task=1 \\
    apptainer exec {nv_flag} \\
        --bind {paths.log_dir}:/app/logs \\
        --bind {project_ws}:/workspace \\
        --bind $HF_CACHE_HOST:/hf_cache \\
        --env HF_HOME=/hf_cache \\
        --env TRANSFORMERS_CACHE=/hf_cache \\
        --env HF_DATASETS_CACHE=/hf_cache/datasets \\
        {paths.sif_path} bash -lc "
            export MASTER_ADDR=$MASTER_ADDR
            export MASTER_PORT=$MASTER_PORT
            export HF_HOME=/hf_cache
            export TRANSFORMERS_CACHE=/hf_cache
            export HF_DATASETS_CACHE=/hf_cache/datasets
            
            # Map SLURM environment variables to what vLLM external_launcher expects
            export RANK=\\$SLURM_PROCID
            export LOCAL_RANK=\\$SLURM_LOCALID
            export WORLD_SIZE=$VLLM_TENSOR_PARALLEL_SIZE
            
            python3 -m vllm.entrypoints.openai.api_server \\
                --model $VLLM_MODEL \\
                --host 0.0.0.0 \\
                --port 8001 \\
                --tensor-parallel-size $VLLM_TENSOR_PARALLEL_SIZE \\
                --distributed-executor-backend external_launcher \\
                --max-model-len $VLLM_MAX_MODEL_LEN \\
                --gpu-memory-utilization $VLLM_GPU_MEMORY_UTILIZATION
        "

container_exit_code=$?
echo "vLLM distributed job exited with: $container_exit_code"
[ $container_exit_code -ne 0 ] && echo "ERROR: vLLM container run failed"
"""
