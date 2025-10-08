# 🚀 Container Orchestration for Meluxina HPC

## Overview

This system provides **Kubernetes-like container orchestration** for the Meluxina HPC environment using Apptainer + SLURM. You get all the benefits of K8s-style deployments without needing an actual Kubernetes cluster.

## Features

✅ **K8s-style YAML deployments**  
✅ **Container orchestration via SLURM**  
✅ **Service discovery and networking**  
✅ **Scaling and lifecycle management**  
✅ **Multi-container pod deployments**  
✅ **Dependency management**  

## Quick Start

### 1. Build Container Images

```bash
# Build all microservice containers
./scripts/orchestrate.sh build
```

### 2. Deploy Microservice Stack

```bash
# Deploy the complete microservice stack
./scripts/orchestrate.sh deploy

# Or deploy a custom configuration
./scripts/orchestrate.sh deploy /path/to/my-deployment.yaml
```

### 3. Manage Deployments

```bash
# List all running deployments
./scripts/orchestrate.sh list

# Scale a deployment
./scripts/orchestrate.sh scale ai-factory-microservices 3

# View logs
./scripts/orchestrate.sh logs ai-factory-microservices

# Stop a deployment
./scripts/orchestrate.sh stop ai-factory-microservices
```

## API Usage

You can also manage deployments via the REST API:

```bash
# Deploy via API
curl -X POST "http://localhost:8001/stacks/deploy" \
  -H "Content-Type: application/json" \
  -d '{"deployment_yaml": "/path/to/deployment.yaml"}'

# List stacks
curl "http://localhost:8001/stacks"

# Scale a stack
curl -X PUT "http://localhost:8001/stacks/{stack_id}/scale?replicas=3"

# Stop a stack
curl -X DELETE "http://localhost:8001/stacks/{stack_id}"
```

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │────│ Container       │────│   SLURM Jobs    │
│                 │    │ Orchestrator    │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   REST API      │    │   K8s-style     │    │   Apptainer     │
│   Endpoints     │    │   YAML Config   │    │   Containers    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## YAML Configuration

Your deployments use familiar K8s-style YAML:

```yaml
apiVersion: v1
kind: Deployment
metadata:
  name: ai-factory-microservices

containers:
  - name: server-service
    image: /workspace/containers/server-service.sif
    ports: [8001]
    environment:
      SERVICE_NAME: "server"
      SERVICE_PORT: "8001"
    replicas: 1

services:
  - name: server-service
    selector:
      app: server-service
    ports:
      - port: 8001
        targetPort: 8001
    type: ClusterIP
```

## Microservice Communication

Services communicate via HTTP using service discovery:

```python
# In your microservice code
from shared.service_discovery import service_client

# Call another microservice
response = await service_client.call_service(
    "server-service", 
    "/api/jobs", 
    method="POST",
    json={"job_spec": {...}}
)
```

## Benefits over Traditional K8s

🎯 **HPC Optimized**: Designed for SLURM-based HPC environments  
🎯 **No K8s Overhead**: Lighter weight than full Kubernetes  
🎯 **GPU Ready**: Native Apptainer GPU support with `--nv`  
🎯 **MPI Support**: Seamless MPI application integration  
🎯 **Familiar API**: K8s-style deployments and management  

## Example Workflow

```bash
# 1. Build your containers
./scripts/orchestrate.sh build

# 2. Deploy your stack
./scripts/orchestrate.sh deploy

# 3. Check status
./scripts/orchestrate.sh list

# 4. Scale up for load
./scripts/orchestrate.sh scale ai-factory-microservices 5

# 5. Monitor logs
./scripts/orchestrate.sh logs ai-factory-microservices

# 6. Clean up
./scripts/orchestrate.sh stop ai-factory-microservices
```

This gives you the **container orchestration experience you want** while working perfectly with Meluxina's HPC infrastructure! 🚀