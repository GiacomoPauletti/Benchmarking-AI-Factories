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
        """Build single-node vLLM run block using Ray backend (default)."""
        project_ws = paths.remote_base_path
        
        return f"""
echo "=== Starting single-node vLLM (Ray backend) ==="
export VLLM_MODEL={model}
export VLLM_MAX_MODEL_LEN={max_len}
export VLLM_GPU_MEMORY_UTILIZATION={gpu_mem}
export VLLM_TENSOR_PARALLEL={tensor_parallel}

# Setup HuggingFace cache on shared filesystem
export HF_CACHE_HOST="{hf_cache}"
mkdir -p $HF_CACHE_HOST
chmod 755 $HF_CACHE_HOST

echo "Launching vLLM server:"
echo "- Node: $(hostname)"
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
            --port 8001 \\
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
        project_ws = paths.remote_base_path
        
        # Total GPUs across all nodes
        total_gpus = f"$(( SLURM_NNODES * {nproc_per_node} ))"
        
        # Ray ports - use different ports to avoid conflicts with vLLM's master_port
        ray_gcs_port = master_port + 1  # GCS server port
        ray_dashboard_port = master_port + 2  # Dashboard port

        return f"""
echo "=== Starting multi-node vLLM with Ray cluster ==="
MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n1)
export MASTER_ADDR

# Get the IP address of the master node
MASTER_IP=$(srun --nodes=1 --ntasks=1 --nodelist=$MASTER_ADDR hostname -I | awk '{{print $1}}')
export MASTER_IP

export VLLM_MODEL={model}
export VLLM_MAX_MODEL_LEN={max_len}
export VLLM_GPU_MEMORY_UTILIZATION={gpu_mem}
export VLLM_TENSOR_PARALLEL_SIZE={total_gpus}

# Setup HuggingFace cache on shared filesystem
export HF_CACHE_HOST="{hf_cache}"
mkdir -p $HF_CACHE_HOST
chmod 755 $HF_CACHE_HOST

# Setup Ray temp directory with CRITICAL requirements:
# 1. Must be on SHARED FILESYSTEM (accessible from all nodes)
# 2. Must have SHORT PATH inside containers (Unix socket limit: 107 bytes)
# 3. Must be SAME PATH across ALL nodes (workers must see head's temp dir)
# 4. Use TCP for inter-node communication, Unix sockets for local IPC
# Solution: Single shared temp dir for entire job, bind-mounted to all containers
RAY_TMPDIR_HOST="{project_ws}/ray_tmp_$SLURM_JOB_ID"
RAY_TMPDIR="/ray_tmp"
mkdir -p $RAY_TMPDIR_HOST
chmod 777 $RAY_TMPDIR_HOST
export RAY_TMPDIR

echo "Multi-node vLLM configuration:"
echo "- Master node: $MASTER_ADDR ($MASTER_IP)"
echo "- Nodes: $SLURM_NNODES"
echo "- GPUs per node: {nproc_per_node}"
echo "- Total GPUs (tensor parallel): $VLLM_TENSOR_PARALLEL_SIZE"
echo "- Model: $VLLM_MODEL"
echo "- Ray GCS port: {ray_gcs_port}"
echo "- Ray temp dir: $RAY_TMPDIR"

# Step 1: Start Ray head node on master - run directly in main script, not via srun
echo "Starting Ray head node on $MASTER_ADDR ($MASTER_IP)..."
echo "Note: Starting Ray head directly on this node..."
echo "Ray temp dir (host): $RAY_TMPDIR_HOST -> (container): $RAY_TMPDIR"
apptainer exec {nv_flag} \\
    --bind {paths.log_dir}:/app/logs \\
    --bind {project_ws}:/workspace \\
    --bind $RAY_TMPDIR_HOST:$RAY_TMPDIR \\
    --writable-tmpfs \\
    {paths.sif_path} bash -c "
        echo 'Ray head starting on node:' \$(hostname)
        echo 'Ray head IP:' \$(hostname -I)
        echo 'Ray temp dir: $RAY_TMPDIR'
        
        # Force Ray to use TCP instead of Unix domain sockets
        export RAY_RAYLET_SOCKET_IFNAME=eth0
        export RAY_USE_TLS=0
        export RAY_TMPDIR=$RAY_TMPDIR
        
        ray start --head --node-ip-address=$MASTER_IP --port={ray_gcs_port} \\
            --dashboard-port={ray_dashboard_port} --num-gpus={nproc_per_node} \\
            --temp-dir=\$RAY_TMPDIR --include-dashboard=false \\
            --disable-usage-stats --block 2>&1
    " &

RAY_HEAD_PID=$!
echo "Waiting for Ray head to initialize..."
sleep 20

# Skip verification - Ray GCS inside container not accessible from outside due to network isolation
echo "Ray head should be running (verification skipped due to container networking)"

# Step 2: Start Ray workers on all other nodes
if [ \"$SLURM_NNODES\" -gt 1 ]; then
    echo "Starting Ray workers on remaining nodes..."
    WORKER_NODES=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | tail -n+2 | paste -sd,)
    if [ -n \"$WORKER_NODES\" ]; then
        echo "Worker nodes: $WORKER_NODES"
        srun --nodes=$((SLURM_NNODES-1)) --ntasks=$((SLURM_NNODES-1)) --nodelist=$WORKER_NODES \\
            apptainer exec {nv_flag} \\
                --bind {paths.log_dir}:/app/logs \\
                --bind {project_ws}:/workspace \\
                --bind $RAY_TMPDIR_HOST:$RAY_TMPDIR \\
                --writable-tmpfs \\
                {paths.sif_path} bash -c "
                    echo 'Ray worker starting on node:' \$(hostname)
                    echo 'Ray worker IP:' \$(hostname -I)
                    echo 'Connecting to Ray head at: $MASTER_IP:{ray_gcs_port}'
                    echo 'Ray temp dir: $RAY_TMPDIR'
                    
                    # Force Ray to use TCP instead of Unix domain sockets
                    export RAY_RAYLET_SOCKET_IFNAME=eth0
                    export RAY_USE_TLS=0
                    export RAY_TMPDIR=$RAY_TMPDIR
                    
                    ray start --address=$MASTER_IP:{ray_gcs_port} --num-gpus={nproc_per_node} \\
                        --temp-dir=\$RAY_TMPDIR --disable-usage-stats --block 2>&1
                " &
        
        echo "Waiting for workers to connect to Ray cluster..."
        sleep 20
        
        # Skip verification - can't verify across container boundaries
        echo "Ray workers should be connecting (verification skipped due to container networking)"
    fi
fi

# Step 3: Launch vLLM on master node - it will use the Ray cluster
echo "Starting vLLM API server on master node..."
srun --nodes=1 --ntasks=1 --nodelist=$MASTER_ADDR \\
    apptainer exec {nv_flag} \\
        --bind {paths.log_dir}:/app/logs \\
        --bind {project_ws}:/workspace \\
        --bind $RAY_TMPDIR_HOST:$RAY_TMPDIR \\
        --bind $HF_CACHE_HOST:/hf_cache \\
        --writable-tmpfs \\
        --env HF_HOME=/hf_cache \\
        --env TRANSFORMERS_CACHE=/hf_cache \\
        --env HF_DATASETS_CACHE=/hf_cache/datasets \\
        {paths.sif_path} bash -c "
            echo 'vLLM container started successfully'
            export HF_HOME=/hf_cache
            export TRANSFORMERS_CACHE=/hf_cache
            export HF_DATASETS_CACHE=/hf_cache/datasets
            
            # Force vLLM to use existing Ray cluster with TCP sockets
            export VLLM_USE_RAY=1
            export RAY_ADDRESS=$MASTER_IP:{ray_gcs_port}
            export RAY_RAYLET_SOCKET_IFNAME=eth0
            export RAY_USE_TLS=0
            export RAY_TMPDIR=$RAY_TMPDIR
            
            echo 'vLLM connecting to Ray at: '\$RAY_ADDRESS
            echo 'Ray temp dir: '\$RAY_TMPDIR
            echo 'Starting vLLM with tensor_parallel_size='\$VLLM_TENSOR_PARALLEL_SIZE
            
            python3 -m vllm.entrypoints.openai.api_server \\
                --model $VLLM_MODEL \\
                --host 0.0.0.0 \\
                --port 8001 \\
                --tensor-parallel-size $VLLM_TENSOR_PARALLEL_SIZE \\
                --max-model-len $VLLM_MAX_MODEL_LEN \\
                --gpu-memory-utilization $VLLM_GPU_MEMORY_UTILIZATION \\
                --distributed-executor-backend ray 2>&1
        " 2>&1

container_exit_code=$?

# Cleanup: Stop Ray cluster on all nodes
echo "Stopping Ray cluster on all nodes..."
srun --nodes=$SLURM_NNODES --ntasks=$SLURM_NNODES \\
    apptainer exec {nv_flag} \\
        --bind {project_ws}:/workspace \\
        --bind $RAY_TMPDIR:$RAY_TMPDIR \\
        {paths.sif_path} bash -c "ray stop --force" 2>/dev/null || true

echo "vLLM multi-node job exited with: $container_exit_code"
[ $container_exit_code -ne 0 ] && echo "ERROR: vLLM container run failed"
"""
