# Server API Reference

The Server Service provides REST API for managing AI services on the MeluXina supercomputer.

## Interactive API Documentation

!!! tip "Live API Explorer"
    The best way to explore the API is here:
    
    **[Open Interactive API Docs](../../api/server){ .md-button .md-button--primary }**

## Overview

A FastAPI server for orchestrating AI workloads on SLURM clusters using Apptainer containers.

### What it does

- **Service Orchestration**: Deploy and manage AI services via SLURM job submission
- **Recipe System**: Pre-defined configurations for common AI workloads
- **REST API**: Operations for service lifecycle management


### Orchestration & Infrastructure

The following class diagram describes the major components in the `services/server` microservice and how they relate to each other (FastAPI routing, orchestration, SLURM interaction, SSH, recipe loading and service-specific handlers).

```mermaid
classDiagram
%% =========================================
%% Groups / Layers
%% =========================================
class FastAPIApp:::api {
    +root()
    +health()
}

class APIRouter:::api {
    +create_service()
    +list_services()
    +get_service()
    +vllm_endpoints()
    +vector_db_endpoints()
}

class ServerService:::core {
    +start_service(recipe_name, config)
    +stop_service(service_id)
    +list_running_services()
    +get_service_status(service_id)
    +get_service_logs(service_id)
}

class SlurmDeployer:::infra {
    +submit_job()
    +cancel_job()
    +get_job_status()
    +get_job_logs()
    +get_job_details()
}

class SSHManager:::infra {
    +setup_slurm_rest_tunnel()
    +fetch_remote_file()
    +http_request_via_ssh()
    +sync_directory_to_remote()
}

class ServiceManager:::infra {
    +register_service()
    +list_services()
    +get_service()
    +update_service_status()
}

class RecipeLoader:::infra {
    +load(recipe_name)
    +list_all()
    +get_recipe_port()
}

class EndpointResolver:::infra {
    +resolve(job_id, default_port)
}

class BuilderRegistry:::infra {
    +create_builder(category, recipe_name)
    +register(category, builder_class)
    +register_recipe(recipe_name, builder_class)
}

%% =========================================
%% Main Relationships
%% =========================================
FastAPIApp --> APIRouter
APIRouter --> ServerService
ServerService *-- SlurmDeployer
ServerService *-- ServiceManager
ServerService *-- RecipeLoader
ServerService *-- EndpointResolver
SlurmDeployer --> SSHManager
SlurmDeployer --> BuilderRegistry
EndpointResolver --> SlurmDeployer

%% =========================================
%% Styling
%% =========================================
classDef api fill:#B3E5FC,stroke:#0288D1,stroke-width:1px,color:#01579B
classDef core fill:#C8E6C9,stroke:#388E3C,stroke-width:1px,color:#1B5E20
classDef infra fill:#F5F5F5,stroke:#9E9E9E,stroke-width:1px,color:#424242

```

The orchestration diagram above groups the primary infrastructure and control-path responsibilities:

- FastAPI exposes HTTP endpoints; the router maps requests to the server-layer.
- ServerService is the central coordinator: it submits jobs using SlurmDeployer, keeps service records in ServiceManager, loads recipes via RecipeLoader, and computes endpoints via EndpointResolver.
- SlurmDeployer is responsible for job lifecycle (submit/cancel/status) and relies on SSHManager for remote operations (tunnels, fetching logs, proxy HTTP calls to compute nodes) and BuilderRegistry for recipe-specific script generation.

When tracing a "create service" request, follow the path: FastAPIApp -> APIRouter -> ServerService -> SlurmDeployer (+ SSHManager + BuilderRegistry). Endpoint resolution happens later via EndpointResolver which queries SLURM job details and recipe metadata.

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

### Example: vLLM Recipe

```yaml
name: vllm
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

resources:
  nodes: "1"
  cpu: "2"
  memory: "32G"
  time_limit: 15
  gpu: "1"

distributed:
  nproc_per_node: 1        # Processes per node (e.g., GPUs)
  master_port: 29500       # Rendezvous port for distributed setup
  rdzv_backend: c10d       # PyTorch distributed backend
```

### How Recipes Are Used

1. **Service Creation**: User calls `/api/v1/services` with `recipe_name: "inference/vllm"`
2. **Recipe Loading**: `RecipeLoader` reads `recipes/inference/vllm.yaml`
3. **Configuration Merge**: User-provided config (e.g., `nodes: 2`) overrides recipe defaults
4. **Builder Selection**: `BuilderRegistry` selects `VllmInferenceBuilder` (recipe-specific) or falls back to `InferenceRecipeBuilder` (category default)
5. **Script Generation**: Builder generates SLURM script using recipe metadata and merged config
6. **Job Submission**: Script is submitted via `sbatch` to SLURM

### Recipe-Specific Builders

Some recipes have custom builders that override script generation behavior. For example:

- **`VllmInferenceBuilder`**: Overrides `build_distributed_run_block()` to add tensor parallelism with `torchrun`
- **`QdrantVectorDbBuilder`**: Overrides `build_run_block()` to mount job-specific storage paths

This allows recipes to customize script generation without modifying the core `SlurmDeployer`.

### Recipe Script Builders

The following diagram shows the Recipe Builder architecture, which uses the Strategy pattern to generate SLURM job scripts for different recipe types. This modular design allows adding new services without modifying the core SLURM deployer.

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
