"""
API route definitions for SLURM-based service orchestration.
"""

from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Any, Optional

from server_service import ServerService
from api.schemas import ServiceRequest, ServiceResponse, RecipeResponse

router = APIRouter()


@router.post("/services", response_model=ServiceResponse, summary="Create and start a new service")
async def create_service(
    request: ServiceRequest = Body(...,
        examples={
            "simple": {
                "summary": "Create a basic vLLM service",
                "value": {"recipe_name": "inference/vllm", "config": {"nodes": 1, "cpus": 2, "memory": "8G", "time": "00:30:00"}}
            }
        }
    )
):
    """Create and start a new service using SLURM + Apptainer.

    This endpoint submits a job to the SLURM cluster using a predefined recipe template.
    The service will be containerized using Apptainer and scheduled on compute nodes.

    **Request Body:**
    - `recipe_name` (required): Path to the recipe (e.g., "inference/vllm", "inference/vllm_dummy")
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
      "recipe_name": "inference/vllm"
    }
    ```

    Custom model:
    ```json
    {
      "recipe_name": "inference/vllm",
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
      "recipe_name": "inference/vllm",
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
    server_service = ServerService()
    try:
        service = server_service.start_service(
            recipe_name=request.recipe_name,
            config=request.config
        )
        return service
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services", response_model=List[ServiceResponse])
async def list_services():
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
        "recipe_name": "inference/vllm",
        "config": {"nodes": 1, "cpus": 4, "memory": "16G"},
        "created_at": "2025-10-14T10:30:00"
      }
    ]
    ```
    """
    server_service = ServerService()
    services = server_service.list_running_services()
    return services


@router.get("/services/{service_id}", response_model=ServiceResponse)
async def get_service(service_id: str):
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
    server_service = ServerService()
    service = server_service.get_service(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.delete("/services/{service_id}")
async def stop_service(service_id: str):
    """Stop a running service by cancelling its SLURM job.

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

    **Example:**
    - DELETE `/api/v1/services/3642874`

    **Note:** This operation is immediate and cannot be undone. The service will be terminated gracefully.
    """
    server_service = ServerService()
    success = server_service.stop_service(service_id)
    if success:
        return {"message": f"Service {service_id} stopped successfully"}
    else:
        raise HTTPException(status_code=404, detail="Service not found or failed to stop")


@router.get("/services/{service_id}/logs")
async def get_service_logs(service_id: str):
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
    server_service = ServerService()
    logs = server_service.get_service_logs(service_id)
    return {"logs": logs}


@router.get("/services/{service_id}/status")
async def get_service_status(service_id: str):
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
    server_service = ServerService()
    status = server_service.get_service_status(service_id)
    return {"status": status}


@router.get("/recipes", response_model=List[RecipeResponse])
async def list_recipes():
    """List all available service recipes.

    Recipes are YAML templates that define how to deploy services on SLURM.
    Each recipe specifies the container image, resource requirements, and runtime configuration.

    **Returns:**
    - Array of recipe objects, each containing:
        - `name`: Recipe identifier (e.g., "vLLM Inference Service")
        - `category`: Recipe category (e.g., "inference", "storage", "vector-db")
        - `description`: Human-readable description
        - `version`: Recipe version
        - `path`: Path to access the recipe (e.g., "inference/vllm")

    **Example Response:**
    ```json
    [
      {
        "name": "vLLM Inference Service",
        "category": "inference",
        "description": "High-performance LLM inference server",
        "version": "1.0.0",
        "path": "inference/vllm"
      }
    ]
    ```

    **Recipe Categories:**
    - `inference`: ML model inference services (vLLM, TensorFlow Serving, etc.)
    - `storage`: Data storage solutions
    - `vector-db`: Vector database services for RAG applications
    - `simple`: Basic test/demo services
    """
    server_service = ServerService()
    recipes = server_service.list_available_recipes()
    return recipes


@router.get("/recipes/{recipe_name}", response_model=RecipeResponse)
async def get_recipe(recipe_name: str):
    """Get detailed information about a specific recipe.

    **Path Parameters:**
    - `recipe_name`: Recipe name or path (e.g., "vLLM Inference Service" or "inference/vllm")

    **Returns:**
    - Recipe object with name, category, description, version, and path

    **Errors:**
    - 404: Recipe not found

    **Example:**
    - GET `/api/v1/recipes/inference/vllm`
    """
    server_service = ServerService()
    recipes = server_service.list_available_recipes()
    
    # Find recipe by name or path
    recipe = None
    for r in recipes:
        if r["name"] == recipe_name or r["path"] == recipe_name:
            recipe = r
            break
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.get("/vllm/services")
async def list_vllm_services():
    """List all running vLLM inference services with their endpoints.

    This endpoint discovers vLLM services among all running services and resolves their network endpoints.
    Use this to find available vLLM instances for inference requests.

    **Returns:**
    - Object with `vllm_services` array, each service containing:
        - `id`: SLURM job ID (service identifier)
        - `name`: Service name
        - `recipe_name`: Recipe used (typically "inference/vllm")
        - `endpoint`: HTTP endpoint URL (e.g., "http://mel2133:8001")
        - `status`: Current status (building/starting/running)

    **Example Response:**
    ```json
    {
      "vllm_services": [
        {
          "id": "3642874",
          "name": "vllm-service",
          "recipe_name": "inference/vllm",
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
    server_service = ServerService()
    try:
        vllm_services = server_service.find_vllm_services()
        return {"vllm_services": vllm_services}
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
    })
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
    server_service = ServerService()
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
async def get_vllm_models(service_id: str):
    """Get the list of models served by a running vLLM service.

    Queries the vLLM service's /v1/models endpoint to discover which models are loaded and available.
    This is useful when you don't know which model to specify in prompt requests.

    **Path Parameters:**
    - `service_id`: SLURM job ID of the vLLM service

    **Returns:**
    ```json
    {
      "models": ["Qwen/Qwen3-0.6B", "gpt2"]
    }
    ```

    **Returns (No Models):**
    ```json
    {
      "models": []
    }
    ```

    **Errors:**
    - 500: Failed to connect to vLLM service or parse response

    **Example:**
    - GET `/api/v1/vllm/3642874/models`

    **Note:** 
    - The vLLM service must be in "running" status to respond
    - Empty array may indicate the service is still initializing or has no models loaded
    - Model names can be used in the `model` parameter of the prompt endpoint
    """
    server_service = ServerService()
    try:
        models = server_service.get_vllm_models(service_id)
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))