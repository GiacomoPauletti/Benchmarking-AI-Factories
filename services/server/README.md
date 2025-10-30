# AI Factory Server Service

This service provides orchestration and management capabilities for AI workloads across different deployment targets (Kubernetes, SLURM).


## Architecture

```
src/
├── main.py              # Application entry point
├── server_service.py    # Core logic
├── models/              # Data models
├── api/                 # REST API endpoints
├── deployment/          # Deployment orchestration
├── recipes/             # Recipe definitions (YAML/JSON)
└── health/              # Health check utilities
```

## Available Recipes

### Inference Services
- **vLLM**: High-performance LLM inference server
- **Triton**: NVIDIA Triton Inference Server

### Storage Services
- **MinIO**: Object storage server
- **PostgreSQL**: Relational database

### Vector Databases
- **Chroma**: Vector database for AI embeddings
- **FAISS**: Vector similarity search service

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python src/main.py
```

## API Usage

```bash
# List available recipes
curl http://localhost:8000/recipes

# Deploy a service
curl -X POST http://localhost:8000/services \
  -H "Content-Type: application/json" \
  -d '{"recipe_name": "vllm", "nodes": 1, "config": {}}'

# List running services
curl http://localhost:8000/services
```

## Development

```bash
# Run tests
pytest tests/

# Build Docker image
docker build -t ai-factory-server .
```