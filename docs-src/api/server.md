# Server API Documentation

## Interactive API Reference

The Server Service provides a REST API for managing SLURM jobs and AI workload orchestration.

<swagger-ui src="server-openapi.json"/>


## API Examples

### Create vLLM Service with Default Model

Create a vLLM service with default configuration (Qwen/Qwen2.5-0.5B-Instruct):

```bash
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm"
  }'
```

### Create vLLM Service with Custom Model

Specify a different model from HuggingFace:

```bash
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm",
    "config": {
      "environment": {
        "VLLM_MODEL": "gpt2"
      }
    }
  }'
```

### Create vLLM Service with Custom Model and Resources

Override both model and resource allocation:

```bash
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm",
    "config": {
      "environment": {
        "VLLM_MODEL": "gpt2"
      },
      "resources": {
        "nodes": 1,
        "cpu": "8",
        "memory": "64G",
        "time_limit": 120,
        "gpu": "1"
      }
    }
  }'
```

### Create vLLM Service with All Options

Full configuration with all available environment variables and resource settings:

```bash
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm",
    "config": {
      "environment": {
        "VLLM_MODEL": "gpt2",
        "VLLM_HOST": "0.0.0.0",
        "VLLM_PORT": "8001",
        "VLLM_MAX_MODEL_LEN": "2048",
        "VLLM_TENSOR_PARALLEL_SIZE": "1",
        "VLLM_GPU_MEMORY_UTILIZATION": "0.9",
        "CUDA_VISIBLE_DEVICES": "0"
      },
      "resources": {
        "nodes": 1,
        "cpu": "2",
        "memory": "32G",
        "time_limit": 15,
        "gpu": "1"
      }
    }
  }'
```

### Create CPU-Only vLLM Service

For testing or when GPU is not available:

```bash
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm",
    "config": {
      "environment": {
        "VLLM_MODEL": "gpt2"
      },
      "resources": {
        "nodes": 1,
        "cpu": "4",
        "memory": "16G",
        "gpu": null
      }
    }
  }'
```

### List All Services

```bash
curl http://localhost:8001/api/v1/services
```

### Get Service Details

```bash
curl http://localhost:8001/api/v1/services/3652098
```

### Check Service Status

```bash
curl http://localhost:8001/api/v1/services/3652098/status
```

### Get Service Logs

```bash
curl http://localhost:8001/api/v1/services/3652098/logs
```

### Stop a Service

```bash
curl -X DELETE http://localhost:8001/api/v1/services/3652098
```

### List vLLM Services

Get all running vLLM services with their endpoints:

```bash
curl http://localhost:8001/api/v1/vllm/services
```

### Get Available Models

Check which models are loaded in a vLLM service:

```bash
curl http://localhost:8001/api/v1/vllm/3652098/models
```

### Send Prompt to vLLM Service

Send a text prompt and get a response:

```bash
curl -X POST http://localhost:8001/api/v1/vllm/3652098/prompt \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Tell me a joke about programming",
    "max_tokens": 100
  }'
```

### Send Prompt with Advanced Options

```bash
curl -X POST http://localhost:8001/api/v1/vllm/3652098/prompt \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write a short haiku about AI",
    "model": "gpt2",
    "max_tokens": 64,
    "temperature": 0.7
  }'
```

### List Available Recipes

```bash
curl http://localhost:8001/api/v1/recipes
```

### Get Recipe Details

```bash
curl http://localhost:8001/api/v1/recipes/inference/vllm
```

## Notes

- **Default Model**: If not specified, services use `Qwen/Qwen2.5-0.5B-Instruct`
- **Model Sources**: Models must be available on HuggingFace or cached locally
- **Resource Defaults**: Each recipe has default resource allocations that can be overridden
- **Status Values**: Services progress through states: `pending` → `building` → `starting` → `running`
- **Service ID**: The SLURM job ID is used as the service identifier
