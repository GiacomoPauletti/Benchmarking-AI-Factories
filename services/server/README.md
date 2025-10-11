# AI Factory Server Service

A FastAPI server for orchestrating AI workloads on SLURM clusters using Apptainer containers.

## What it does

- **Service Orchestration**: Deploy and manage AI services via SLURM job submission
- **Recipe System**: Pre-defined configurations for common AI workloads
- **VLLM Integration**: Direct API access to running VLLM inference services
- **REST API**: Operations for service lifecycle management

## Architecture

```
src/
├── main.py              # FastAPI application (port 8001)
├── server_service.py    # Core orchestration logic
├── api/
│   ├── routes.py        # REST API endpoints
│   └── schemas.py       # Pydantic models
├── deployment/
│   └── slurm.py         # SLURM REST API integration
├── recipes/             # YAML recipe definitions
│   ├── inference/       # vLLM, Triton
│   ├── storage/         # MinIO, PostgreSQL
│   ├── vector-db/       # Chroma, FAISS
│   └── simple/          # Test recipes
└── health/              # Health checking utilities
```

## Available Recipes

- **vLLM**: High-performance LLM inference (real and dummy versions)
- **Hello**: Simple test service

## Quick Start

### Launch Server
```bash
# Get interactive SLURM node and start server
./launch_server.sh
```
This generates a base endpoint from which the API will be accessible.
This base endpoint should be used in the "node" placeholder of the following 
instructions.

### API Usage
```bash
# Health check
curl http://<node>:8001/health

# List recipes
curl http://<node>:8001/api/v1/recipes

# Deploy vLLM service
curl -X POST http://<node>:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{"recipe_name": "vllm", "config": {"nodes": 1}}'

# List running services
curl http://<node>:8001/api/v1/services

# Prompt VLLM service
curl -X POST http://<node>:8001/api/v1/vllm/{service_id}/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello world"}'
```

## Development

### Local Development
```bash
# Build the server container
apptainer build server.sif server.def

# Run server in container (requires SLURM_JWT token)
apptainer run \
  --env SLURM_JWT="${SLURM_JWT}" \
  --bind /home/users/<user>:/home/users/<user> \
  server.sif
```

### Testing
```bash
# Run tests in Apptainer container
./run-tests.sh
```

### Environment
- **Cluster**: Meluxina (Luxembourg)
- **Scheduler**: SLURM with REST API
- **Container**: Apptainer
- **Language**: Python 3.11+
- **Framework**: FastAPI + Uvicorn