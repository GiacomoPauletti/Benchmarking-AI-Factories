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
- SlurmDeployer is responsible for job lifecycle (submit/cancel/status) and relies on SSHManager for remote operations (tunnels, fetching logs, proxy HTTP calls to compute nodes).

When tracing a "create service" request, follow the path: FastAPIApp -> APIRouter -> ServerService -> SlurmDeployer (+ SSHManager). Endpoint resolution happens later via EndpointResolver which queries SLURM job details and recipe metadata.

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

## Further Reading

The service-handlers diagram explains how domain-specific functionality is organized:

- `BaseService` provides the shared plumbing (deployer access, service registry, endpoint resolution) used by concrete handlers.
- `InferenceService` and `VectorDbService` define the operations expected by their domains; `VllmService` and `QdrantService` implement those operations against running jobs.
- These handlers consult `SlurmDeployer` for live job state and `EndpointResolver` to discover the compute-node HTTP endpoints used to reach the actual running services.

Refer to this diagram when extending the system with a new service type (create a subclass of `BaseService` and implement the domain-specific API surface).

## Further Reading

- [Service Recipes](recipes.md) - Available service templates
- [Architecture](../architecture/overview.md) - System design
- [Development Guide](../development/guidelines.md) - API development

---
