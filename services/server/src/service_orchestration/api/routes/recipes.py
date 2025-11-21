"""
Recipe API routes
List and query available service recipes
"""

from fastapi import APIRouter


def create_router(orchestrator):
    """Create recipe routes"""
    router = APIRouter()
    
    @router.get("")
    async def list_recipes():
        """List all available service recipes"""
        return orchestrator.list_recipes()
    
    return router
