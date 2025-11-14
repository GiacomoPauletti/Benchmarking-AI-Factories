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
        """Build distributed multi-node run block for vLLM with tensor parallelism.
        
        For single-node setups, uses Ray backend (default).
        For multi-node setups, uses external_launcher with srun.
        """
        nodes = int(resources.get("nodes", 1))
        project_ws = paths.remote_base_path
        hf_cache = f"{project_ws}/huggingface_cache"
        nv_flag = "--nv" if resources.get("gpu") else ""
        
        nproc_per_node = int(distributed_cfg.get("nproc_per_node", 1))
        master_port = distributed_cfg.get("master_port", 29500)
        # Get model from distributed config, or fallback to recipe environment, or use default
        model = distributed_cfg.get("model", recipe.get("environment", {}).get("VLLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct"))
        max_len = distributed_cfg.get("max_model_len", 4096)
        gpu_mem = distributed_cfg.get("gpu_memory_utilization", 0.9)
        
        # For single-node, use simpler Ray-based approach
        if nodes == 1:
            return self._build_single_node_run_block(paths, resources, recipe, distributed_cfg, 
                                                     model, max_len, gpu_mem, nproc_per_node, hf_cache, nv_flag)

        # For multi-node, use external_launcher approach
        return self._build_multi_node_run_block(paths, resources, recipe, distributed_cfg,
                                                model, max_len, gpu_mem, nproc_per_node, master_port, hf_cache, nv_flag)
    
    def _build_single_node_run_block(self, paths: ScriptPaths, resources: Dict[str, Any],
                                      recipe: Dict[str, Any], distributed_cfg: Dict[str, Any],
                                      model: str, max_len: int, gpu_mem: float,
                                      tensor_parallel: int, hf_cache: str, nv_flag: str) -> str:
        """Build single-node vLLM run block using Ray backend (default).
        
        Supports replica_port in distributed_cfg for data-parallel deployments.
        """
        project_ws = paths.remote_base_path
        
        # Support custom port for replicas (default to 8001)
        vllm_port = distributed_cfg.get("replica_port", 8001)
        
        return f"""
echo "=== Starting single-node vLLM (Ray backend) ==="
export VLLM_MODEL={model}
export VLLM_MAX_MODEL_LEN={max_len}
export VLLM_GPU_MEMORY_UTILIZATION={gpu_mem}
export VLLM_TENSOR_PARALLEL={tensor_parallel}
export VLLM_PORT={vllm_port}

# Setup HuggingFace cache on shared filesystem
export HF_CACHE_HOST="{hf_cache}"
mkdir -p $HF_CACHE_HOST
chmod 755 $HF_CACHE_HOST

echo "Launching vLLM server:"
echo "- Node: $(hostname)"
echo "- Port: $VLLM_PORT"
echo "- GPUs (tensor parallel): $VLLM_TENSOR_PARALLEL"
echo "- Model: $VLLM_MODEL"
echo "- Max model len: $VLLM_MAX_MODEL_LEN"
echo "- HF Cache: $HF_CACHE_HOST"

# Launch single vLLM process with Ray backend (handles multi-GPU internally)
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
            --port $VLLM_PORT \\
            --tensor-parallel-size $VLLM_TENSOR_PARALLEL \\
            --max-model-len $VLLM_MAX_MODEL_LEN \\
            --gpu-memory-utilization $VLLM_GPU_MEMORY_UTILIZATION \\
            2>&1 | tee /app/logs/vllm_server.log
    "

container_exit_code=$?
echo "vLLM server exited with: $container_exit_code"
[ $container_exit_code -ne 0 ] && echo "ERROR: vLLM container run failed"
"""
    
    def _build_multi_node_run_block(self, paths: ScriptPaths, resources: Dict[str, Any],
                                     recipe: Dict[str, Any], distributed_cfg: Dict[str, Any],
                                     model: str, max_len: int, gpu_mem: float,
                                     nproc_per_node: int, master_port: int, hf_cache: str, nv_flag: str) -> str:
        """Build multi-node vLLM run block using Ray backend with proper multi-node setup."""
        raise NotImplementedError("Multi-node vLLM with tensor parallelism is not yet implemented.")
