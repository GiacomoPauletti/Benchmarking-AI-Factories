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
- **VLLM Integration**: Direct API access to running VLLM inference services
- **REST API**: Operations for service lifecycle management

### Architecture

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

The following class diagram describes the major components in the `services/server` microservice and how they relate to each other (FastAPI routing, orchestration, SLURM interaction, SSH, recipe loading and service-specific handlers).

```mermaid
classDiagram
    %% Core app and API
    class FastAPIApp {
        +root()
        +health()
    }
    class APIRouter <<router>> {
        +create_service()
        +list_services()
        +get_service()
        +vllm_endpoints()
        +vector_db_endpoints()
    }

    %% Main service orchestration
    class ServerService {
        -deployer: SlurmDeployer
        -service_manager: ServiceManager
        -recipe_loader: RecipeLoader
        -endpoint_resolver: EndpointResolver
        -_vllm_service
        -_vector_db_service
        +start_service(recipe_name, config)
        +stop_service(service_id)
        +list_running_services()
        +get_service_status(service_id)
        +get_service_logs(service_id)
    }

    %% SLURM + SSH
    class SlurmDeployer {
        -ssh_manager: SSHManager
        +submit_job()
        +cancel_job()
        +get_job_status()
        +get_job_logs()
        +get_job_details()
    }

    class SSHManager {
        +setup_slurm_rest_tunnel()
        +fetch_remote_file()
        +http_request_via_ssh()
        +sync_directory_to_remote()
    }

    %% Persistence / bookkeeping
    class ServiceManager <<singleton>> {
        +register_service()
        +list_services()
        +get_service()
        +update_service_status()
    }

    %% Recipes and endpoint resolution
    class RecipeLoader {
        +load(recipe_name)
        +list_all()
        +get_recipe_port()
    }

    class EndpointResolver {
        +resolve(job_id, default_port)
    }

    %% Base service classes and concrete implementations
    class BaseService {
        -deployer
        -service_manager
        -endpoint_resolver
        -logger
        +_filter_services()
    }

    class InferenceService {
        <<abstract>>
        +get_models()
        +prompt()
        +_check_service_ready()
    }

    class VllmService {
        +find_services()
        +get_models()
        +prompt()
        +get_metrics()
    }

    class VectorDbService {
        <<abstract>>
        +get_collections()
        +create_collection()
        +upsert_points()
        +search_points()
    }

    class QdrantService {
        +find_services()
        +get_collections()
        +create_collection()
        +upsert_points()
        +get_metrics()
    }

    %% Relationships
    FastAPIApp --> APIRouter : includes
    APIRouter --> ServerService : depends on / calls
    ServerService *-- SlurmDeployer : uses
    ServerService *-- ServiceManager : uses (singleton)
    ServerService *-- RecipeLoader : uses
    ServerService *-- EndpointResolver : uses

    SlurmDeployer --> SSHManager : uses
    EndpointResolver --> SlurmDeployer : queries job details
    EndpointResolver --> ServiceManager : reads service metadata
    EndpointResolver --> RecipeLoader : reads recipe port

    BaseService <|-- InferenceService
    BaseService <|-- VectorDbService
    InferenceService <|-- VllmService
    VectorDbService <|-- QdrantService

    VllmService --> EndpointResolver : resolves endpoints
    QdrantService --> EndpointResolver : resolves endpoints
    VllmService --> SlurmDeployer : checks job status / logs
    QdrantService --> SlurmDeployer : checks job status / logs

    ServiceManager <.. ServerService : registers services

    %% Notes as a class-like annotation for readers
    class Notes {
        +"Service IDs = SLURM job IDs"
        +"SSH tunnel used to reach SLURM REST API and compute nodes"
    }

    Notes ..> SlurmDeployer

```

### Legend & Rendering

- Solid arrow (A --> B): A calls or depends on B
- Composition (A *-- B): A composes/owns B instance
- Inheritance (A <|-- B): B extends A

To render this diagram in the docs site ensure the MkDocs configuration (or your viewer) supports Mermaid diagrams (mkdocs-mermaid2-plugin or built-in Mermaid support in MkDocs Material). The diagram can be previewed in editors that support Mermaid or on GitHub when Mermaid rendering is enabled.


## Further Reading

- [Service Recipes](recipes.md) - Available service templates
- [Architecture](../architecture/overview.md) - System design
- [Development Guide](../development/guidelines.md) - API development

---
