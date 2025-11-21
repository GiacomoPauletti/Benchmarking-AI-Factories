"""
Service Management API routes
High-level service and service group operations
"""

from fastapi import APIRouter, HTTPException, Request


def create_router(orchestrator):
    """Create service management routes"""
    router = APIRouter()
    
    # ===== Service Operations =====
    
    @router.get("")
    async def list_services():
        """List all services"""
        return orchestrator.list_services()
    
    @router.post("/start")
    async def start_service(request: Request):
        """Start a new service from a recipe"""
        data = await request.json()
        recipe_name = data.get("recipe_name")
        config = data.get("config", {})
        
        if not recipe_name:
            raise HTTPException(status_code=400, detail="recipe_name required")
        
        return orchestrator.start_service(recipe_name, config)
    
    @router.post("/stop/{service_id}")
    async def stop_service(service_id: str):
        """Stop a service"""
        return orchestrator.stop_service(service_id)
    
    @router.get("/{service_id}")
    async def get_service(service_id: str):
        """Get details of a specific service or service group"""
        service = orchestrator.get_service(service_id)
        if service is None:
            raise HTTPException(status_code=404, detail=f"Service {service_id} not found")
        return service
    
    @router.get("/{service_id}/status")
    async def get_service_status(service_id: str):
        """Get current status of a service or service group"""
        return orchestrator.get_service_status(service_id)
    
    @router.get("/{service_id}/logs")
    async def get_service_logs(service_id: str):
        """Get SLURM logs from a service"""
        return orchestrator.get_service_logs(service_id)
    
    return router
