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

### Launch Server Locally
```bash
cd services/server
./launch_local.sh
```

The server will be available at http://localhost:8001

### API Usage
```bash
# Health check
curl http://localhost:8001/health

# List recipes
curl http://localhost:8001/api/v1/recipes

# Deploy vLLM service (executes on MeluXina)
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{"recipe_name": "vllm", "config": {"nodes": 1}}'

# List running services
curl http://localhost:8001/api/v1/services

# Prompt VLLM service
curl -X POST http://localhost:8001/api/v1/vllm/{service_id}/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello world"}'
```

## Development

### Local Development with Docker

Run the server locally on your laptop in Docker while tunneling to MeluXina for SLURM job orchestration. This provides the best development experience with fast iteration and full IDE support.

#### Architecture

```
┌─────────────────────────────────────┐
│  Local Laptop (Docker)              │
│  ┌────────────────────────────────┐ │
│  │  FastAPI Server Container      │ │
│  │  - API endpoints               │ │
│  │  - Hot-reload on code changes  │ │
│  │  - SLURM client (via SSH)      │ │
│  └────────────────────────────────┘ │
│           │ SSH Tunnel               │
└───────────┼─────────────────────────┘
            │
            ▼
┌─────────────────────────────────────┐
│  MeluXina HPC Cluster               │
│  ┌────────────────────────────────┐ │
│  │  SLURM Job Submission          │ │
│  │  Apptainer containers          │ │
│  │  GPU nodes                     │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

#### Prerequisites

1. **Docker Desktop** installed and running
2. **SSH access to MeluXina** configured (password-less with SSH keys)
   ```bash
   # Add to ~/.ssh/config
   Host meluxina
       HostName login.lxp.lu
       User <your_meluxina_username>
       IdentityFile ~/.ssh/<your_private_key>
   ```

See [LOCAL_SETUP.md](LOCAL_SETUP.md) for detailed setup instructions.

#### Setup

1. **Configure environment:**
   ```bash
   cd services/server
   cp .env.local.example .env.local
   # Edit .env.local with your credentials
   ```

2. **Edit `.env.local`:**
   ```bash
   SSH_TUNNEL_USER=\<your_meluxina_username\>
   SSH_TUNNEL_HOST=login.lxp.lu
   ENVIRONMENT=local-tunnel
   # Optional: Add SLURM_JWT if you have it
   ```

3. **Launch the server:**
   ```bash
   ./launch_local.sh
   ```

4. **Access the API:**
   - API docs: http://localhost:8001/docs
   - Health check: http://localhost:8001/health
   - OpenAPI spec: http://localhost:8001/openapi.json

#### How It Works

- FastAPI server runs in a Docker container on your laptop
- Code changes are hot-reloaded automatically (via volume mount)
- Job submission commands (`sbatch`, `squeue`, `scancel`) execute on MeluXina via SSH
- Logs are stored locally in `./logs`
- Hugging Face cache is shared with local filesystem

#### Benefits

✅ Full IDE support (debugging, autocomplete, etc.)  
✅ Fast iteration without cluster access  
✅ Use Docker instead of Apptainer locally  
✅ Only consume MeluXina resources when submitting jobs  
✅ Test API changes without rebuilding containers  

#### Development Workflow

```bash
# 1. Start server
./launch_local.sh

# 2. Edit code in src/
# Changes are automatically reloaded

# 3. Test API
curl http://localhost:8001/health

# 4. Submit a test job (executes on MeluXina)
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{"recipe_name": "hello", "config": {}}'

# 5. Check job status
curl http://localhost:8001/api/v1/services

# 6. Stop server (Ctrl+C)
```

For more detailed setup instructions, see [LOCAL_SETUP.md](LOCAL_SETUP.md).

### Testing

Run tests locally in Docker:
```bash
./run-tests.sh
```

### Technology Stack
- **Local Development**: Docker + SSH
- **Remote Cluster**: MeluXina (Luxembourg)
- **Scheduler**: SLURM (via SSH)
- **Container Runtime**: Apptainer (on cluster)
- **Language**: Python 3.11+
- **Framework**: FastAPI + Uvicorn