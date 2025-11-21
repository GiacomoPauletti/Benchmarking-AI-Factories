"""
Client-facing API routes
Direct client requests (OpenAI-compatible endpoints)
No SSH overhead - local network on MeluXina
"""

from fastapi import APIRouter, Request, HTTPException


def create_router(orchestrator):
    """Create client-facing routes"""
    router = APIRouter()
    
    @router.post("/v1/completions")
    async def completions(request: Request):
        """Handle completion requests from clients (OpenAI-compatible)"""
        data = await request.json()
        try:
            return await orchestrator.forward_completion(data)
        except RuntimeError as e:
            # Convert orchestrator RuntimeError to HTTPException
            if "No healthy vLLM services" in str(e):
                raise HTTPException(status_code=503, detail=str(e))
            else:
                raise HTTPException(status_code=502, detail=str(e))
    
    @router.get("/health")
    async def health():
        """Health check endpoint"""
        return {"status": "healthy", "services": len(orchestrator.endpoints)}
    
    return router
