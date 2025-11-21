"""
Service Group API routes
Manage groups of replicated services
"""

from fastapi import APIRouter, HTTPException


def create_router(orchestrator):
    """Create service group routes"""
    router = APIRouter()
    
    @router.get("")
    async def list_service_groups():
        """List all service groups"""
        return orchestrator.list_service_groups()
    
    @router.get("/{group_id}")
    async def get_service_group(group_id: str):
        """Get detailed information about a service group"""
        group = orchestrator.get_service_group(group_id)
        if group is None:
            raise HTTPException(status_code=404, detail=f"Service group {group_id} not found")
        return group
    
    @router.get("/{group_id}/status")
    async def get_service_group_status(group_id: str):
        """Get aggregated status of a service group"""
        status = orchestrator.get_service_group_status(group_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Service group {group_id} not found")
        return status
    
    @router.post("/{group_id}/stop")
    async def stop_service_group(group_id: str):
        """Stop all replicas in a service group"""
        return orchestrator.stop_service_group(group_id)
    
    return router
