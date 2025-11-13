"""
API route definitions for SLURM-based service orchestration.
"""

from fastapi import APIRouter, HTTPException, Body, Depends, Query
from typing import List, Dict, Any, Optional

from server_service import ServerService
from api.schemas import ServiceRequest, ServiceResponse, RecipeResponse
from api.metrics_proxy import router as metrics_router
from services.inference.vllm_models_config import (
    get_architecture_info,
    search_hf_models,
    get_model_info as get_hf_model_info,
)

router = APIRouter()

# Include metrics proxy routes
router.include_router(metrics_router)

# Singleton instance of ServerService (created once, reused for all requests)
_server_service_instance = None

def get_server_service() -> ServerService:
    """Dependency function to get the singleton ServerService instance."""
    global _server_service_instance
    if _server_service_instance is None:
        _server_service_instance = ServerService()
    return _server_service_instance


@router.post("/services", response_model=ServiceResponse, summary="Create and start a new service")
async def create_service(
    request: ServiceRequest = Body(...,
        examples={
            "simple": {
                "summary": "Create a basic vLLM service",
                "value": {"recipe_name": "inference/vllm-single-node", "config": {"nodes": 1, "cpus": 2, "memory": "8G", "time": "00:30:00"}}
            }
        }
    ),
    server_service: ServerService = Depends(get_server_service)
):
    """Create and start a new service using SLURM + Apptainer.

    This endpoint submits a job to the SLURM cluster using a predefined recipe template.
    The service will be containerized using Apptainer and scheduled on compute nodes.

    **Request Body:**
    - `recipe_name` (required): Path to the recipe (e.g., "inference/vllm-single-node", "inference/vllm_dummy")
    - `config` (optional): Configuration object with:
        - **SLURM resource requirements** (all optional, override recipe defaults):
            - `nodes`: Number of compute nodes (default: 1)
            - `resources`: Resource overrides object:
                - `cpu`: Number of CPUs (e.g., "2", "8")
                - `memory`: Memory per CPU (e.g., "8G", "16G", "32G")
                - `time_limit`: Time limit in minutes (e.g., 15, 60, 120)
                - `gpu`: GPU allocation (e.g., "1", "2", null for CPU-only)
        - **Environment variables** (all optional, override recipe defaults):
            - `environment`: Environment variable overrides:
                - `VLLM_MODEL`: Model to load (e.g., "gpt2", "Qwen/Qwen2.5-0.5B-Instruct")
                - `VLLM_MAX_MODEL_LEN`: Max sequence length
                - `VLLM_GPU_MEMORY_UTILIZATION`: GPU memory fraction (0.0-1.0)
                - Any other environment variables supported by the container

    **Examples:**

    Simple creation with defaults:
    ```json
    {
      "recipe_name": "inference/vllm-single-node"
    }
    ```

    Custom model:
    ```json
    {
      "recipe_name": "inference/vllm-single-node",
      "config": {
        "environment": {
          "VLLM_MODEL": "gpt2"
        }
      }
    }
    ```

    Custom model + resources:
    ```json
    {
      "recipe_name": "inference/vllm-single-node",
      "config": {
        "nodes": 1,
        "environment": {
          "VLLM_MODEL": "meta-llama/Llama-2-7b-chat-hf"
        },
        "resources": {
          "cpu": "8",
          "memory": "64G",
          "time_limit": 120,
          "gpu": "1"
        }
      }
    }
    ```

    **Returns:**
    - Service object with `id` (SLURM job ID), `name`, `status`, `recipe_name`, `config`, and `created_at`

    **Status Values:**
    - `pending`: Job queued in SLURM
    - `building`: Apptainer container image being built
    - `starting`: Container started, application initializing
    - `running`: Service fully operational and ready
    - `completed`: Service finished successfully
    - `failed`: Service encountered an error
    - `cancelled`: Service was stopped by user
    """
    try:
        service = server_service.start_service(
            recipe_name=request.recipe_name,
            config=request.config
        )
        return service
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services", response_model=List[ServiceResponse])
async def list_services(server_service: ServerService = Depends(get_server_service)):
    """List all services managed by this server.

    Returns all services that were started through this API. Does not include
    unrelated SLURM jobs (e.g., interactive sessions, other users' jobs).

    **Returns:**
    - Array of service objects, each containing:
        - `id`: SLURM job ID (used as service identifier)
        - `name`: Service name (derived from recipe)
        - `status`: Current status (pending/building/starting/running/completed/failed/cancelled)
        - `recipe_name`: Recipe used to create the service
        - `config`: Resource configuration (nodes, cpus, memory, time, etc.)
        - `created_at`: Service creation timestamp

    **Example Response:**
    ```json
    [
      {
        "id": "3642874",
        "name": "vllm-service",
        "status": "running",
        "recipe_name": "inference/vllm-single-node",
        "config": {"nodes": 1, "cpus": 4, "memory": "16G"},
        "created_at": "2025-10-14T10:30:00"
      }
    ]
    ```
    """
    services = server_service.list_running_services()
    return services


@router.get("/services/targets")
async def get_service_targets(server_service: ServerService = Depends(get_server_service)):
    """Get Prometheus scrape targets for all managed services.

    This endpoint returns a list of Prometheus scrape targets for running services.
    This allows to dynamically configure Prometheus to monitor all services managed by this server.

    **Returns:**
    - Content-Type: `application/json`
    - Body: JSON object compatible with Prometheus file-based service discovery format

    **Example Response:**
    ```json
    [
      {
        "targets": ["server:8001"],
        "labels": {
          "job": "service-3642874",
          "service_id": "3642874",
          "recipe_name": "inference/vllm-single-node"
        }
      },
      ...
    ]
    ```
    """
    try:
        targets = []
        for service in server_service.list_running_services():
            service_id = service["id"]
            targets.append({
                "targets": [service_id],
                "labels": {
                    "job": f"service-{service_id}",
                    "service_id": service_id,
                    "recipe_name": service["recipe_name"],
                    "status": service["status"],
                }
            })
        return targets
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/{service_id}", response_model=ServiceResponse)
async def get_service(service_id: str, server_service: ServerService = Depends(get_server_service)):
    """Get detailed information about a specific service.

    **Path Parameters:**
    - `service_id`: The SLURM job ID of the service (obtained from create_service or list_services)

    **Returns:**
    - Service object with current status and configuration details

    **Errors:**
    - 404: Service not found (not managed by this server)

    **Example:**
    - GET `/api/v1/services/3642874`
    """
    service = server_service.get_service(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.get("/service-groups")
async def list_service_groups(server_service: ServerService = Depends(get_server_service)):
    """List all service groups.

    Returns summary information for all service groups (collections of replicas).

    **Returns:**
    ```json
    [
      {
        "id": "sg-ba5f6e2462fb",
        "type": "replica_group",
        "recipe_name": "inference/vllm-replicas",
        "total_replicas": 4,
        "healthy_replicas": 3,
        "starting_replicas": 1,
        "pending_replicas": 0,
        "failed_replicas": 0,
        "created_at": "2025-11-10T12:00:00"
      },
      ...
    ]
    ```

    **Example:**
    - GET `/api/v1/service-groups`
    """
    try:
        groups = server_service.list_service_groups()
        return groups
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service-groups/{group_id}")
async def get_service_group(group_id: str, server_service: ServerService = Depends(get_server_service)):
    """Get detailed information about a service group and all its replicas.

    Service groups are collections of replica services that share a common group_id.
    This endpoint aggregates information from all replicas in the group.

    **Path Parameters:**
    - `group_id`: The service group ID (e.g., "sg-ba5f6e2462fb")

    **Returns:**
    ```json
    {
      "id": "sg-ba5f6e2462fb",
      "type": "replica_group",
      "replicas": [
        {
          "id": "3713894:8001",
          "name": "vllm-replicas-3713894-replica-0",
          "status": "running",
          "port": 8001,
          "gpu_id": 0,
          "replica_index": 0,
          "job_id": "3713894"
        },
        ...
      ],
      "total_replicas": 4,
      "healthy_replicas": 3,
      "starting_replicas": 1,
      "failed_replicas": 0,
      "recipe_name": "inference/vllm-replicas",
      "base_port": 8001,
      "node_jobs": [
        {
          "job_id": "3713894",
          "node_index": 0,
          "replicas": [...]
        }
      ]
    }
    ```

    **Errors:**
    - 404: Service group not found (no services with this group_id)

    **Example:**
    - GET `/api/v1/service-groups/sg-ba5f6e2462fb`
    """
    try:
        group_info = server_service.get_service_group(group_id)
        if not group_info:
            raise HTTPException(status_code=404, detail=f"Service group '{group_id}' not found")
        return group_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/service-groups/{group_id}")
async def stop_service_group(group_id: str, server_service: ServerService = Depends(get_server_service)):
    """Stop all replicas in a service group.

    This endpoint cancels all SLURM jobs associated with the service group,
    stopping all replicas at once.

    **Path Parameters:**
    - `group_id`: The service group ID (e.g., "sg-ba5f6e2462fb")

    **Returns:**
    ```json
    {
      "message": "Service group sg-ba5f6e2462fb stopped successfully",
      "group_id": "sg-ba5f6e2462fb",
      "replicas_stopped": 4
    }
    ```

    **Errors:**
    - 404: Service group not found
    - 500: Failed to stop one or more replicas

    **Example:**
    - DELETE `/api/v1/service-groups/sg-ba5f6e2462fb`

    **Note:** This operation stops all replicas in the group. Individual replicas
    cannot be stopped separately - the entire group is managed as a unit.
    """
    try:
        result = server_service.stop_service_group(group_id)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Service group not found"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service-groups/{group_id}/status")
async def get_service_group_status(group_id: str, server_service: ServerService = Depends(get_server_service)):
    """Get aggregated status of a service group.

    Returns a summary of the group's overall health and replica statuses.

    **Path Parameters:**
    - `group_id`: The service group ID (e.g., "sg-ba5f6e2462fb")

    **Returns:**
    ```json
    {
      "group_id": "sg-ba5f6e2462fb",
      "overall_status": "healthy",
      "total_replicas": 4,
      "healthy_replicas": 4,
      "starting_replicas": 0,
      "pending_replicas": 0,
      "failed_replicas": 0,
      "replica_statuses": [
        {"id": "3713894:8001", "status": "running"},
        {"id": "3713894:8002", "status": "running"},
        ...
      ]
    }
    ```

    **Overall Status Values:**
    - `healthy`: All replicas are running
    - `partial`: Some replicas are running, others are starting/pending
    - `starting`: All replicas are starting or pending
    - `failed`: All replicas have failed
    - `degraded`: Some replicas have failed, others are running

    **Errors:**
    - 404: Service group not found

    **Example:**
    - GET `/api/v1/service-groups/sg-ba5f6e2462fb/status`
    """
    try:
        status_info = server_service.get_service_group_status(group_id)
        if not status_info:
            raise HTTPException(status_code=404, detail=f"Service group '{group_id}' not found")
        return status_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/{service_id}/metrics")
async def get_service_metrics(service_id: str, server_service: ServerService = Depends(get_server_service)):
    """Get Prometheus-compatible metrics from any service (generic endpoint).
    
    This is a unified metrics endpoint that automatically routes to the appropriate
    service-specific metrics endpoint based on the service's recipe type.
    
    Supported service types:
    - vLLM inference services (recipe: "inference/vllm*")
    - Qdrant vector database (recipe: "vector-db/qdrant")
    - Other vector databases (recipe: "vector-db/*")
    
    **Path Parameters:**
    - `service_id`: The SLURM job ID of the service
    
    **Returns (Success):**
    - Content-Type: `text/plain; version=0.0.4`
    - Body: Prometheus text format metrics
    
    **Returns (Error):**
    - Content-Type: `application/json`
    - Body: JSON error object with details
    
    **Examples:**
    ```bash
    # Get metrics from a service
    curl http://localhost:8001/api/v1/services/3642874/metrics
    ```
    
    **Integration with Prometheus:**
    This endpoint provides a consistent interface for monitoring, regardless of service type.
    Simply use `/api/v1/services/{service_id}/metrics` for all services.
    
    ```yaml
    scrape_configs:
      - job_name: 'managed-services'
        static_configs:
          - targets: ['server:8001']
        metrics_path: '/api/v1/services/<service_id>/metrics'
        scrape_interval: 15s
    ```
    
    **Note:** This endpoint determines the service type from the recipe_name and routes
    to the appropriate service-specific metrics endpoint (vLLM, Qdrant, etc.).
    """
    from fastapi.responses import PlainTextResponse
    
    try:
        # Get service details to determine recipe type
        service = server_service.get_service(service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        
        recipe_name = service.get("recipe_name", "")
        
        # Route to appropriate service-specific metrics endpoint
        if recipe_name.startswith("inference/vllm"):
            result = server_service.get_vllm_metrics(service_id)
        elif recipe_name.startswith("vector-db/qdrant"):
            result = server_service.get_qdrant_metrics(service_id)
        else:
            # Unknown service type
            raise HTTPException(
                status_code=400,
                detail=f"Metrics not available for service type: {recipe_name}"
            )
        
        # If successful, return metrics as plain text
        if result.get("success"):
            return PlainTextResponse(
                content=result.get("metrics", ""),
                media_type="text/plain; version=0.0.4"
            )
        else:
            # Return error as JSON
            return result
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/services/{service_id}")
async def stop_service(service_id: str, server_service: ServerService = Depends(get_server_service)):
    """DEPRECATED: Use POST /api/v1/services/{service_id}/status instead.
    
    Stop a running service by cancelling its SLURM job.

    **DEPRECATION NOTICE:** This endpoint is deprecated in favor of the POST endpoint which
    better preserves service metadata for post-mortem analysis and Grafana integration.
    Use `POST /api/v1/services/{service_id}/status` with `{"status": "cancelled"}` instead.

    This endpoint cancels the SLURM job associated with the service, which will:
    1. Terminate the running container
    2. Free up allocated compute resources
    3. Mark the service as cancelled in SLURM

    **Path Parameters:**
    - `service_id`: The SLURM job ID of the service to stop

    **Returns:**
    - Success message with service ID

    **Errors:**
    - 404: Service not found or already stopped

    **Example (DEPRECATED):**
    - DELETE `/api/v1/services/3642874`
    
    **Recommended Alternative:**
    ```bash
    curl -X POST http://localhost:8001/api/v1/services/3642874/status \\
      -H "Content-Type: application/json" \\
      -d '{"status": "cancelled"}'
    ```

    **Note:** This operation is immediate and cannot be undone. The service will be terminated gracefully.
    """
    success = server_service.stop_service(service_id)
    if success:
        return {"message": f"Service {service_id} stopped successfully"}
    else:
        raise HTTPException(status_code=404, detail="Service not found or failed to stop")


@router.get("/services/{service_id}/logs")
async def get_service_logs(service_id: str, server_service: ServerService = Depends(get_server_service)):
    """Get SLURM logs (stdout and stderr) from a service.

    Retrieves the job output logs written by SLURM. These logs contain:
    - Container build output (if applicable)
    - Application startup messages
    - Runtime logs and errors
    - Container termination information

    **Path Parameters:**
    - `service_id`: The SLURM job ID of the service

    **Returns:**
    - Object with `logs` field containing the combined stdout/stderr output

    **Example Response:**
    ```json
    {
      "logs": "=== SLURM STDOUT ===\\nBuilding Apptainer image...\\nStarting container...\\nApplication startup complete."
    }
    ```

    **Note:** Logs may not be available immediately after job creation. They become available once the job starts running.
    """
    return server_service.get_service_logs(service_id)


@router.get("/services/{service_id}/status")
async def get_service_status(service_id: str, server_service: ServerService = Depends(get_server_service)):
    """Get the current detailed status of a service.

    This endpoint returns the real-time status by checking both SLURM state and parsing log files
    to determine the exact stage of service initialization.

    **Path Parameters:**
    - `service_id`: The SLURM job ID of the service

    **Returns:**
    - Object with `status` field containing one of:
        - `pending`: Job waiting in SLURM queue
        - `building`: Apptainer container image being built
        - `starting`: Container launched, application initializing
        - `running`: Service fully operational
        - `completed`: Service finished successfully
        - `failed`: Service encountered an error
        - `cancelled`: Service was stopped
        - `unknown`: Unable to determine status

    **Example Response:**
    ```json
    {
      "status": "running"
    }
    ```
    """
    return server_service.get_service_status(service_id)


@router.post("/services/{service_id}/status")
async def update_service_status(
    service_id: str,
    status_update: Dict[str, str] = Body(..., examples={
        "cancel": {
            "summary": "Cancel a running service",
            "value": {"status": "cancelled"}
        }
    }),
    server_service: ServerService = Depends(get_server_service)
):
    """Update the status of a service (primarily for cancelling).

    This endpoint allows updating a service's status. Currently supports cancelling services
    by setting status to "cancelled", which stops the SLURM job and frees compute resources.
    Service metadata and logs are preserved for post-mortem analysis.

    **Path Parameters:**
    - `service_id`: The SLURM job ID of the service

    **Request Body:**
    - `status`: New status to set. Supported values:
        - `"cancelled"`: Cancel the running SLURM job

    **Returns:**
    - Success message with service ID and new status

    **Errors:**
    - 400: Invalid status value
    - 404: Service not found or failed to update
    - 500: Error during status update

    **Example Request:**
    ```bash
    curl -X POST http://localhost:8001/api/v1/services/3642874/status \\
      -H "Content-Type: application/json" \\
      -d '{"status": "cancelled"}'
    ```

    **Example Response:**
    ```json
    {
      "message": "Service 3642874 status updated to cancelled",
      "service_id": "3642874",
      "status": "cancelled"
    }
    ```

    **Note:** This is the recommended way to stop services (instead of DELETE) as it preserves
    service records for logging and post-mortem analysis, which is essential for Grafana integration.
    """
    new_status = status_update.get("status")
    
    if not new_status:
        raise HTTPException(status_code=400, detail="Missing 'status' field in request body")
    
    # Currently only support cancelling services
    if new_status == "cancelled":
        success = server_service.stop_service(service_id)
        if success:
            # Update the service status in the service manager
            server_service.service_manager.update_service_status(service_id, "cancelled")
            return {
                "message": f"Service {service_id} status updated to {new_status}",
                "service_id": service_id,
                "status": new_status
            }
        else:
            raise HTTPException(status_code=404, detail="Service not found or failed to stop")
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported status value: '{new_status}'. Currently only 'cancelled' is supported."
        )


@router.get("/recipes")
async def list_or_get_recipe(
    path: Optional[str] = None,
    name: Optional[str] = None,
    server_service: ServerService = Depends(get_server_service)
):
    """List all available recipes OR get a specific recipe by path/name.

    **Behavior:**
    - Without query parameters: Returns list of all available recipes
    - With `path` or `name`: Returns a single matching recipe

    **Query Parameters (Optional):**
    - `path`: Recipe path (e.g., "inference/vllm-single-node", "vector-db/qdrant")
    - `name`: Recipe display name (e.g., "vLLM Inference Service")

    **Returns:**
    - If no parameters: Array of all recipe objects
    - If path/name specified: Single recipe object

    **Errors:**
    - 404: Recipe not found (when path/name specified)

    **Examples:**
    - List all: `GET /api/v1/recipes`
    - Get by path: `GET /api/v1/recipes?path=inference/vllm`
    - Get by path: `GET /api/v1/recipes?path=vector-db/qdrant`
    - Get by name: `GET /api/v1/recipes?name=vLLM%20Inference%20Service`

    **Recipe Object Fields:**
    - `name`: Recipe display name
    - `category`: Category (inference, storage, vector-db, etc.)
    - `description`: Human-readable description
    - `version`: Recipe version
    - `path`: Path identifier (e.g., "inference/vllm-single-node")
    """
    recipes = server_service.list_available_recipes()
    
    # If no search criteria provided, return all recipes
    if not path and not name:
        return recipes
    
    # Otherwise, find specific recipe by path or name
    recipe = None
    for r in recipes:
        if (path and r.get("path") == path) or (name and r.get("name") == name):
            recipe = r
            break
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.get("/vllm/services")
async def list_vllm_services(server_service: ServerService = Depends(get_server_service)):
    """List all running vLLM inference services with their endpoints.

    This endpoint discovers vLLM services among all running services and resolves their network endpoints.
    Use this to find available vLLM instances for inference requests.

    **Returns:**
    - Object with `vllm_services` array, each service containing:
        - `id`: SLURM job ID (service identifier)
        - `name`: Service name
        - `recipe_name`: Recipe used (typically "inference/vllm-single-node")
        - `endpoint`: HTTP endpoint URL (e.g., "http://mel2133:8001")
        - `status`: Current status (building/starting/running)

    **Example Response:**
    ```json
    {
      "vllm_services": [
        {
          "id": "3642874",
          "name": "vllm-service",
          "recipe_name": "inference/vllm-single-node",
          "endpoint": "http://mel2133:8001",
          "status": "running"
        }
      ]
    }
    ```

    **Status Meanings:**
    - `building`: Container image being built
    - `starting`: vLLM server initializing, not ready for requests
    - `running`: vLLM fully loaded and ready to serve inference requests

    **Note:** Only services with status "running" are ready to accept prompt requests.
    """
    try:
        vllm_services = server_service.find_vllm_services()
        return {"vllm_services": vllm_services}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/available-models")
async def list_available_vllm_models():
    """Get information about models that can be used with vLLM.

    This endpoint provides information about vLLM's supported model architectures
    and how to find compatible models from HuggingFace Hub. Unlike a hardcoded model list,
    this returns architectural compatibility information since vLLM can load ANY model
    from HuggingFace Hub that uses a supported architecture.

    **Key Information:**
    - **Model Source**: All models are downloaded from HuggingFace Hub (https://huggingface.co/models)
    - **Compatibility**: Based on model architecture, not specific model names
    - **How to Use**: Provide any HuggingFace model ID in the `VLLM_MODEL` environment variable
    - **Format**: `organization/model-name` (e.g., `meta-llama/Llama-2-7b-chat-hf`)

    **Returns:**
    ```json
    {
      "model_source": "HuggingFace Hub",
      "supported_architectures": {
        "text-generation": ["LlamaForCausalLM", "MistralForCausalLM", ...],
        "vision-language": ["LlavaForConditionalGeneration", ...],
        "embedding": ["BertModel", ...]
      },
      "examples": {
        "GPT-2 (small, for testing)": "gpt2",
        "Llama 2 7B Chat": "meta-llama/Llama-2-7b-chat-hf",
        "Qwen 2.5 0.5B Instruct": "Qwen/Qwen2.5-0.5B-Instruct",
        ...
      },
      "how_to_find_models": [
        "Browse HuggingFace: https://huggingface.co/models?pipeline_tag=text-generation",
        "Check model card for architecture",
        ...
      ],
      "resource_guidelines": {
        "small_models": {
          "size_range": "< 1B parameters",
          "min_gpu_memory_gb": 4,
          ...
        },
        ...
      }
    }
    ```

    **How to Find Compatible Models:**
    1. Browse HuggingFace: https://huggingface.co/models?pipeline_tag=text-generation
    2. Check the model's architecture in its `config.json` file
    3. Verify the architecture is in vLLM's supported list (returned by this endpoint)
    4. Use the model ID when creating a vLLM service

    **Example Usage:**

    First, query this endpoint to see supported architectures and examples:
    ```bash
    curl http://localhost:8001/vllm/available-models
    ```

    Then create a service with any compatible model:
    ```json
    {
      "recipe_name": "inference/vllm-single-node",
      "config": {
        "environment": {
          "VLLM_MODEL": "Qwen/Qwen2.5-7B-Instruct"
        }
      }
    }
    ```

    **Resource Planning:**
    Use the `resource_guidelines` section to estimate GPU memory requirements based on model size.
    Larger models may require multiple GPUs using tensor parallelism.

    **Authentication:**
    Some models (e.g., Llama 2, Llama 3) require HuggingFace authentication.
    You'll need to set up HuggingFace credentials before deploying these models.
    """
    try:
        info = get_architecture_info()
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/search-models")
async def search_vllm_models(
    query: Optional[str] = Query(None, description="Search query (e.g., 'llama', 'mistral', 'qwen')"),
    architecture: Optional[str] = Query(None, description="Filter by architecture (e.g., 'LlamaForCausalLM')"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results (1-100)"),
    sort_by: str = Query("downloads", description="Sort by: downloads, likes, trending, created_at")
):
    """Search HuggingFace Hub for models compatible with vLLM.

    This endpoint queries the HuggingFace Hub API to find models that match your search criteria
    and checks their compatibility with vLLM's supported architectures.

    **Query Parameters:**
    - `query`: Search string (e.g., "llama", "mistral", "qwen", "instruct")
    - `architecture`: Filter by specific architecture class name
    - `limit`: Maximum results to return (1-100, default: 20)
    - `sort_by`: Sort order - "downloads", "likes", "trending", or "created_at"

    **Returns:**
    ```json
    {
      "models": [
        {
          "id": "meta-llama/Llama-2-7b-chat-hf",
          "downloads": 1500000,
          "likes": 5000,
          "architecture": "LlamaForCausalLM",
          "vllm_compatible": true,
          "created_at": "2023-07-18T...",
          "tags": ["llama", "text-generation", "conversational"]
        },
        ...
      ],
      "total": 20
    }
    ```

    **Example Searches:**

    Find popular Llama models:
    ```
    GET /vllm/search-models?query=llama&sort_by=downloads&limit=10
    ```

    Find Qwen instruction models:
    ```
    GET /vllm/search-models?query=qwen+instruct&limit=15
    ```

    Find all models with specific architecture:
    ```
    GET /vllm/search-models?architecture=MistralForCausalLM
    ```

    **Use Case:**
    Use this to discover new models before creating a vLLM service. The `vllm_compatible`
    field indicates whether the model uses an architecture supported by vLLM.
    """
    try:
        models = search_hf_models(
            query=query,
            architecture=architecture,
            limit=limit,
            sort_by=sort_by
        )
        return {
            "models": models,
            "total": len(models)
        }
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/model-info/{model_id:path}")
async def get_model_info(model_id: str):
    """Get detailed information about a specific model from HuggingFace Hub.

    This endpoint fetches comprehensive information about a model including its architecture,
    size, compatibility with vLLM, and download statistics.

    **Path Parameters:**
    - `model_id`: HuggingFace model ID (e.g., "meta-llama/Llama-2-7b-hf", "Qwen/Qwen2.5-3B-Instruct")

    **Returns:**
    ```json
    {
      "id": "Qwen/Qwen2.5-3B-Instruct",
      "architecture": "Qwen2ForCausalLM",
      "vllm_compatible": true,
      "task_type": "text-generation",
      "downloads": 250000,
      "likes": 1200,
      "tags": ["qwen2", "instruct", "chat"],
      "size_bytes": 6442450944,
      "size_gb": 6.0,
      "pipeline_tag": "text-generation",
      "library_name": "transformers"
    }
    ```

    **Fields:**
    - `vllm_compatible`: Whether this model can be loaded by vLLM
    - `task_type`: Type of task (text-generation, vision-language, embedding)
    - `size_gb`: Approximate model size in gigabytes
    - `architecture`: The model's architecture class

    **Example Usage:**

    Check if a model is compatible before deployment:
    ```bash
    curl http://localhost:8001/vllm/model-info/Qwen/Qwen2.5-7B-Instruct
    ```

    Then use the model ID to create a service:
    ```json
    {
      "recipe_name": "inference/vllm-single-node",
      "config": {
        "environment": {
          "VLLM_MODEL": "Qwen/Qwen2.5-7B-Instruct"
        }
      }
    }
    ```

    **Note:** Some models require HuggingFace authentication. Check the model page on
    HuggingFace Hub if you encounter access errors.
    """
    try:
        model_info = get_hf_model_info(model_id)
        return model_info
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )
    except Exception as e:
        # Could be 404 if model doesn't exist, or other HF API errors
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found or error accessing HuggingFace Hub: {str(e)}"
        )


@router.get("/vector-db/services")
async def list_vector_db_services(server_service: ServerService = Depends(get_server_service)):
    """List all running vector database services.

    Returns a list of vector database services (Qdrant, Chroma, etc.) with their endpoints.

    **Example Response:**
    ```json
    {
      "vector_db_services": [
        {
          "id": "3642875",
          "name": "qdrant-service",
          "recipe_name": "vector-db/qdrant",
          "endpoint": "http://mel2079:6333",
          "status": "running"
        }
      ]
    }
    ```
    """
    try:
        vector_db_services = server_service.find_vector_db_services()
        return {"vector_db_services": vector_db_services}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector-db/{service_id}/collections")
async def get_collections(service_id: str, server_service: ServerService = Depends(get_server_service)):
    """Get list of collections from a vector database service.

    **Path Parameters:**
    - `service_id`: SLURM job ID of the vector DB service

    **Returns (Success):**
    ```json
    {
      "success": true,
      "collections": ["my_documents", "embeddings"],
      "service_id": "3642875",
      "endpoint": "http://mel2079:6333"
    }
    ```

    **Returns (Service Not Ready):**
    ```json
    {
      "success": false,
      "error": "Service is not ready yet (status: starting)",
      "message": "The vector DB service is still starting up. Please wait.",
      "collections": []
    }
    ```
    """
    try:
        result = server_service.get_collections(service_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector-db/{service_id}/collections/{collection_name}")
async def get_collection_info(
    service_id: str,
    collection_name: str,
    server_service: ServerService = Depends(get_server_service)
):
    """Get detailed information about a specific collection.

    **Path Parameters:**
    - `service_id`: SLURM job ID of the vector DB service
    - `collection_name`: Name of the collection

    **Returns (Success):**
    ```json
    {
      "success": true,
      "collection_info": {
        "status": "green",
        "vectors_count": 1000,
        "indexed_vectors_count": 1000,
        "config": {
          "params": {
            "vectors": {
              "size": 384,
              "distance": "Cosine"
            }
          }
        }
      },
      "service_id": "3642875",
      "collection_name": "my_documents"
    }
    ```
    """
    try:
        result = server_service.get_collection_info(service_id, collection_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/vector-db/{service_id}/collections/{collection_name}")
async def create_collection(
    service_id: str,
    collection_name: str,
    request: Dict[str, Any] = Body(..., examples={
        "basic": {
            "summary": "Create a basic collection",
            "value": {"vector_size": 384, "distance": "Cosine"}
        },
        "euclidean": {
            "summary": "Create collection with Euclidean distance",
            "value": {"vector_size": 768, "distance": "Euclid"}
        }
    }),
    server_service: ServerService = Depends(get_server_service)
):
    """Create a new collection in the vector database.

    **Path Parameters:**
    - `service_id`: SLURM job ID of the vector DB service
    - `collection_name`: Name for the new collection

    **Request Body:**
    - `vector_size` (required): Dimension of vectors (e.g., 384, 768, 1536)
    - `distance` (optional): Distance metric - "Cosine" (default), "Euclid", or "Dot"

    **Returns (Success):**
    ```json
    {
      "success": true,
      "message": "Collection 'my_documents' created successfully",
      "collection_name": "my_documents",
      "vector_size": 384,
      "distance": "Cosine"
    }
    ```

    **Example:**
    ```bash
    curl -X PUT "http://localhost:8001/api/v1/vector-db/3642875/collections/my_docs" \\
      -H "Content-Type: application/json" \\
      -d '{"vector_size": 384, "distance": "Cosine"}'
    ```
    """
    try:
        vector_size = request.get("vector_size")
        if not vector_size:
            raise HTTPException(status_code=400, detail="vector_size is required")
        
        distance = request.get("distance", "Cosine")
        result = server_service.create_collection(service_id, collection_name, vector_size, distance)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/vector-db/{service_id}/collections/{collection_name}")
async def delete_collection(
    service_id: str,
    collection_name: str,
    server_service: ServerService = Depends(get_server_service)
):
    """Delete a collection from the vector database.

    **Path Parameters:**
    - `service_id`: SLURM job ID of the vector DB service
    - `collection_name`: Name of the collection to delete

    **Returns (Success):**
    ```json
    {
      "success": true,
      "message": "Collection 'my_documents' deleted successfully",
      "collection_name": "my_documents"
    }
    ```

    **Example:**
    ```bash
    curl -X DELETE "http://localhost:8001/api/v1/vector-db/3642875/collections/my_docs"
    ```
    """
    try:
        result = server_service.delete_collection(service_id, collection_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/vector-db/{service_id}/collections/{collection_name}/points")
async def upsert_points(
    service_id: str,
    collection_name: str,
    request: Dict[str, Any] = Body(..., examples={
        "simple": {
            "summary": "Insert a single point",
            "value": {
                "points": [
                    {
                        "id": 1,
                        "vector": [0.1, 0.2, 0.3, 0.4],
                        "payload": {"text": "Example document"}
                    }
                ]
            }
        },
        "multiple": {
            "summary": "Insert multiple points",
            "value": {
                "points": [
                    {"id": 1, "vector": [0.1, 0.2, 0.3], "payload": {"text": "First doc"}},
                    {"id": 2, "vector": [0.4, 0.5, 0.6], "payload": {"text": "Second doc"}}
                ]
            }
        }
    }),
    server_service: ServerService = Depends(get_server_service)
):
    """Insert or update points (vectors with payloads) in a collection.

    **Path Parameters:**
    - `service_id`: SLURM job ID of the vector DB service
    - `collection_name`: Name of the collection

    **Request Body:**
    - `points` (required): List of points to upsert
      - Each point must have: `id`, `vector`, and optional `payload`

    **Returns (Success):**
    ```json
    {
      "success": true,
      "message": "Upserted 2 points to collection 'my_documents'",
      "num_points": 2
    }
    ```

    **Example:**
    ```bash
    curl -X PUT "http://localhost:8001/api/v1/vector-db/3642875/collections/my_docs/points" \\
      -H "Content-Type: application/json" \\
      -d '{
        "points": [
          {"id": 1, "vector": [0.1, 0.2, 0.3], "payload": {"text": "Hello world"}}
        ]
      }'
    ```
    """
    try:
        points = request.get("points")
        if not points or not isinstance(points, list):
            raise HTTPException(status_code=400, detail="points must be a non-empty list")
        
        result = server_service.upsert_points(service_id, collection_name, points)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vector-db/{service_id}/collections/{collection_name}/points/search")
async def search_points(
    service_id: str,
    collection_name: str,
    request: Dict[str, Any] = Body(..., examples={
        "basic": {
            "summary": "Basic similarity search",
            "value": {
                "query_vector": [0.1, 0.2, 0.3, 0.4],
                "limit": 5
            }
        }
    }),
    server_service: ServerService = Depends(get_server_service)
):
    """Search for similar vectors in a collection.

    **Path Parameters:**
    - `service_id`: SLURM job ID of the vector DB service
    - `collection_name`: Name of the collection to search

    **Request Body:**
    - `query_vector` (required): The query vector to find similar items
    - `limit` (optional): Maximum number of results (default: 10)

    **Returns (Success):**
    ```json
    {
      "success": true,
      "results": [
        {
          "id": 1,
          "score": 0.95,
          "payload": {"text": "Similar document"}
        }
      ],
      "num_results": 1
    }
    ```

    **Example:**
    ```bash
    curl -X POST "http://localhost:8001/api/v1/vector-db/3642875/collections/my_docs/points/search" \\
      -H "Content-Type: application/json" \\
      -d '{
        "query_vector": [0.1, 0.2, 0.3],
        "limit": 5
      }'
    ```
    """
    try:
        query_vector = request.get("query_vector")
        if not query_vector or not isinstance(query_vector, list):
            raise HTTPException(status_code=400, detail="query_vector must be a non-empty list")
        
        limit = request.get("limit", 10)
        result = server_service.search_points(service_id, collection_name, query_vector, limit)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/vllm/{service_id}/prompt", summary="Send a prompt to a running vLLM service")
async def prompt_vllm_service(
    service_id: str,
    request: Dict[str, Any] = Body(..., examples={
        "simple": {
            "summary": "Basic prompt",
            "value": {"prompt": "Write a short haiku about AI."}
        },
        "with_model": {
            "summary": "Prompt specifying model",
            "value": {"prompt": "Hello", "model": "gpt2", "max_tokens": 64}
        }
    }),
    server_service: ServerService = Depends(get_server_service)
):
    """Send a text prompt to a running vLLM inference service and get a response.

    This endpoint forwards your prompt to the vLLM service using the OpenAI-compatible API.
    The vLLM service must be in "running" status (not "building" or "starting").

    **Path Parameters:**
    - `service_id`: SLURM job ID of the vLLM service (from list_vllm_services)

    **Request Body:**
    - `prompt` (required): Text prompt to send to the model
    - `model` (optional): Model identifier (auto-discovered if omitted)
    - `max_tokens` (optional): Maximum tokens to generate (default: 150)
    - `temperature` (optional): Sampling temperature 0.0-2.0 (default: 0.7)

    **Returns (Success):**
    ```json
    {
      "success": true,
      "response": "Generated text response from the model...",
      "service_id": "3642874",
      "endpoint": "http://mel2133:8001",
      "usage": {"prompt_tokens": 10, "completion_tokens": 25, "total_tokens": 35}
    }
    ```

    **Returns (Error):**
    ```json
    {
      "success": false,
      "error": "Failed to connect to VLLM service: Connection refused",
      "endpoint": "http://mel2133:8001"
    }
    ```

    **Errors:**
    - 400: Prompt is missing or invalid
    - 404: vLLM service not found
    - 500: Service error or connection failure

    **Example:**
    ```bash
    curl -X POST "http://server:8000/api/v1/vllm/3642874/prompt" \\
      -H "Content-Type: application/json" \\
      -d '{"prompt": "What is AI?", "max_tokens": 100}'
    ```

    **Note:** The vLLM service must be fully initialized (status="running") before it can accept prompts.
    """
    try:
        prompt = request.get("prompt")
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")

        # Extract optional parameters
        kwargs = {
            "max_tokens": request.get("max_tokens", 150),
            "temperature": request.get("temperature", 0.7),
            "model": request.get("model")
        }
        # Remove None values
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        result = server_service.prompt_vllm_service(service_id, prompt, **kwargs)
        return result
    except HTTPException:
        # Re-raise HTTPExceptions (like our 400 error) without wrapping them
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/{service_id}/models")
async def get_vllm_models(service_id: str, server_service: ServerService = Depends(get_server_service)):
    """Get the list of models served by a running vLLM service.

    Queries the vLLM service's /v1/models endpoint to discover which models are loaded and available.
    This is useful when you don't know which model to specify in prompt requests.

    **Path Parameters:**
    - `service_id`: SLURM job ID of the vLLM service

    **Returns (Success):**
    ```json
    {
      "success": true,
      "models": ["Qwen/Qwen3-0.6B", "gpt2"],
      "service_id": "3642874",
      "endpoint": "http://mel2079:8000"
    }
    ```

    **Returns (Service Not Ready):**
    ```json
    {
      "success": false,
      "error": "Service is not ready yet (status: starting)",
      "message": "The vLLM service is still starting up (status: starting). Please wait a moment and try again.",
      "service_id": "3642874",
      "status": "starting",
      "models": []
    }
    ```

    **Returns (No Models):**
    ```json
    {
      "success": true,
      "models": [],
      "service_id": "3642874",
      "endpoint": "http://mel2079:8000"
    }
    ```

    **Example:**
    - GET `/api/v1/vllm/3642874/models`

    **Note:** 
    - The response now includes success status and detailed error messages
    - Check the `success` field to determine if the operation succeeded
    - Model names can be used in the `model` parameter of the prompt endpoint
    """
    try:
        result = server_service.get_vllm_models(service_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/{service_id}/metrics")
async def get_vllm_metrics(service_id: str, server_service: ServerService = Depends(get_server_service)):
    """Get Prometheus-compatible metrics from a running vLLM service.

    vLLM natively exposes comprehensive metrics on the /metrics endpoint in Prometheus text format.
    These metrics can be scraped by Prometheus, Grafana, or any other monitoring system that supports
    the Prometheus metrics format.

    **Available Metrics Include:**
    - `vllm_request_count`: Total number of requests processed
    - `vllm_request_duration_seconds`: Request latency distribution (histogram)
    - `vllm_tokens_generated`: Total tokens generated by the model
    - `vllm_cache_usage_ratio`: KV cache usage as a ratio (0.0-1.0)
    - `vllm_scheduling_delays`: Scheduling delays in the batch processor
    - `vllm_running_requests`: Number of requests currently being processed
    - Plus many more detailed metrics for performance monitoring

    **Path Parameters:**
    - `service_id`: SLURM job ID of the vLLM service

    **Available Metrics (vLLM-specific):**
    - `vllm:num_requests_running` - Number of requests currently being processed
    - `vllm:num_requests_waiting` - Number of requests waiting in queue
    - `vllm:kv_cache_usage_perc` - KV cache utilization percentage (0.0-1.0)
    - `vllm:prompt_tokens_total` - Total number of prompt tokens processed
    - `vllm:generation_tokens_total` - Total number of tokens generated
    - `vllm:time_to_first_token_seconds` - Histogram of time to first token
    - `vllm:time_per_output_token_seconds` - Histogram of time per output token
    - `vllm:e2e_request_latency_seconds` - End-to-end request latency histogram

    **Returns (Success):**
    - Content-Type: `text/plain; version=0.0.4`
    - Body: Prometheus text format metrics

    **Example Success Response:**
    ```
    # HELP vllm:num_requests_running Number of requests currently running
    # TYPE vllm:num_requests_running gauge
    vllm:num_requests_running{engine="0",model_name="gpt2"} 0.0
    # HELP vllm:prompt_tokens_total Total prompt tokens processed
    # TYPE vllm:prompt_tokens_total counter
    vllm:prompt_tokens_total{engine="0",model_name="gpt2"} 150.0
    ...
    ```

    **Returns (Error):**
    - Content-Type: `application/json`
    - Body: JSON error object

    **Example Error Response:**
    ```json
    {
      "success": false,
      "error": "Service is not ready yet (status: starting)",
      "message": "The vLLM service is still starting up. Please wait.",
      "service_id": "3642874",
      "status": "starting"
    }
    ```

    **Integration with Prometheus:**
    Add this endpoint to your Prometheus scrape configuration:
    ```yaml
    scrape_configs:
      - job_name: 'vllm-services'
        static_configs:
          - targets: ['server:8001']
        metrics_path: '/api/v1/vllm/<service_id>/metrics'
        scrape_interval: 15s
    ```

    **Example:**
    ```bash
    curl http://localhost:8001/api/v1/vllm/3642874/metrics
    ```

    **Note:**
    - Metrics are returned in Prometheus text format (not JSON)
    - This endpoint is lightweight and safe to call frequently (every 5-15 seconds)
    - Metrics are cumulative counters and gauges - use Prometheus functions like `rate()` for analysis
    """
    try:
        from fastapi.responses import PlainTextResponse
        
        result = server_service.get_vllm_metrics(service_id)
        
        # If successful, return metrics as plain text
        if result.get("success"):
            return PlainTextResponse(
                content=result.get("metrics", ""),
                media_type="text/plain; version=0.0.4"
            )
        else:
            # Return error as JSON
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector-db/{service_id}/metrics")
async def get_qdrant_metrics(service_id: str, server_service: ServerService = Depends(get_server_service)):
    """Get Prometheus metrics from a running Qdrant vector database service.

    Queries the Qdrant service's /metrics endpoint to retrieve Prometheus-compatible metrics.
    Qdrant natively exposes metrics about collections, points, search operations, and performance.

    **Path Parameters:**
    - `service_id`: SLURM job ID of the Qdrant service

    **Available Metrics (Qdrant-specific):**
    - `app_info` - Application information (version, features)
    - `app_status_recovery_mode` - Whether recovery mode is active
    - `collections_total` - Total number of collections
    - `collections_vector_total` - Total number of vectors across all collections
    - `collections_full_total` - Number of fully optimized collections
    - `rest_responses_total` - Total REST API responses by status code
    - `rest_responses_duration_seconds` - REST API response time histogram
    - `grpc_responses_total` - Total gRPC responses by status code
    - `grpc_responses_duration_seconds` - gRPC response time histogram

    **Returns (Success):**
    - Content-Type: `text/plain; version=0.0.4`
    - Body: Prometheus text format metrics

    **Example Success Response:**
    ```
    # HELP app_info information about qdrant server
    # TYPE app_info gauge
    app_info{name="qdrant",version="1.7.0"} 1
    # HELP collections_total Number of collections
    # TYPE collections_total gauge
    collections_total 3
    # HELP rest_responses_total Total number of responses
    # TYPE rest_responses_total counter
    rest_responses_total{status="200"} 45
    ...
    ```

    **Returns (Error):**
    - Content-Type: `application/json`
    - Body: JSON error object

    **Example Error Response:**
    ```json
    {
      "success": false,
      "error": "Service is not ready yet (status: starting)",
      "message": "The Qdrant service is still starting up. Please wait.",
      "service_id": "3642875",
      "status": "starting"
    }
    ```

    **Integration with Prometheus:**
    Add this endpoint to your Prometheus scrape configuration:
    ```yaml
    scrape_configs:
      - job_name: 'qdrant-services'
        static_configs:
          - targets: ['server:8001']
        metrics_path: '/api/v1/vector-db/<service_id>/metrics'
        scrape_interval: 15s
    ```

    **Example:**
    ```bash
    curl http://localhost:8001/api/v1/vector-db/3642875/metrics
    ```

    **Note:**
    - Metrics are returned in Prometheus text format (not JSON)
    - This endpoint is lightweight and safe to call frequently (every 5-15 seconds)
    - Metrics provide insights into collection sizes, API usage, and performance
    """
    try:
        from fastapi.responses import PlainTextResponse
        
        result = server_service.get_qdrant_metrics(service_id)
        
        # If successful, return metrics as plain text
        if result.get("success"):
            return PlainTextResponse(
                content=result.get("metrics", ""),
                media_type="text/plain; version=0.0.4"
            )
        else:
            # Return error as JSON
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

