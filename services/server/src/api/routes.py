"""
API route definitions.
"""

from fastapi import APIRouter, HTTPException
from typing import List
from ..models import Service, Recipe
from ..server_service import ServerService
from .schemas import ServiceRequest, ServiceResponse, RecipeResponse

router = APIRouter()


@router.post("/services", response_model=ServiceResponse)
async def create_service(request: ServiceRequest):
    """Create and start a new service."""
    server_service = ServerService()
    service = server_service.start_service(
        recipe_name=request.recipe_name,
        nodes=request.nodes,
        config=request.config
    )
    return service


@router.get("/services", response_model=List[ServiceResponse])
async def list_services():
    """List all running services."""
    server_service = ServerService()
    services = server_service.list_running_services()
    return services


@router.get("/services/{service_id}", response_model=ServiceResponse)
async def get_service(service_id: str):
    """Get details of a specific service."""
    # Implementation will be added here
    pass


@router.delete("/services/{service_id}")
async def stop_service(service_id: str):
    """Stop a running service."""
    server_service = ServerService()
    success = server_service.stop_service(service_id)
    if success:
        return {"message": f"Service {service_id} stopped successfully"}
    else:
        raise HTTPException(status_code=404, detail="Service not found or failed to stop")


@router.get("/recipes", response_model=List[RecipeResponse])
async def list_recipes():
    """List all available recipes."""
    server_service = ServerService()
    recipes = server_service.list_available_recipes()
    return recipes


@router.get("/recipes/{recipe_name}", response_model=RecipeResponse)
async def get_recipe(recipe_name: str):
    """Get details of a specific recipe."""
    # Implementation will be added here
    pass