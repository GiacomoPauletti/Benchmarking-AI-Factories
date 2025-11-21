"""
Data Plane API routes
Service-specific operations (vLLM, Qdrant)
Direct communication with running services
"""

from fastapi import APIRouter, HTTPException, Request


def create_router(orchestrator):
    """Create data plane routes"""
    router = APIRouter()
    
    # ===== vLLM Operations =====
    
    @router.get("/vllm")
    async def find_vllm_services():
        """Find running vLLM services"""
        return orchestrator.vllm_service.find_services()
    
    @router.get("/vllm/{service_id}/models")
    async def get_vllm_models(service_id: str, timeout: int = 5):
        """Get models from a vLLM service"""
        return orchestrator.vllm_service.get_models(service_id, timeout)
    
    @router.get("/vllm/{service_id}/metrics")
    async def get_vllm_metrics(service_id: str, timeout: int = 10):
        """Get metrics from a vLLM service"""
        return orchestrator.vllm_service.get_metrics(service_id, timeout)
    
    @router.post("/vllm/{service_id}/prompt")
    async def prompt_vllm_service(service_id: str, request: Request):
        """Send a prompt to a vLLM service"""
        data = await request.json()
        prompt = data.get("prompt")
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt required")
        kwargs = {k: v for k, v in data.items() if k != "prompt"}
        return orchestrator.vllm_service.prompt(service_id, prompt, **kwargs)
    
    # ===== Vector DB (Qdrant) Operations =====
    
    @router.get("/vector-db")
    async def find_vector_db_services():
        """Find running vector DB services"""
        return orchestrator.qdrant_service.find_services()
    
    @router.get("/vector-db/{service_id}/collections")
    async def get_collections(service_id: str, timeout: int = 5):
        """Get collections from a vector DB service"""
        return orchestrator.qdrant_service.get_collections(service_id, timeout)
    
    @router.get("/vector-db/{service_id}/collections/{collection_name}")
    async def get_collection_info(service_id: str, collection_name: str, timeout: int = 5):
        """Get collection info"""
        return orchestrator.qdrant_service.get_collection_info(service_id, collection_name, timeout)
    
    @router.put("/vector-db/{service_id}/collections/{collection_name}")
    async def create_collection(service_id: str, collection_name: str, request: Request):
        """Create a collection"""
        data = await request.json()
        vector_size = data.get("vector_size")
        distance = data.get("distance", "Cosine")
        timeout = data.get("timeout", 10)
        if not vector_size:
            raise HTTPException(status_code=400, detail="vector_size required")
        return orchestrator.qdrant_service.create_collection(service_id, collection_name, vector_size, distance, timeout)
    
    @router.delete("/vector-db/{service_id}/collections/{collection_name}")
    async def delete_collection(service_id: str, collection_name: str, timeout: int = 10):
        """Delete a collection"""
        return orchestrator.qdrant_service.delete_collection(service_id, collection_name, timeout)
    
    @router.put("/vector-db/{service_id}/collections/{collection_name}/points")
    async def upsert_points(service_id: str, collection_name: str, request: Request):
        """Upsert points to a collection"""
        data = await request.json()
        points = data.get("points")
        timeout = data.get("timeout", 30)
        if not points:
            raise HTTPException(status_code=400, detail="points required")
        return orchestrator.qdrant_service.upsert_points(service_id, collection_name, points, timeout)
    
    @router.post("/vector-db/{service_id}/collections/{collection_name}/search")
    async def search_points(service_id: str, collection_name: str, request: Request):
        """Search for similar points"""
        data = await request.json()
        query_vector = data.get("query_vector")
        limit = data.get("limit", 10)
        timeout = data.get("timeout", 10)
        if not query_vector:
            raise HTTPException(status_code=400, detail="query_vector required")
        return orchestrator.qdrant_service.search_points(service_id, collection_name, query_vector, limit, timeout)
    
    @router.get("/vector-db/{service_id}/metrics")
    async def get_qdrant_metrics(service_id: str, timeout: int = 10):
        """Get metrics from a Qdrant service"""
        return orchestrator.qdrant_service.get_metrics(service_id, timeout)
    
    return router
