"""
API route definitions for SLURM-based service orchestration.
"""

import logging
from fastapi import APIRouter, HTTPException, Body, Depends, Query
from typing import List, Dict, Any, Optional

from api.schemas import ServiceRequest, ServiceResponse, RecipeResponse
from service_orchestration.services.inference.vllm_models_config import (
    get_architecture_info,
    search_hf_models,
    get_model_info as get_hf_model_info,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Global orchestrator proxy instance (set by main.py at startup)
_orchestrator_proxy_instance = None

def set_orchestrator_proxy(proxy):
    """Set the global orchestrator proxy instance."""
    global _orchestrator_proxy_instance
    _orchestrator_proxy_instance = proxy

def get_orchestrator_proxy():
    """Dependency function to get the orchestrator proxy instance."""
    if _orchestrator_proxy_instance is None:
        raise RuntimeError("Orchestrator proxy not initialized")
    return _orchestrator_proxy_instance


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
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Create and start a new service.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, parameters, and examples, see the orchestrator API documentation at:
    **POST /api/services/start** on the orchestrator service.
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[DEBUG] create_service received: recipe_name={request.recipe_name}, config={request.config}")
        response = orchestrator.start_service(
            recipe_name=request.recipe_name,
            config=request.config or {}
        )
        
        # Check for error responses from orchestrator
        if isinstance(response, dict) and response.get("status") == "error":
            raise HTTPException(status_code=500, detail=response.get("message", "Unknown error"))
        
        # Unwrap service_data if present (orchestrator returns {status, job_id, service_data})
        if "service_data" in response:
            return response["service_data"]
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services", response_model=List[ServiceResponse])
async def list_services(orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** List all services managed by the orchestrator.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, filtering options, and response schemas, see the orchestrator API documentation at:
    **GET /api/services** on the orchestrator service.
    """
    services = orchestrator.list_services()
    return services


@router.get("/services/targets")
async def get_service_targets(orchestrator = Depends(get_orchestrator_proxy)):
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
        "targets": ["mel0343:8002"],
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
        services_response = orchestrator.list_services()
        logger.debug(f"list_services() returned: {type(services_response)} = {repr(services_response)}")
        
        # Handle both dict response {'services': [...]} and list response [...]
        if isinstance(services_response, dict):
            services_list = services_response.get('services', [])
        else:
            services_list = services_response
        
        for service in services_list:
            service_id = service["id"]
            
            # Get full service details to resolve endpoint
            service_details = orchestrator.get_service(service_id)
            if not service_details:
                continue
            
            # Only include running services with resolved endpoints
            status = service_details.get("status", "").lower()
            if status not in ["running", "RUNNING", "pending", "PENDING", "starting", "STARTING"]:
                continue
            
            # Extract endpoint - it's in format "http://host:port"
            endpoint = service_details.get("endpoint")
            if not endpoint:
                # If pending, we might not have an endpoint yet.
                # Use a placeholder so Prometheus still discovers it.
                if status in ["pending", "PENDING", "starting", "STARTING"]:
                     target = f"pending-{service_id}"
                else:
                     continue
            else:
                # Strip protocol to get "host:port" format for Prometheus
                target = endpoint.replace("http://", "").replace("https://", "")
            
            targets.append({
                "targets": [target],
                "labels": {
                    "job": f"service-{service_id}",
                    "service_id": service_id,
                    "recipe_name": service["recipe_name"],
                }
            })
        return targets
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/{service_id}", response_model=ServiceResponse)
async def get_service(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get detailed information about a specific service or service group.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, response formats, and service/group detection logic, see the orchestrator API documentation at:
    **GET /api/services/{service_id}** on the orchestrator service.
    """
    service = orchestrator.get_service(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.get("/service-groups")
async def list_service_groups(orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** List all service groups.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, response format, and filtering options, see the orchestrator API documentation at:
    **GET /api/service-groups** on the orchestrator service.
    """
    try:
        groups = orchestrator.list_service_groups()
        return groups
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service-groups/{group_id}")
async def get_service_group(group_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get detailed information about a service group and all its replicas.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, replica information, and health status details, see the orchestrator API documentation at:
    **GET /api/service-groups/{group_id}** on the orchestrator service.
    """
    try:
        group_info = orchestrator.get_service_group(group_id)
        if not group_info:
            raise HTTPException(status_code=404, detail=f"Service group '{group_id}' not found")
        return group_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/service-groups/{group_id}")
async def stop_service_group(group_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Stop all replicas in a service group.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, response format, and error handling, see the orchestrator API documentation at:
    **DELETE /api/service-groups/{group_id}** on the orchestrator service.
    """
    try:
        result = orchestrator.stop_service_group(group_id)
        
        # Handle not found gracefully - if already stopped, return success
        if not result.get("success"):
            error_msg = result.get("error", "Service group not found")
            # If the group doesn't exist, it's already stopped - this is idempotent
            if "not found" in error_msg.lower():
                return {
                    "success": True,
                    "message": f"Service group {group_id} already stopped or does not exist",
                    "group_id": group_id,
                    "replicas_stopped": 0
                }
            # For other errors, return 500
            raise HTTPException(status_code=500, detail=error_msg)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service-groups/{group_id}/status")
async def get_service_group_status(group_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get aggregated status of a service group.
    
    This endpoint proxies to the orchestrator's service management API.
    
    For detailed documentation, status values, and health metrics, see the orchestrator API documentation at:
    **GET /api/service-groups/{group_id}/status** on the orchestrator service.
    """
    try:
        status_info = orchestrator.get_service_group_status(group_id)
        if not status_info:
            raise HTTPException(status_code=404, detail=f"Service group '{group_id}' not found")
        return status_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/service-groups/{group_id}/status")
async def update_service_group_status(
    group_id: str,
    status_update: Dict[str, str] = Body(..., examples={
        "cancel": {
            "summary": "Cancel a service group",
            "value": {"status": "cancelled"}
        }
    }),
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Update the status of a service group (primarily for cancelling).
    
    This endpoint proxies to the orchestrator's service group management API.
    Similar to single service status updates, this allows graceful cancellation
    of all replicas in a group while preserving metadata for analysis.
    
    For detailed documentation, see the orchestrator API documentation at:
    **POST /api/service-groups/{group_id}/status** on the orchestrator service.
    """
    new_status = status_update.get("status")
    
    if not new_status:
        raise HTTPException(status_code=400, detail="Missing 'status' field in request body")
    
    # Currently only support cancelling service groups
    if new_status == "cancelled":
        result = orchestrator.update_service_group_status(group_id, new_status)
        if not result.get("success"):
            error_msg = result.get("error", "Service group not found")
            if "not found" in error_msg.lower():
                raise HTTPException(status_code=404, detail=error_msg)
            else:
                raise HTTPException(status_code=500, detail=error_msg)
        return result
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported status value: '{new_status}'. Currently only 'cancelled' is supported."
        )


@router.get("/services/{service_id}/metrics")
async def get_service_metrics(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get Prometheus-compatible metrics from any service.
    
    This endpoint proxies to the orchestrator's unified metrics API.
    
    For detailed documentation, supported service types, metric formats, and Prometheus integration examples, see the orchestrator API documentation at:
    **GET /api/services/{service_id}/metrics** on the orchestrator service.
    """
    from fastapi.responses import PlainTextResponse
    
    # Route to appropriate service-specific metrics endpoint
    result = orchestrator.get_service_metrics(service_id)
    
    if isinstance(result, dict):
        if result.get("success"):
            return PlainTextResponse(
                content=result.get("metrics", ""),
                media_type="text/plain; version=0.0.4"
            )
        else:
            # If metrics retrieval failed, return 500 so Prometheus marks target as down
            error_msg = result.get("error", "Unknown error fetching metrics")
            raise HTTPException(status_code=500, detail=error_msg)
            
    # Fallback for unexpected return types
    return PlainTextResponse(
        content=str(result),
        media_type="text/plain; version=0.0.4"
    )


@router.delete("/services/{service_id}")
async def stop_service(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** DEPRECATED - Stop a service (use POST /services/{service_id}/status instead).
    
    This endpoint proxies to the orchestrator's service stop API.
    
    **DEPRECATION NOTICE:** Use POST /services/{service_id}/status with {"status": "cancelled"} instead.
    
    For detailed documentation and recommended alternatives, see the orchestrator API documentation at:
    **POST /api/services/stop/{service_id}** on the orchestrator service.
    """
    success = orchestrator.stop_service(service_id)
    if success:
        return {"message": f"Service {service_id} stopped successfully"}
    else:
        raise HTTPException(status_code=404, detail="Service not found or failed to stop")


@router.get("/services/{service_id}/logs")
async def get_service_logs(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get SLURM logs (stdout and stderr) from a service.
    
    This endpoint proxies to the orchestrator's service logs API.
    
    For detailed documentation, log format descriptions, and troubleshooting tips, see the orchestrator API documentation at:
    **GET /api/services/{service_id}/logs** on the orchestrator service.
    """
    return orchestrator.get_service_logs(service_id)


@router.get("/services/{service_id}/status")
async def get_service_status(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get the current detailed status of a service.
    
    This endpoint proxies to the orchestrator's service status API.
    
    For detailed documentation, status values, and initialization stages, see the orchestrator API documentation at:
    **GET /api/services/{service_id}/status** on the orchestrator service.
    """
    return orchestrator.get_service_status(service_id)


@router.post("/services/{service_id}/status")
async def update_service_status(
    service_id: str,
    status_update: Dict[str, str] = Body(..., examples={
        "cancel": {
            "summary": "Cancel a running service",
            "value": {"status": "cancelled"}
        }
    }),
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Update the status of a service (primarily for cancelling).
    
    This endpoint proxies to the orchestrator's service status update API.
    
    For detailed documentation, supported status values, state transitions, and examples, see the orchestrator API documentation at:
    **POST /api/services/{service_id}/status** (or equivalent) on the orchestrator service.
    """
    new_status = status_update.get("status")
    
    if not new_status:
        raise HTTPException(status_code=400, detail="Missing 'status' field in request body")
    
    # Currently only support cancelling services
    if new_status == "cancelled":
        try:
            result = orchestrator.stop_service(service_id)
            # The orchestrator handles status updates internally
            return {
                "message": f"Service {service_id} status updated to {new_status}",
                "service_id": service_id,
                "status": new_status
            }
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Service not found or failed to stop: {e}")
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported status value: '{new_status}'. Currently only 'cancelled' is supported."
        )


@router.get("/recipes")
async def list_or_get_recipe(
    path: Optional[str] = None,
    name: Optional[str] = None,
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** List all available recipes OR get a specific recipe.
    
    This endpoint proxies to the orchestrator's recipe management API.
    
    For detailed documentation, query parameters, recipe structure, and examples, see the orchestrator API documentation at:
    **GET /api/recipes** on the orchestrator service.
    """
    recipes = orchestrator.list_available_recipes()
    
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
async def list_vllm_services(orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** List all running vLLM inference services with their endpoints.
    
    This endpoint proxies to the orchestrator's vLLM service discovery API.
    
    For detailed documentation, endpoint resolution, and service status meanings, see the orchestrator API documentation at:
    **GET /api/vllm** (or /api/data-plane/vllm) on the orchestrator service.
    """
    try:
        vllm_services = orchestrator.find_vllm_services()
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


@router.get("/vllm/model-options")
async def get_vllm_model_options():
    """Get vLLM model options formatted for Grafana dropdown.
    
    Returns an array of label/value pairs suitable for use in Grafana Form Panel dropdowns.
    Each entry contains a human-readable label and the corresponding HuggingFace model ID.
    
    **Returns:**
    ```json
    [
      {"label": "GPT-2 (small, for testing)", "value": "gpt2"},
      {"label": "Llama 2 7B Chat", "value": "meta-llama/Llama-2-7b-chat-hf"},
      ...
    ]
    ```
    """
    try:
        info = get_architecture_info()
        examples = info.get("examples", {})
        # Convert examples dict to array of label/value objects
        return [{"label": label, "value": value} for label, value in examples.items()]
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
async def list_vector_db_services(orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** List all running vector database services.
    
    This endpoint proxies to the orchestrator's vector database service discovery API.
    
    For detailed documentation, supported vector databases, and endpoint formats, see the orchestrator API documentation at:
    **GET /api/vector-db** (or /api/data-plane/vector-db) on the orchestrator service.
    """
    try:
        vector_db_services = orchestrator.find_vector_db_services()
        return {"vector_db_services": vector_db_services}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector-db/{service_id}/collections")
async def get_collections(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get list of collections from a vector database service.
    
    This endpoint proxies to the orchestrator's vector database collections API.
    
    For detailed documentation, supported operations, and response formats, see the orchestrator API documentation at:
    **GET /api/vector-db/{service_id}/collections** on the orchestrator service.
    """
    try:
        result = orchestrator.get_collections(service_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector-db/{service_id}/collections/{collection_name}")
async def get_collection_info(
    service_id: str,
    collection_name: str,
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Get detailed information about a specific collection.
    
    This endpoint proxies to the orchestrator's collection info API.
    
    For detailed documentation, collection metadata formats, and vector configuration details, see the orchestrator API documentation at:
    **GET /api/vector-db/{service_id}/collections/{collection_name}** on the orchestrator service.
    """
    try:
        result = orchestrator.get_collection_info(service_id, collection_name)
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
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Create a new collection in the vector database.
    
    This endpoint proxies to the orchestrator's collection creation API.
    
    For detailed documentation, vector size configuration, distance metrics, and examples, see the orchestrator API documentation at:
    **PUT /api/vector-db/{service_id}/collections/{collection_name}** on the orchestrator service.
    """
    try:
        vector_size = request.get("vector_size")
        if not vector_size:
            raise HTTPException(status_code=400, detail="vector_size is required")
        
        distance = request.get("distance", "Cosine")
        result = orchestrator.create_collection(service_id, collection_name, vector_size, distance)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/vector-db/{service_id}/collections/{collection_name}")
async def delete_collection(
    service_id: str,
    collection_name: str,
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Delete a collection from the vector database.
    
    This endpoint proxies to the orchestrator's collection deletion API.
    
    For detailed documentation, operation details, and error handling, see the orchestrator API documentation at:
    **DELETE /api/vector-db/{service_id}/collections/{collection_name}** on the orchestrator service.
    """
    try:
        result = orchestrator.delete_collection(service_id, collection_name)
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
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Insert or update points (vectors with payloads) in a collection.
    
    This endpoint proxies to the orchestrator's vector upsert API.
    
    For detailed documentation, point formats, payload structures, and batch operations, see the orchestrator API documentation at:
    **PUT /api/vector-db/{service_id}/collections/{collection_name}/points** on the orchestrator service.
    """
    try:
        points = request.get("points")
        if not points or not isinstance(points, list):
            raise HTTPException(status_code=400, detail="points must be a non-empty list")
        
        result = orchestrator.upsert_points(service_id, collection_name, points)
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
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Search for similar vectors in a collection.
    
    This endpoint proxies to the orchestrator's vector search API.
    
    For detailed documentation, query parameters, scoring methods, and filtering options, see the orchestrator API documentation at:
    **POST /api/vector-db/{service_id}/collections/{collection_name}/points/search** on the orchestrator service.
    """
    try:
        query_vector = request.get("query_vector")
        if not query_vector or not isinstance(query_vector, list):
            raise HTTPException(status_code=400, detail="query_vector must be a non-empty list")
        
        limit = request.get("limit", 10)
        result = orchestrator.search_points(service_id, collection_name, query_vector, limit)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orchestrator/endpoint")
async def get_orchestrator_endpoint(orchestrator = Depends(get_orchestrator_proxy)):
    """Get the internal endpoint of the orchestrator service.
    
    This endpoint returns the internal URL of the orchestrator running on the compute node.
    Clients can use this to communicate directly with the orchestrator if needed.
    
    **Returns:**
    ```json
    {
      "endpoint": "http://mel1234:8003"
    }
    ```
    """
    endpoint = orchestrator.get_orchestrator_url()
    if not endpoint:
        raise HTTPException(status_code=404, detail="Orchestrator endpoint not available")
    return {"endpoint": endpoint}


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
    orchestrator = Depends(get_orchestrator_proxy)
):
    """**[Proxy]** Send a text prompt to a running vLLM inference service.
    
    This endpoint proxies to the orchestrator's vLLM prompt API.
    
    For detailed documentation, request parameters, response formats, and examples, see the orchestrator API documentation at:
    **POST /api/vllm/{service_id}/prompt** (or /api/data-plane/vllm/{service_id}/prompt) on the orchestrator service.
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

        result = orchestrator.prompt_vllm_service(service_id, prompt, **kwargs)
        return result
    except HTTPException:
        # Re-raise HTTPExceptions (like our 400 error) without wrapping them
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vllm/{service_id}/models")
async def get_vllm_models(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """**[Proxy]** Get the list of models served by a running vLLM service.
    
    This endpoint proxies to the orchestrator's vLLM model discovery API.
    
    For detailed documentation, model formats, and service status handling, see the orchestrator API documentation at:
    **GET /api/vllm/{service_id}/models** (or /api/data-plane/vllm/{service_id}/models) on the orchestrator service.
    """
    try:
        result = orchestrator.get_vllm_models(service_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{service_id}")
async def get_service_metrics_generic(service_id: str, orchestrator = Depends(get_orchestrator_proxy)):
    """Get Prometheus metrics from any service (generic endpoint).
    
    This is a unified metrics endpoint that automatically routes to the appropriate
    service-specific metrics endpoint based on the service's recipe type.
    
    **Path Parameters:**
    - `service_id`: The SLURM job ID or service group ID of the service
    
    **Returns (Success):**
    - Content-Type: `text/plain; version=0.0.4`
    - Body: Prometheus text format metrics
    
    **Returns (Error):**
    - Content-Type: `application/json`
    - Body: JSON error object with details
    
    **Examples:**
    ```bash
    # Get metrics from any service
    curl http://localhost:8001/api/v1/metrics/3642874
    ```
    
    **Integration with Prometheus:**
    ```yaml
    scrape_configs:
      - job_name: 'managed-services'
        static_configs:
          - targets: ['server:8001']
        metrics_path: '/api/v1/metrics/<service_id>'
        scrape_interval: 15s
    ```
    
    **Note:** This endpoint determines the service type automatically and routes
    to the appropriate metrics fetcher (vLLM, Qdrant, etc.).
    """
    from fastapi.responses import PlainTextResponse
    
    try:
        # Delegate to orchestrator which will handle service type detection
        result = orchestrator.get_service_metrics(service_id)
        
        # If successful, return metrics as plain text
        if result.get("success"):
            return PlainTextResponse(
                content=result.get("metrics", ""),
                media_type="text/plain; version=0.0.4"
            )
        else:
            # Return error as JSON
            error = result.get("error", "Unknown error")
            status_code = result.get("status_code", 500)
            raise HTTPException(status_code=status_code, detail=error)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
