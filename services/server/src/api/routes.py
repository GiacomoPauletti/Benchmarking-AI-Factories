"""
API route definitions for SLURM-based service orchestration.
"""

from fastapi import APIRouter, HTTPException
from typing import List

from server_service import ServerService
from api.schemas import ServiceRequest, ServiceResponse, RecipeResponse

router = APIRouter()


@router.post("/services", response_model=ServiceResponse)
async def create_service(request: ServiceRequest):
    """Create and start a new service using SLURM + Apptainer."""
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