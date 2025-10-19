# Getting Started

This guide will help you set up and run the AI Factory Benchmarking Framework on the MeluXina supercomputer.

## Prerequisites

### Requirements

- Access to **MeluXina** supercomputer
- SLURM allocation (account: `p200981` or your project account)
- Docker and docker compose

### Required Modules

On MeluXina, load the following modules:

```bash
module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0
```

## Installation

### 1. Clone the Repository

```bash
cd $HOME
git clone https://github.com/GiacomoPauletti/Benchmarking-AI-Factories.git
cd Benchmarking-AI-Factories
```

### 2. Set Up Environment Variables

The server requires the `SERVER_BASE_PATH` environment variable (automatically set by launch scripts):

```bash
export SERVER_BASE_PATH="$(pwd)/services/server"
```

### 3. Verify Setup

Check that all required files are present:

```bash
ls -la services/server/
# Should show: launch_server.sh, server.def, src/, docs/, tests/, etc.
```

## First Steps

### Launch the Server

The easiest way to start is with the server service:

```bash
cd services/server
./launch_server.sh
```

This script will:

1. Request an interactive compute node from SLURM
2. Build the Apptainer container (first time only)
3. Start the FastAPI server
4. Display the endpoint URL

**Output example:**
```
========================================
Interactive node allocated: mel2106
========================================
Starting AI Factory Server on mel2106:8001
========================================
API Docs: http://mel2106:8001/docs
Health: http://mel2106:8001/health
========================================
```

### Access the API

Once the server is running:

1. **Interactive API Docs**: Open `http://<hostname>:8001/docs` in your browser
2. **Health Check**: `curl http://<hostname>:8001/health`
3. **OpenAPI Spec**: `http://<hostname>:8001/openapi.json`

!!! tip "Using the API Docs"
    The `/docs` endpoint provides an interactive Swagger UI where you can:
    
    - Browse all available endpoints
    - See request/response schemas
    - Try out API calls directly
    - View example requests

## Quick Example

### Create a vLLM Service

```bash
# Set the server endpoint
export SERVER_ENDPOINT="http://mel2106:8001"

# Create a vLLM inference service
curl -X POST "${SERVER_ENDPOINT}/api/v1/services" \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "inference/vllm",
    "config": {
      "environment": {
        "VLLM_MODEL": "Qwen/Qwen2.5-0.5B-Instruct"
      },
      "resources": {
        "cpu": "8",
        "memory": "32G",
        "gpu": "1"
      }
    }
  }'
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

### Check Service Status

```bash
# Get service status
curl "${SERVER_ENDPOINT}/api/v1/services/3614523/status"

# List all services
curl "${SERVER_ENDPOINT}/api/v1/services"
```

### Send a Prompt (when service is ready)

```bash
curl -X POST "${SERVER_ENDPOINT}/api/v1/vllm/3614523/prompt" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain quantum computing in simple terms."
  }'
```

## Running Tests

The project includes comprehensive test suites:

```bash
cd services/server
./run-tests.sh
```

This will:

1. Request a compute node
2. Build the test container
3. Run unit tests
4. Start a test server
5. Run integration tests

See [Testing Documentation](../services/server/testing.md) for details.

## Next Steps

<div class="grid cards" markdown>

- :material-file-tree: [**Architecture Overview**](../architecture/overview.md)
  
  Understand the system components and design

- :material-api: [**Server API Reference**](../services/server/api-reference.md)
  
  Explore all available endpoints

- :material-cog: [**Recipes Guide**](../services/server/recipes.md)
  
  Learn about service recipes and configuration

- :material-code-braces: [**Development Guide**](../development/guidelines.md)
  
  Start contributing to the project

</div>

## Common Issues

### Container Build Fails

If the Apptainer build fails:

```bash
# Try building with explicit options
apptainer build --fakeroot --force server.sif server.def
```

### SLURM Token Issues

If you get SLURM authentication errors:

```bash
# Verify your SLURM token
scontrol token

# Ensure you're on a compute node
hostname  # Should show mel#### (compute node)
```

### Port Already in Use

If port 8001 is busy:

```bash
# Stop existing server
pkill -f "uvicorn main:app"

# Or use a different port
export PORT=8002
./launch_server.sh
```

## Getting Help

- **API Documentation**: `http://<server>:8001/docs`
- **GitHub Issues**: [Report a bug](https://github.com/GiacomoPauletti/Benchmarking-AI-Factories/issues)
- **Server Logs**: Check `services/server/logs/` directory

---

Ready to dive deeper? Continue to [Installation Details](installation.md) or jump to [Quick Start](quickstart.md)!
