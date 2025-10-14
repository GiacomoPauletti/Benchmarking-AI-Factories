# vLLM Custom Model Configuration

This guide explains how to use custom models with the vLLM inference service.

## Overview

The vLLM recipe supports dynamic model configuration through environment variables. You can specify any HuggingFace model when creating a service.

## Default Model

If no model is specified, the service uses: **`Qwen/Qwen2.5-0.5B-Instruct`**

## Specifying a Custom Model

### Method 1: Using the API

```bash
curl -X POST http://your-server:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm",
    "config": {
      "nodes": 1,
      "environment": {
        "VLLM_MODEL": "gpt2"
      }
    }
  }'
```

### Method 2: Using the Interactive Shell

```bash
./services/server/server-shell.sh
# In the shell, use the create command with JSON payload
# Currently, the shell's create command uses default config
# Use the API method above for custom models
```

## Popular Model Examples

### Small Models (Good for Testing)
```json
{
  "recipe_name": "inference/vllm",
  "config": {
    "environment": {
      "VLLM_MODEL": "gpt2"
    }
  }
}
```

### Instruction-Tuned Models
```json
{
  "recipe_name": "inference/vllm",
  "config": {
    "environment": {
      "VLLM_MODEL": "Qwen/Qwen2.5-0.5B-Instruct"
    }
  }
}
```

### Larger Models (Requires More Resources)
```json
{
  "recipe_name": "inference/vllm",
  "config": {
    "nodes": 1,
    "environment": {
      "VLLM_MODEL": "meta-llama/Llama-2-7b-chat-hf"
    }
  }
}
```

## Advanced Configuration

You can configure both model parameters and resource requirements:

### Custom Model + Custom Resources
```json
{
  "recipe_name": "inference/vllm",
  "config": {
    "nodes": 1,
    "environment": {
      "VLLM_MODEL": "meta-llama/Llama-2-7b-chat-hf",
      "VLLM_MAX_MODEL_LEN": "4096",
      "VLLM_TENSOR_PARALLEL_SIZE": "1",
      "VLLM_GPU_MEMORY_UTILIZATION": "0.9"
    },
    "resources": {
      "cpu": "8",
      "memory": "64G",
      "time_limit": 60,
      "gpu": "1"
    }
  }
}
```

### Environment Variables

- `VLLM_MODEL`: HuggingFace model identifier (required)
- `VLLM_HOST`: Bind address (default: `0.0.0.0`)
- `VLLM_PORT`: Service port (default: `8001`)
- `VLLM_MAX_MODEL_LEN`: Maximum sequence length (optional)
- `VLLM_TENSOR_PARALLEL_SIZE`: Number of GPUs for tensor parallelism (optional)
- `VLLM_GPU_MEMORY_UTILIZATION`: GPU memory utilization fraction 0.0-1.0 (optional)

### Resource Overrides

You can override any resource requirement from the recipe:

- `cpu`: Number of CPU cores (default: `"2"`)
- `memory`: Memory allocation per CPU (default: `"32G"`)
- `time_limit`: Time limit in minutes (default: `15`)
- `gpu`: GPU allocation (default: `"1"`, set to `null` or `""` for CPU-only)

**Example: CPU-only inference with custom memory**
```json
{
  "recipe_name": "inference/vllm",
  "config": {
    "environment": {
      "VLLM_MODEL": "gpt2"
    },
    "resources": {
      "cpu": "4",
      "memory": "16G",
      "gpu": null
    }
  }
}
```

**Example: More time for large model download**
```json
{
  "recipe_name": "inference/vllm",
  "config": {
    "environment": {
      "VLLM_MODEL": "mistralai/Mistral-7B-Instruct-v0.2"
    },
    "resources": {
      "time_limit": 120
    }
  }
}
```

## Model Download & Caching

### First Run
When you specify a new model, vLLM will:
1. Download the model from HuggingFace
2. Cache it in `/workspace/huggingface_cache` (bound from your project directory)
3. Load the model into GPU memory

This can take several minutes for large models.

### Subsequent Runs
Cached models load much faster (seconds to minutes depending on size).

## Checking Available Models

After starting a vLLM service, query which models it's serving:

```bash
# Using the shell
vllm models <service_id>

# Using the API
curl http://your-server:8001/api/v1/vllm/<service_id>/models
```

## Sending Prompts

The model parameter in prompt requests is **optional**. If you don't specify it, vLLM uses the model configured at startup:

```bash
# Using the shell (model auto-detected)
prompt <service_id> 'Your prompt here'

# Using the API (model auto-detected)
curl -X POST http://your-server:8001/api/v1/vllm/<service_id>/prompt \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Your prompt here",
    "max_tokens": 150,
    "temperature": 0.7
  }'
```

## Troubleshooting

### Error: "The model `X` does not exist"
This error occurs when:
1. You send a prompt with `--model` parameter that doesn't match the loaded model
2. The vLLM service was started without specifying a model

**Solution**: Don't use the `--model` parameter in your prompt, or ensure it matches the model configured when creating the service.

### Model Download Fails
- Check your internet connection
- Verify the model exists on HuggingFace
- Some models require authentication - set `HUGGING_FACE_HUB_TOKEN` in environment

### Out of Memory Errors
- Use a smaller model
- Reduce `VLLM_MAX_MODEL_LEN`
- Adjust `VLLM_GPU_MEMORY_UTILIZATION` to a lower value (e.g., `0.8`)
- Request more GPU resources in the config

## Model Recommendations by Use Case

### Quick Testing & Development
- `gpt2` (124M parameters) - Very fast, basic quality
- `facebook/opt-125m` - Small but reasonable quality

### Production Quality (Single GPU)
- `Qwen/Qwen2.5-0.5B-Instruct` (default) - Fast, instruction-following
- `microsoft/phi-2` (2.7B) - Good quality, fits on 1 GPU
- `mistralai/Mistral-7B-Instruct-v0.2` (7B) - High quality

### High Performance (Multi-GPU)
- `meta-llama/Llama-2-13b-chat-hf` (13B) - Excellent quality
- `mistralai/Mixtral-8x7B-Instruct-v0.1` (47B MoE) - State-of-the-art

## Example Workflow

1. **Create a service with custom model:**
```bash
curl -X POST http://mel0110:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm",
    "config": {
      "nodes": 1,
      "environment": {"VLLM_MODEL": "gpt2"}
    }
  }'
```

2. **Wait for service to be ready:**
```bash
# Check status (should show: building → starting → running)
curl http://mel0110:8001/api/v1/services/<service_id>/status
```

3. **Verify loaded models:**
```bash
curl http://mel0110:8001/api/v1/vllm/<service_id>/models
# Should return: {"models": ["gpt2"]}
```

4. **Send prompts:**
```bash
curl -X POST http://mel0110:8001/api/v1/vllm/<service_id>/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is artificial intelligence?"}'
```

## Notes

- Model selection happens at **service creation time**, not at prompt time
- Each vLLM service runs one model at a time
- To use multiple models simultaneously, create multiple vLLM services
- The `--model` parameter in prompts is legacy and should not be used
