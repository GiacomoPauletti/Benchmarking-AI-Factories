# Server API Reference

The Server Service provides a comprehensive REST API for managing AI services on the MeluXina supercomputer.

## Interactive API Documentation

!!! tip "Live API Explorer"
    The best way to explore the API is through the **interactive Swagger UI**:
    
    **📖 [Open Interactive API Docs](http://localhost:8001/docs){ .md-button .md-button--primary }**
    
    *(Replace `localhost:8001` with your actual server endpoint)*

The interactive documentation provides:

- ✅ **Try it out** - Execute API calls directly from the browser
- 📋 **Request/Response schemas** - See exact data structures
- 🔍 **Example values** - Pre-filled request examples
- 📝 **Detailed descriptions** - Comprehensive endpoint documentation

## Alternative Documentation Formats

- **Swagger UI**: `http://<server>:8001/docs`
- **ReDoc**: `http://<server>:8001/redoc` (alternative UI)
- **OpenAPI Schema**: `http://<server>:8001/openapi.json` (raw specification)

## Quick Reference

### Base URL

```
http://<hostname>:8001/api/v1
```

Replace `<hostname>` with your compute node name (e.g., `mel2106`).

### Endpoints Overview

| Category | Endpoint | Method | Description |
|----------|----------|--------|-------------|
| **Health** | `/health` | GET | Health check |
| **Services** | `/services` | GET | List all services |
| | `/services` | POST | Create new service |
| | `/services/{id}` | GET | Get service details |
| | `/services/{id}` | DELETE | Stop/delete service |
| | `/services/{id}/status` | GET | Get service status |
| | `/services/{id}/logs` | GET | Get service logs |
| **Recipes** | `/recipes` | GET | List available recipes |
| | `/recipes/{path}` | GET | Get recipe details |
| **vLLM** | `/vllm/services` | GET | List vLLM services |
| | `/vllm/{id}/prompt` | POST | Send prompt to vLLM |
| | `/vllm/{id}/models` | GET | List available models |

## Common API Patterns

### Authentication

Currently, the API does not require authentication. Access control is managed at the SLURM level.

!!! warning "Production Deployment"
    For production deployments, implement proper authentication (API keys, OAuth2, etc.)

### Request Format

All POST/PUT requests use JSON:

```bash
curl -X POST "http://mel2106:8001/api/v1/services" \
  -H "Content-Type: application/json" \
  -d '{"recipe_name": "inference/vllm"}'
```

### Response Format

All responses are JSON with consistent structure:

**Success Response:**
```json
{
  "id": "3614523",
  "name": "vllm-3614523",
  "status": "running",
  ...
}
```

**Error Response:**
```json
{
  "detail": "Service not found"
}
```

### HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful GET, DELETE |
| 201 | Created | Successful POST (resource created) |
| 400 | Bad Request | Invalid request data |
| 404 | Not Found | Resource doesn't exist |
| 500 | Internal Server Error | Server-side error |

## Key Endpoints

### Health Check

```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### Create Service

```bash
POST /api/v1/services
```

**Request Body:**
```json
{
  "recipe_name": "inference/vllm",
  "config": {
    "environment": {
      "VLLM_MODEL": "Qwen/Qwen2.5-0.5B-Instruct",
      "VLLM_MAX_MODEL_LEN": "2048"
    },
    "resources": {
      "cpu": "8",
      "memory": "32G",
      "gpu": "1",
      "time_limit": 60
    }
  }
}
```

**Response:**
```json
{
  "id": "3614523",
  "name": "vllm-3614523",
  "recipe_name": "inference/vllm",
  "status": "pending",
  "config": { ... },
  "created_at": "2025-10-14T12:00:00"
}
```

### List Services

```bash
GET /api/v1/services
```

**Response:**
```json
[
  {
    "id": "3614523",
    "name": "vllm-3614523",
    "recipe_name": "inference/vllm",
    "status": "running",
    ...
  },
  ...
]
```

### Get Service Status

```bash
GET /api/v1/services/{id}/status
```

**Response:**
```json
{
  "status": "running",
  "slurm_state": "RUNNING",
  "job_id": "3614523",
  "node": "mel2106"
}
```

**Status Values:**
- `pending` - Job queued in SLURM
- `building` - Container image being built
- `starting` - Container started, application initializing
- `running` - Service fully operational
- `completed` - Service finished successfully
- `failed` - Service encountered an error
- `cancelled` - Service was stopped by user

### Send vLLM Prompt

```bash
POST /api/v1/vllm/{id}/prompt
```

**Request Body:**
```json
{
  "prompt": "Explain quantum computing in simple terms.",
  "max_tokens": 100,
  "temperature": 0.7
}
```

**Response:**
```json
{
  "response": "Quantum computing is a type of computing...",
  "model": "Qwen/Qwen2.5-0.5B-Instruct",
  "tokens_used": 87
}
```

### Stop Service

```bash
DELETE /api/v1/services/{id}
```

**Response:**
```json
{
  "message": "Service stopped successfully",
  "job_id": "3614523"
}
```

## Error Handling

### Service Not Ready

When accessing a vLLM service that's still starting:

```json
{
  "error": "Service not available",
  "message": "The service may still be starting up. Please wait and try again.",
  "details": "Connection refused at mel2106:8001"
}
```

**Solution**: Wait for service to reach `running` status.

### Chat Template Error

If a base model doesn't support chat:

```json
{
  "error": "Chat completion failed",
  "message": "The model may not support chat templates. Try using a different prompt format.",
  "fallback": "Automatically retried with completions endpoint"
}
```

The API automatically falls back to the completions endpoint.

### Invalid Recipe

```json
{
  "detail": "Recipe 'invalid/recipe' not found"
}
```

**Solution**: Check available recipes with `GET /api/v1/recipes`.

## Configuration Options

### Environment Variables

Common environment variables for services:

**vLLM:**
```json
{
  "VLLM_MODEL": "model-name",
  "VLLM_MAX_MODEL_LEN": "2048",
  "VLLM_GPU_MEMORY_UTILIZATION": "0.9",
  "VLLM_TENSOR_PARALLEL_SIZE": "1"
}
```

### Resource Allocation

```json
{
  "resources": {
    "cpu": "8",           // Number of CPUs
    "memory": "32G",      // Memory (G suffix)
    "gpu": "1",           // GPU count (null for CPU-only)
    "time_limit": 60      // Minutes
  }
}
```

## Code Examples

### Python

```python
import requests

server = "http://mel2106:8001"

# Create service
response = requests.post(
    f"{server}/api/v1/services",
    json={
        "recipe_name": "inference/vllm",
        "config": {
            "environment": {"VLLM_MODEL": "gpt2"}
        }
    }
)
service = response.json()
service_id = service["id"]

# Wait for service to be ready
import time
while True:
    status = requests.get(f"{server}/api/v1/services/{service_id}/status").json()
    if status["status"] == "running":
        break
    time.sleep(5)

# Send prompt
response = requests.post(
    f"{server}/api/v1/vllm/{service_id}/prompt",
    json={"prompt": "Hello, world!"}
)
print(response.json()["response"])
```

### Bash

```bash
#!/bin/bash
SERVER="http://mel2106:8001"

# Create service
SERVICE_ID=$(curl -s -X POST "${SERVER}/api/v1/services" \
  -H "Content-Type: application/json" \
  -d '{"recipe_name": "inference/vllm"}' \
  | jq -r '.id')

echo "Created service: $SERVICE_ID"

# Wait for running status
while true; do
  STATUS=$(curl -s "${SERVER}/api/v1/services/${SERVICE_ID}/status" | jq -r '.status')
  echo "Status: $STATUS"
  [[ "$STATUS" == "running" ]] && break
  sleep 5
done

# Send prompt
curl -X POST "${SERVER}/api/v1/vllm/${SERVICE_ID}/prompt" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello!"}'
```

## Further Reading

- [Service Recipes](recipes.md) - Available service templates
- [Architecture](../architecture/overview.md) - System design
- [Development Guide](../development/guidelines.md) - API development

---

!!! info "OpenAPI Specification"
    The complete, machine-readable API specification is available at:
    `http://<server>:8001/openapi.json`
    
    This can be imported into tools like Postman, Insomnia, or used to generate client SDKs.
