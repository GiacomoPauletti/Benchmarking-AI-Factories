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

### Create Data-Parallel vLLM Service Group

Create multiple vLLM replicas for high-throughput workloads. Requests are automatically load-balanced across healthy replicas:

```bash
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm-data-parallel",
    "config": {
      "replicas": 3
    }
  }'
```

The `replicas` field in the recipe YAML (or config override) creates a service group where each replica runs on a separate node. Prompts are distributed using round-robin load balancing with automatic failover.

**Note**: Currently only single-node multi-GPU replicas are supported (e.g., 1 node × 4 GPUs per replica). Multi-node multi-GPU is not yet implemented.

### Create vLLM Service with Custom Model

Specify a different model from HuggingFace:

```bash
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm-single-node",
    "config": {
      "environment": {
        "VLLM_MODEL": "gpt2"
      }
    }
  }'
```

### Query Available Models

Before creating a service, you can search HuggingFace Hub for compatible models:

```bash
# Get supported architectures and examples
curl http://localhost:8001/api/v1/vllm/available-models

# Search for models (e.g., Qwen models)
curl "http://localhost:8001/api/v1/vllm/search-models?query=qwen&limit=10"

# Get detailed info about a specific model
curl http://localhost:8001/api/v1/vllm/model-info/Qwen/Qwen2.5-7B-Instruct
```

These endpoints return model compatibility information, download statistics, and architecture details to help you choose the right model for your use case.

### Create vLLM Service with Custom Model and Resources

Override both model and resource allocation (only single node supported for now):

```bash
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm-single-node",
    "config": {
      "environment": {
        "VLLM_MODEL": "gpt2"
      },
      "resources": {
        "cpu": "8",
        "memory": "64G",
        "time_limit": 120,
        "gpu": "4"
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
    "recipe_name": "inference/vllm-single-node",
    "config": {
      "environment": {
        "VLLM_MODEL": "gpt2",
        "VLLM_HOST": "0.0.0.0",
        "VLLM_PORT": "8001",
        "VLLM_MAX_MODEL_LEN": "2048",
        "VLLM_TENSOR_PARALLEL_SIZE": "4",
        "VLLM_GPU_MEMORY_UTILIZATION": "0.9",
        "CUDA_VISIBLE_DEVICES": "0"
      },
      "resources": {
        "cpu": "2",
        "memory": "32G",
        "time_limit": 15,
        "gpu": "4"
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
    "recipe_name": "inference/vllm-single-node",
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

Send a text prompt to a single service or service group (group automatically routes to a healthy replica):

```bash
curl -X POST http://localhost:8001/api/v1/vllm/3652098/prompt \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Tell me a joke about programming",
    "max_tokens": 100
  }'
```

When using a service group, the response includes `routed_to` and `group_id` fields showing which replica handled the request.

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

## Vector DB (Qdrant) Examples

### List Collections

Get the list of collections from a running Qdrant service (replace SERVICE_ID):

```bash
curl http://localhost:8001/api/v1/vector-db/3642875/collections
```

### Create Collection

Create a collection named `my_documents` with 384-dimensional vectors using Cosine distance:

```bash
curl -X PUT "http://localhost:8001/api/v1/vector-db/3642875/collections/my_documents" \
  -H "Content-Type: application/json" \
  -d '{"vector_size": 384, "distance": "Cosine"}'
```

### Upsert Points

Insert one or more points into a collection. Each point must contain `id` and `vector` and may include a `payload`:

```bash
curl -X PUT "http://localhost:8001/api/v1/vector-db/3642875/collections/my_documents/points" \
  -H "Content-Type: application/json" \
  -d '{
    "points": [
      {"id": 1, "vector": [0.1, 0.2, 0.3, 0.4], "payload": {"text": "First document"}},
      {"id": 2, "vector": [0.4, 0.5, 0.6, 0.7], "payload": {"text": "Second document"}}
    ]
  }'
```

### Search Points

Perform a similarity search against a collection (returns most similar points):

```bash
curl -X POST "http://localhost:8001/api/v1/vector-db/3642875/collections/my_documents/points/search" \
  -H "Content-Type: application/json" \
  -d '{"query_vector": [0.1, 0.2, 0.3, 0.4], "limit": 5}'
```

## Metrics Examples

### Qdrant Metrics (Prometheus)

Qdrant exposes Prometheus-compatible metrics on `/metrics`. Fetch raw metrics (text format):

```bash
curl http://localhost:8001/api/v1/vector-db/3642875/metrics
```

### vLLM Metrics (Prometheus)

vLLM exposes Prometheus-compatible metrics on `/metrics`. Fetch raw metrics (text format):

```bash
curl http://localhost:8001/api/v1/vllm/3642874/metrics
```

## Notes

### Python examples

If you prefer runnable Python demos that exercise the Server API (vector DB and vLLM flows), see the `examples/` folder at the repository root. Notable scripts:

- `examples/qdrant_simple_example.py`
- `examples/qdrant_simple_example_with_metrics.py`
- `examples/vllm_simple_example.py`
- `examples/vllm_simple_example_with_metrics.py`
- `examples/vllm_data_parallel_example.py` - demonstrates replica groups with load balancing

Run an example locally (adjust arguments or SERVICE_ID inside the script where required):

```bash
python3 examples/vllm_data_parallel_example.py
```


- **Default Model**: If not specified, services use `Qwen/Qwen2.5-0.5B-Instruct`
- **Model Sources**: Models must be available on HuggingFace or cached locally
- **Resource Defaults**: Each recipe has default resource allocations that can be overridden
- **Status Values**: Services progress through states: `pending` → `building` → `starting` → `running`
- **Service ID**: The SLURM job ID is used as the service identifier
