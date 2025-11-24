"""
Main FastAPI application factory for ServiceOrchestrator
"""

from fastapi import FastAPI
import logging

logger = logging.getLogger(__name__)


def create_app(orchestrator) -> FastAPI:
    """
    Create and configure the FastAPI application
    
    Args:
        orchestrator: ServiceOrchestrator instance
        
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="ServiceOrchestrator",
        version="1.0.0",
        description="Orchestrates AI services on MeluXina HPC cluster"
    )
    
    # Register startup/shutdown events
    @app.on_event("startup")
    async def startup_event():
        await orchestrator.start()
        logger.info("ServiceOrchestrator started")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        await orchestrator.stop()
        logger.info("ServiceOrchestrator stopped")
    
    # Register route modules
    from .routes import management, jobs, services, service_groups, recipes, data_plane, client
    
    app.include_router(management.create_router(orchestrator), prefix="/api", tags=["Management"])
    app.include_router(jobs.create_router(orchestrator), prefix="/api/jobs", tags=["Jobs"])
    app.include_router(services.create_router(orchestrator), prefix="/api/services", tags=["Services"])
    app.include_router(service_groups.create_router(orchestrator), prefix="/api/service-groups", tags=["Service Groups"])
    app.include_router(recipes.create_router(orchestrator), prefix="/api/recipes", tags=["Recipes"])
    app.include_router(data_plane.create_router(orchestrator), prefix="/api/services", tags=["Data Plane"])
    app.include_router(client.create_router(orchestrator), tags=["Client"])
    
    return app
