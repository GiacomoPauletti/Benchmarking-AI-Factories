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

    The `request` body should contain `recipe_name` (path to a recipe, e.g. `inference/vllm`) and
    an optional `config` object with keys like `nodes`, `cpus`, `memory` and `time` (HH:MM:SS).
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
    """List all running services."""
    server_service = ServerService()
    services = server_service.list_running_services()
    return services


@router.get("/services/{service_id}", response_model=ServiceResponse)
async def get_service(service_id: str):
    """Get details of a specific service."""
    server_service = ServerService()
    service = server_service.get_service(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.delete("/services/{service_id}")
async def stop_service(service_id: str):
    """Stop a running service by cancelling the SLURM job."""
    server_service = ServerService()
    success = server_service.stop_service(service_id)
    if success:
        return {"message": f"Service {service_id} stopped successfully"}
    else:
        raise HTTPException(status_code=404, detail="Service not found or failed to stop")


@router.get("/services/{service_id}/logs")
async def get_service_logs(service_id: str):
    """Get logs from a service."""
    server_service = ServerService()
    logs = server_service.get_service_logs(service_id)
    return {"logs": logs}


@router.get("/services/{service_id}/status")
async def get_service_status(service_id: str):
    """Get current status of a service."""
    server_service = ServerService()
    status = server_service.get_service_status(service_id)
    return {"status": status}


@router.get("/recipes", response_model=List[RecipeResponse])
async def list_recipes():
    """List all available recipes."""
    server_service = ServerService()
    recipes = server_service.list_available_recipes()
    return recipes


@router.get("/recipes/{recipe_name}", response_model=RecipeResponse)
async def get_recipe(recipe_name: str):
    """Get details of a specific recipe."""
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
    """List all running VLLM services.

    Returns a JSON object with a `vllm_services` key containing a list of service descriptors.
    """
    server_service = ServerService()
    try:
        vllm_services = server_service.find_vllm_services()
        return {"vllm_services": vllm_services}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vllm/{service_id}/prompt", summary="Send a prompt to a running VLLM service")
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
    """Send a prompt to a running VLLM service.

    Request body fields:
    - `prompt` (string, required): the text prompt to send
    - `model` (string, optional): model id to request (if omitted the server will try to auto-discover)
    - `max_tokens` (int, optional): maximum number of tokens to generate
    - `temperature` (float, optional): sampling temperature
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
    """Get available models served by a running VLLM service.

    The response contains a `models` array with model identifiers discoverable via the vLLM instance.
    Example response: {"models": ["gpt2", "qwen-3b"]}
    """
    server_service = ServerService()
    try:
        models = server_service.get_vllm_models(service_id)
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))