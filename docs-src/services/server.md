# Server API Reference

The Server Service provides REST API for managing AI services on the MeluXina supercomputer.

## Interactive API Documentation

!!! tip "Live API Explorer"
    The best way to explore the API is here:
    
    **[Open Interactive API Docs](../../api/server){ .md-button .md-button--primary }**

## Overview

A FastAPI gateway server that proxies AI workload orchestration requests to a ServiceOrchestrator running on MeluXina.

### Architecture

The system consists of two main components:

1. **Server (Gateway)**: Runs locally (e.g., laptop/workstation), exposes REST API, forwards requests via SSH
2. **ServiceOrchestrator**: Runs on MeluXina, manages SLURM jobs, handles container deployment

### What it does

- **API Gateway**: Provides a stable REST API endpoint for external clients
- **Request Proxying**: Forwards all orchestration requests to the ServiceOrchestrator via SSH tunnels
- **Dual Access Pattern**: 
  - **External clients** → Server (localhost:8001) → SSH tunnel → Orchestrator (MeluXina)
  - **Internal clients** (on MeluXina) → Orchestrator API directly (orchestrator:8000)


### Deployment Architecture

The system is split across two locations with clear separation of concerns:

```mermaid
graph TB
    subgraph Local["Local Machine (Laptop/Workstation)"]
        Client["Client Application"]
        Server["Server (Gateway)<br/>FastAPI<br/>Port 8001"]
    end
    
    subgraph MeluXina["MeluXina Supercomputer"]
        Orchestrator["ServiceOrchestrator<br/>FastAPI<br/>Port 8000"]
        SLURM["SLURM Cluster"]
        Compute["Compute Nodes<br/>(vLLM, Qdrant, etc.)"]
    end
    
    Client -->|"HTTP: localhost:8001"| Server
    Server -->|"SSH Tunnel<br/>(http_request_via_ssh)"| Orchestrator
    Orchestrator -->|"sbatch/scancel"| SLURM
    SLURM -->|"Job Control"| Compute
    Orchestrator -->|"HTTP<br/>(status, models, prompts)"| Compute
    
    InternalClient["Internal Client<br/>(on MeluXina)"] -.->|"HTTP: orchestrator:8000<br/>(Direct Access)"| Orchestrator
    
    style Server fill:#B3E5FC,stroke:#0288D1,stroke-width:2px
    style Orchestrator fill:#C8E6C9,stroke:#388E3C,stroke-width:2px
    style Client fill:#FFF9C4,stroke:#FBC02D,stroke-width:1px
    style InternalClient fill:#FFF9C4,stroke:#FBC02D,stroke-width:1px,stroke-dasharray: 5 5
```

**Key Points:**

- **Server (Gateway)**: Lightweight proxy running locally, provides stable API endpoint
- **ServiceOrchestrator**: Heavy lifting component on MeluXina, manages SLURM and containers
- **SSH Tunnel**: Secure communication channel between server and orchestrator
- **Dual Access**: External clients use the gateway; internal MeluXina clients can bypass it

### Server (Gateway) Components

The server component focuses on request proxying and client-facing API:

```mermaid
classDiagram
    class FastAPIApp:::api {
        +root()
        +health()
    }
    
    class APIRouter:::api {
        +create_service()
        +list_services()
        +stop_service()
        +get_service_status()
        +update_service_status()
        +vllm_endpoints()
        +vector_db_endpoints()
    }
    
    class OrchestratorProxy:::proxy {
        +start_service(recipe, config)
        +stop_service(service_id)
        +list_services()
        +get_service_status(service_id)
        +prompt_vllm_service(...)
        +get_vllm_models(...)
        +_make_request(method, endpoint)
    }
    
    class SSHManager:::ssh {
        +http_request_via_ssh(host, port, method, path)
        +execute_remote_command(cmd)
        +setup_tunnel(local_port, remote_port)
    }
    
    FastAPIApp --> APIRouter
    APIRouter --> OrchestratorProxy
    OrchestratorProxy --> SSHManager
    
    classDef api fill:#B3E5FC,stroke:#0288D1,stroke-width:2px
    classDef proxy fill:#FFE0B2,stroke:#F57C00,stroke-width:2px
    classDef ssh fill:#E0E0E0,stroke:#9E9E9E,stroke-width:1px
```

**Server Layer Responsibilities:**

- Expose REST API on `localhost:8001` for external clients
- Parse and validate client requests
- Forward requests to orchestrator via SSH tunnels
- Handle SSH connection failures gracefully
- Return normalized responses to clients

### ServiceOrchestrator Components (on MeluXina)

The orchestrator handles all the heavy lifting:

```mermaid
classDiagram
    class OrchestratorAPI:::api {
        +start_service()
        +stop_service()
        +list_services()
        +get_service_group()
    }
    
    class ServiceOrchestrator:::core {
        +start_service(recipe_name, config)
        +stop_service(service_id)
        +update_service_status(service_id, status)
        +stop_service_group(group_id)
        +update_service_group_status(group_id, status)
    }
    
    class SlurmDeployer:::infra {
        +submit_job()
        +cancel_job()
        +get_job_status()
    }
    
    class ServiceManager:::infra {
        +register_service()
        +get_service()
        +update_service_status()
    }
    
    class RecipeLoader:::infra {
        +load(recipe_name)
        +list_all()
    }
    
    class BuilderRegistry:::infra {
        +create_builder(category)
    }
    
    OrchestratorAPI --> ServiceOrchestrator
    ServiceOrchestrator *-- SlurmDeployer
    ServiceOrchestrator *-- ServiceManager
    ServiceOrchestrator *-- RecipeLoader
    SlurmDeployer --> BuilderRegistry
    
    classDef api fill:#C8E6C9,stroke:#388E3C,stroke-width:2px
    classDef core fill:#DCEDC8,stroke:#8BC34A,stroke-width:2px
    classDef infra fill:#F5F5F5,stroke:#9E9E9E,stroke-width:1px
```

**Orchestrator Layer Responsibilities:**

- Expose internal API on `orchestrator:8000` (accessible from MeluXina network)
- Load and parse recipe YAML files
- Generate SLURM job scripts with appropriate resource allocations
- Submit jobs to SLURM via `sbatch`
- Track service lifecycle (pending → configuring → running → cancelled)
- Resolve compute node endpoints for running services
- Query service health and models from compute nodes
- Handle service groups (replica sets) and load balancing

### Service Handlers & Types

```mermaid
graph TD
    %% =========================================
    %% Base / Abstract layer
    %% =========================================
    BaseService["BaseService"]

    %% =========================================
    %% Subgraphs / Layers
    %% =========================================
    subgraph InferenceLayer["Inference Layer"]
        InferenceService["InferenceService"]
        VllmService["VllmService"]
    end

    subgraph VectorDBLayer["VectorDB Layer"]
        VectorDbService["VectorDbService"]
        QdrantService["QdrantService"]
    end

    subgraph InfraLayer["Infrastructure Layer"]
        SlurmDeployer["SlurmDeployer"]
        EndpointResolver["EndpointResolver"]
    end

    %% =========================================
    %% Inheritance / Composition
    %% =========================================
    BaseService --> InferenceService
    InferenceService --> VllmService
    BaseService --> VectorDbService
    VectorDbService --> QdrantService

    %% =========================================
    %% Dependencies
    %% =========================================
    VllmService --> EndpointResolver
    QdrantService --> EndpointResolver
    VllmService --> SlurmDeployer
    QdrantService --> SlurmDeployer

    %% =========================================
    %% Styling
    %% =========================================
    class BaseService base
    class InferenceService inference
    class VllmService inference
    class VectorDbService vectordb
    class QdrantService vectordb
    class SlurmDeployer infra
    class EndpointResolver infra

    classDef base fill:#FFF9C4,stroke:#FBC02D,stroke-width:1px,color:#795548
    classDef inference fill:#DCEDC8,stroke:#8BC34A,stroke-width:1px,color:#33691E
    classDef vectordb fill:#E1BEE7,stroke:#8E24AA,stroke-width:1px,color:#4A148C
    classDef infra fill:#E0E0E0,stroke:#9E9E9E,stroke-width:1px,color:#424242

```

The service-handlers diagram explains how domain-specific functionality is organized:

- `BaseService` provides the shared plumbing (deployer access, service registry, endpoint resolution) used by concrete handlers.
- `InferenceService` and `VectorDbService` define the operations expected by their domains; `VllmService` and `QdrantService` implement those operations against running jobs.
- These handlers consult `SlurmDeployer` for live job state and `EndpointResolver` to discover the compute-node HTTP endpoints used to reach the actual running services.

Refer to this diagram when extending the system with a new service type (create a subclass of `BaseService` and implement the domain-specific API surface).

## How Recipe YAML Files Work

Recipe YAML files define service configurations that are loaded and used to generate SLURM job scripts for deploying services on the cluster.

### Recipe Loading Flow

```
User Request → RecipeLoader.load(recipe_name) → YAML File Read → Recipe Object → SlurmDeployer
                                                                                         ↓
BuilderRegistry.create_builder() → RecipeScriptBuilder → Generated SLURM Script → sbatch
```

### Recipe YAML Structure

Each recipe YAML file contains:

| Section | Purpose |
|---------|---------|
| `name` | Recipe identifier (e.g., `vllm`) |
| `category` | Service type: `inference`, `vector-db`, or `storage` |
| `description` | Human-readable service description |
| `image` | Singularity/Apptainer image filename (built from `.def`) |
| `container_def` | Singularity definition file for building the image |
| `ports` | Default ports the service exposes |
| `environment` | Environment variables passed to the container |
| `resources` | Default SLURM resource requests (can be overridden per job) |
| `distributed` | Configuration for multi-node/multi-GPU execution |
| `replicas` | Number of independent service instances for data parallelism (optional) |

### Example: vLLM Recipe

```yaml
name: vllm-single-node
category: inference
description: "vLLM high-performance inference server for large language models"
version: "0.2.0"
image: "vllm.sif"
container_def: "vllm.def"

ports:
  - 8001

environment:
  VLLM_HOST: "0.0.0.0"
  VLLM_PORT: "8001"
  VLLM_MODEL: "Qwen/Qwen2.5-0.5B-Instruct"
  VLLM_WORKDIR: "/workspace"
  VLLM_LOGGING_LEVEL: "INFO"
  VLLM_TENSOR_PARALLEL_SIZE: "4" 

resources:
  nodes: "1"
  cpu: "2"
  memory: "32G"
  time_limit: 15
  gpu: "4"
```

### Multi-Replica Configuration

The `vllm-replicas` recipe creates multiple replicas on a single node for high-throughput inference:

```yaml
name: vllm-replicas
category: inference
description: "vLLM with multiple replicas - flexible GPU allocation per replica"

environment:
  VLLM_HOST: "0.0.0.0"
  VLLM_MODEL: "Qwen/Qwen2.5-0.5B-Instruct"
  # ... other settings ...

resources:  # Per node (not per replica)
  nodes: "1"  # Number of nodes to allocate
  cpu: "8"    # CPUs per node
  memory: "64G"  # Memory per node
  time_limit: 15
  gpu: "4"    # Total GPUs per node

# Replica group configuration
# System calculates: replicas_per_node = gpu / gpu_per_replica
gpu_per_replica: 1  # Each replica uses 1 GPU (data parallel)
base_port: 8001     # First replica uses 8001, second uses 8002, etc.
```

**How it works:**
- With `gpu: 4` and `gpu_per_replica: 1`, you get 4 replicas
- Each replica runs independently on separate GPUs (0, 1, 2, 3)
- Replicas listen on consecutive ports (8001, 8002, 8003, 8004)
- All replicas run in a single SLURM job
- Load balancing distributes requests using round-robin with automatic failover

### How Recipes Are Used

1. **Service Creation**: User calls `/api/v1/services` with `recipe_name: "inference/vllm-single-node"`
2. **Recipe Loading**: `RecipeLoader` reads `recipes/inference/vllm-single-node.yaml`
3. **Configuration Merge**: User-provided config (e.g., `gpu: 8`) overrides recipe defaults
4. **Replica Detection**: If `gpu_per_replica` field is present, calculate replicas per node
5. **Builder Selection**: `BuilderRegistry` selects recipe-specific builder or category default
6. **Script Generation**: Builder generates SLURM script with replica configuration
7. **Job Submission**: Submit single SLURM job that launches all replicas on assigned GPUs

### Recipe-Specific Builders

Some recipes have custom builders that override script generation behavior. For example:

- **`VllmInferenceBuilder`**: Overrides `build_distributed_run_block()` to add tensor parallelism with `torchrun`
- **`QdrantVectorDbBuilder`**: Overrides `build_run_block()` to mount job-specific storage paths

This allows recipes to customize script generation without modifying the core `SlurmDeployer`.

### Recipe Script Builders (Orchestrator Component)

The following diagram shows the Recipe Builder architecture **running on the ServiceOrchestrator** (MeluXina side). It uses the Strategy pattern to generate SLURM job scripts for different recipe types. This modular design allows adding new services without modifying the core SLURM deployer.

```mermaid
classDiagram
    %% =========================================
    %% Abstract Base
    %% =========================================
    class RecipeScriptBuilder:::base {
        <<abstract>>
        +build_environment_section()*
        +build_container_build_block()*
        +build_run_block()*
        +supports_distributed()
        +build_distributed_run_block()*
    }

    class BuilderRegistry:::registry {
        +register(category, builder_class)
        +register_recipe(recipe_name, builder_class)
        +create_builder(category, recipe_name)
        +list_categories()
        +list_recipes()
    }

    %% =========================================
    %% Category Builders (Generic)
    %% =========================================
    class InferenceRecipeBuilder:::inference {
        +build_environment_section()
        +build_container_build_block()
        +build_run_block()
        +supports_distributed() bool
        +build_distributed_run_block()
    }

    class VectorDbRecipeBuilder:::vectordb {
        +build_environment_section()
        +build_container_build_block()
        +build_run_block()
        +supports_distributed() bool
    }

    %% =========================================
    %% Recipe-Specific Builders
    %% =========================================
    class VllmInferenceBuilder:::inference {
        +build_distributed_run_block()
    }

    class QdrantVectorDbBuilder:::vectordb {
        +build_run_block()
    }

    %% =========================================
    %% Client
    %% =========================================
    class SlurmDeployer:::client {
        +_create_script(recipe, config)
    }

    %% =========================================
    %% Relationships
    %% =========================================
    RecipeScriptBuilder <|-- InferenceRecipeBuilder
    RecipeScriptBuilder <|-- VectorDbRecipeBuilder
    InferenceRecipeBuilder <|-- VllmInferenceBuilder
    VectorDbRecipeBuilder <|-- QdrantVectorDbBuilder

    BuilderRegistry ..> RecipeScriptBuilder : creates
    SlurmDeployer --> BuilderRegistry : uses

    %% =========================================
    %% Styling
    %% =========================================
    classDef base fill:#FFF9C4,stroke:#FBC02D,stroke-width:2px,color:#795548
    classDef registry fill:#FFE0B2,stroke:#F57C00,stroke-width:2px,color:#E65100
    classDef inference fill:#DCEDC8,stroke:#8BC34A,stroke-width:1px,color:#33691E
    classDef vectordb fill:#E1BEE7,stroke:#8E24AA,stroke-width:1px,color:#4A148C
    classDef client fill:#E0E0E0,stroke:#9E9E9E,stroke-width:1px,color:#424242
```


## Further Reading

- [Service Recipes](recipes.md) - Available service templates
- [Architecture](../architecture/overview.md) - System design
- [Development Guide](../development/guidelines.md) - API development

---
