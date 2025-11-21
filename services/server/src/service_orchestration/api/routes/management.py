"""
Management API routes (called by Server via SSH)
Handles service registration, metrics, and configuration
"""

from fastapi import APIRouter


def create_router(orchestrator):
    """Create management routes"""
    router = APIRouter()
    
    @router.post("/register")
    async def register_service(service_id: str, host: str, port: int, model: str):
        """Register a vLLM service"""
        return orchestrator.register_service(service_id, host, port, model)
    
    @router.delete("/services/{service_id}")
    async def unregister_service(service_id: str):
        """Unregister a vLLM service"""
        return orchestrator.unregister_service(service_id)
    
    @router.get("/metrics")
    async def get_metrics():
        """Get metrics"""
        return orchestrator.get_metrics()
    
    @router.post("/configure")
    async def configure(strategy: str):
        """Configure load balancer strategy"""
        return orchestrator.configure_load_balancer(strategy)
    
    return router
