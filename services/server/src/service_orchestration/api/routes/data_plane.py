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
        """List all running vLLM inference services with their endpoints.

        This endpoint discovers vLLM services among all running services and resolves their network endpoints.
        Use this to find available vLLM instances for inference requests.

        **Returns:**
        - Object with `vllm_services` array, each service containing:
            - `id`: SLURM job ID (service identifier)
            - `name`: Service name
            - `recipe_name`: Recipe used (typically "inference/vllm-single-node" or "inference/vllm-replicas")
            - `endpoint`: HTTP endpoint URL (e.g., "http://mel2133:8001")
            - `status`: Current status (building/starting/running)

        **Example Response:**
        ```json
        {
          "vllm_services": [
            {
              "id": "3642874",
              "name": "vllm-service",
              "recipe_name": "inference/vllm-single-node",
              "endpoint": "http://mel2133:8001",
              "status": "running"
            }
          ]
        }
        ```

        **Status Meanings:**
        - `building`: Container image being built (not ready)
        - `starting`: vLLM server initializing, loading model weights (not ready)
        - `running`: vLLM fully loaded and ready to serve inference requests

        **Note:** Only services with status "running" are ready to accept prompt requests.
        Services in "starting" status may take several minutes to become ready, especially
        for large models.
        """
        services = orchestrator.vllm_service.find_services()
        return {"vllm_services": services}
    
    @router.get("/vllm/{service_id}/models")
    async def get_vllm_models(service_id: str, timeout: int = 5):
        """Get the list of models served by a running vLLM service.

        Queries the vLLM service's /v1/models endpoint to discover which models are loaded and available.
        This is useful when you don't know which model to specify in prompt requests.

        **Path Parameters:**
        - `service_id`: SLURM job ID of the vLLM service

        **Query Parameters:**
        - `timeout`: Request timeout in seconds (default: 5)

        **Returns (Success):**
        ```json
        {
          "success": true,
          "models": ["Qwen/Qwen3-0.6B", "gpt2"],
          "service_id": "3642874",
          "endpoint": "http://mel2079:8000"
        }
        ```

        **Returns (Service Not Ready):**
        ```json
        {
          "success": false,
          "error": "Service is not ready yet (status: starting)",
          "message": "The vLLM service is still starting up (status: starting). Please wait a moment and try again.",
          "service_id": "3642874",
          "status": "starting",
          "models": []
        }
        ```

        **Returns (Connection Error):**
        ```json
        {
          "success": false,
          "error": "Failed to connect to vLLM service",
          "endpoint": "http://mel2079:8000",
          "models": []
        }
        ```

        **Use Cases:**
        - Auto-discover model name before sending prompts
        - Verify service is ready and responsive
        - Check which models are available in multi-model setups

        **Note:** vLLM services typically serve one model, but can be configured for multiple models.
        """
        return orchestrator.vllm_service.get_models(service_id, timeout)
    
    @router.post("/vllm/{service_id}/prompt")
    async def prompt_vllm_service(service_id: str, request: Request):
        """Send a text prompt to a running vLLM inference service and get a response.

        This endpoint forwards your prompt to the vLLM service using the OpenAI-compatible API.
        The vLLM service must be in "running" status (not "building" or "starting").

        **Path Parameters:**
        - `service_id`: SLURM job ID of the vLLM service (from find_vllm_services)

        **Request Body:**
        - `prompt` (required): Text prompt to send to the model
        - `model` (optional): Model identifier (auto-discovered if omitted)
        - `max_tokens` (optional): Maximum tokens to generate (default: 150)
        - `temperature` (optional): Sampling temperature 0.0-2.0 (default: 0.7)
        - `top_p` (optional): Nucleus sampling parameter (default: 1.0)
        - `frequency_penalty` (optional): Penalize repeated tokens (default: 0.0)
        - `presence_penalty` (optional): Penalize already mentioned tokens (default: 0.0)

        **Returns (Success):**
        ```json
        {
          "success": true,
          "response": "Generated text response from the model...",
          "service_id": "3642874",
          "endpoint": "http://mel2133:8001",
          "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 25,
            "total_tokens": 35
          }
        }
        ```

        **Returns (Error):**
        ```json
        {
          "success": false,
          "error": "Failed to connect to vLLM service: Connection refused",
          "endpoint": "http://mel2133:8001"
        }
        ```

        **Errors:**
        - 400: Prompt is missing or invalid
        - 404: vLLM service not found
        - 500: Service error or connection failure

        **Example Request:**
        ```json
        {
          "prompt": "What is artificial intelligence?",
          "max_tokens": 100,
          "temperature": 0.7
        }
        ```

        **Note:** The vLLM service must be fully initialized (status="running") before it can accept prompts.
        Check service status or model endpoint first if unsure.
        """
        data = await request.json()
        prompt = data.get("prompt")
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt required")
        kwargs = {k: v for k, v in data.items() if k != "prompt"}
        return orchestrator.vllm_service.prompt(service_id, prompt, **kwargs)
    
    # ===== Vector DB (Qdrant) Operations =====
    
    @router.get("/vector-db")
    async def find_vector_db_services():
        """List all running vector database services with their endpoints.

        Returns a list of vector database services (Qdrant, Chroma, etc.) with their endpoints
        and current status.

        **Returns:**
        - Object with `vector_db_services` array, each service containing:
            - `id`: SLURM job ID (service identifier)
            - `name`: Service name
            - `recipe_name`: Recipe used (e.g., "vector-db/qdrant")
            - `endpoint`: HTTP endpoint URL (e.g., "http://mel2079:6333")
            - `status`: Current status (building/starting/running)

        **Example Response:**
        ```json
        {
          "vector_db_services": [
            {
              "id": "3642875",
              "name": "qdrant-service",
              "recipe_name": "vector-db/qdrant",
              "endpoint": "http://mel2079:6333",
              "status": "running"
            }
          ]
        }
        ```

        **Supported Vector Databases:**
        - **Qdrant**: High-performance vector similarity search engine
        - Additional databases can be added via recipes

        **Status Meanings:**
        - `building`: Container image being built (not ready)
        - `starting`: Database initializing (not ready)
        - `running`: Database ready to accept operations

        **Note:** Only services with status "running" are ready for collection and point operations.
        """
        services = orchestrator.qdrant_service.find_services()
        return {"vector_db_services": services}
    
    @router.get("/vector-db/{service_id}/collections")
    async def get_collections(service_id: str, timeout: int = 5):
        """Get list of collections from a vector database service.

        Returns all collections (vector indexes) currently stored in the database.

        **Path Parameters:**
        - `service_id`: SLURM job ID of the vector DB service

        **Query Parameters:**
        - `timeout`: Request timeout in seconds (default: 5)

        **Returns (Success):**
        ```json
        {
          "success": true,
          "collections": ["my_documents", "embeddings", "knowledge_base"],
          "service_id": "3642875",
          "endpoint": "http://mel2079:6333"
        }
        ```

        **Returns (Service Not Ready):**
        ```json
        {
          "success": false,
          "error": "Service is not ready yet (status: starting)",
          "message": "The vector DB service is still starting up. Please wait.",
          "collections": []
        }
        ```

        **Note:** Empty array means no collections exist yet (not an error).
        Create collections using PUT /vector-db/{service_id}/collections/{collection_name}
        """
        return orchestrator.qdrant_service.get_collections(service_id, timeout)
    
    @router.get("/vector-db/{service_id}/collections/{collection_name}")
    async def get_collection_info(service_id: str, collection_name: str, timeout: int = 5):
        """Get detailed information about a specific collection.

        Returns metadata about a collection including vector configuration, point count, and status.

        **Path Parameters:**
        - `service_id`: SLURM job ID of the vector DB service
        - `collection_name`: Name of the collection

        **Query Parameters:**
        - `timeout`: Request timeout in seconds (default: 5)

        **Returns (Success):**
        ```json
        {
          "success": true,
          "collection_info": {
            "status": "green",
            "vectors_count": 1000,
            "indexed_vectors_count": 1000,
            "points_count": 1000,
            "config": {
              "params": {
                "vectors": {
                  "size": 384,
                  "distance": "Cosine"
                }
              }
            }
          },
          "service_id": "3642875",
          "collection_name": "my_documents"
        }
        ```

        **Collection Status Values:**
        - `green`: Collection is healthy and ready
        - `yellow`: Collection is available but may have issues
        - `red`: Collection has errors

        **Vector Configuration:**
        - `size`: Dimension of vectors (must match embedding model)
        - `distance`: Similarity metric (Cosine, Euclid, or Dot)

        **Point Counts:**
        - `vectors_count`: Total vectors stored
        - `indexed_vectors_count`: Vectors indexed for search
        - `points_count`: Total data points (same as vectors_count)

        **Errors:**
        - 404: Collection not found
        - 500: Connection error or service unavailable

        **Note:** Use this to verify collection configuration before inserting points.
        """
        return orchestrator.qdrant_service.get_collection_info(service_id, collection_name, timeout)
    
    @router.put("/vector-db/{service_id}/collections/{collection_name}")
    async def create_collection(service_id: str, collection_name: str, request: Request):
        """Create a new collection (vector index) in the vector database.

        Creates a new collection with specified vector dimensions and distance metric.
        Collections must be created before inserting points.

        **Path Parameters:**
        - `service_id`: SLURM job ID of the vector DB service
        - `collection_name`: Name for the new collection (must be unique)

        **Request Body:**
        - `vector_size` (required): Dimension of vectors (e.g., 384, 768, 1536)
            - Must match your embedding model's output dimension
            - Common sizes: 384 (sentence-transformers/all-MiniLM-L6-v2), 768 (BERT), 1536 (OpenAI)
        - `distance` (optional): Distance metric - "Cosine" (default), "Euclid", or "Dot"
            - **Cosine**: Most common, normalized similarity (0-2 range)
            - **Euclid**: Euclidean distance (good for spatial data)
            - **Dot**: Dot product (for pre-normalized vectors)
        - `timeout` (optional): Request timeout in seconds (default: 10)

        **Returns (Success):**
        ```json
        {
          "success": true,
          "message": "Collection 'my_documents' created successfully",
          "collection_name": "my_documents",
          "vector_size": 384,
          "distance": "Cosine"
        }
        ```

        **Returns (Already Exists):**
        ```json
        {
          "success": false,
          "error": "Collection 'my_documents' already exists"
        }
        ```

        **Example Request:**
        ```json
        {
          "vector_size": 384,
          "distance": "Cosine"
        }
        ```

        **Errors:**
        - 400: Missing vector_size or invalid parameters
        - 409: Collection already exists
        - 500: Database error or connection failure

        **Note:** Vector size cannot be changed after creation. Delete and recreate if needed.
        """
        data = await request.json()
        vector_size = data.get("vector_size")
        distance = data.get("distance", "Cosine")
        timeout = data.get("timeout", 10)
        if not vector_size:
            raise HTTPException(status_code=400, detail="vector_size required")
        return orchestrator.qdrant_service.create_collection(service_id, collection_name, vector_size, distance, timeout)
    
    @router.delete("/vector-db/{service_id}/collections/{collection_name}")
    async def delete_collection(service_id: str, collection_name: str, timeout: int = 10):
        """Delete a collection from the vector database.

        Permanently removes a collection and all its vectors. This operation cannot be undone.

        **Path Parameters:**
        - `service_id`: SLURM job ID of the vector DB service
        - `collection_name`: Name of the collection to delete

        **Query Parameters:**
        - `timeout`: Request timeout in seconds (default: 10)

        **Returns (Success):**
        ```json
        {
          "success": true,
          "message": "Collection 'my_documents' deleted successfully",
          "collection_name": "my_documents"
        }
        ```

        **Returns (Not Found):**
        ```json
        {
          "success": false,
          "error": "Collection 'my_documents' not found"
        }
        ```

        **Example:**
        ```bash
        curl -X DELETE "http://orchestrator:8000/api/data-plane/vector-db/3642875/collections/my_docs"
        ```
        """
        return orchestrator.qdrant_service.delete_collection(service_id, collection_name, timeout)
    
    @router.put("/vector-db/{service_id}/collections/{collection_name}/points")
    async def upsert_points(service_id: str, collection_name: str, request: Request):
        """Insert or update points (vectors with payloads) in a collection.

        Upserts vectors into the collection. If a point with the same ID exists, it will be updated.
        Otherwise, a new point is created.

        **Path Parameters:**
        - `service_id`: SLURM job ID of the vector DB service
        - `collection_name`: Name of the collection

        **Request Body:**
        - `points` (required): List of points to upsert, each with:
            - `id`: Unique identifier (integer or UUID string)
            - `vector`: Array of floats matching collection's vector_size
            - `payload` (optional): Metadata dict (any JSON-serializable data)
        - `timeout` (optional): Request timeout in seconds (default: 30)

        **Example Request:**
        ```json
        {
          "points": [
            {
              "id": 1,
              "vector": [0.1, 0.2, 0.3, 0.4, ...],
              "payload": {
                "text": "Example document",
                "category": "documentation",
                "timestamp": "2025-01-15T10:30:00"
              }
            },
            {
              "id": 2,
              "vector": [0.5, 0.6, 0.7, 0.8, ...],
              "payload": {"text": "Another document"}
            }
          ]
        }
        ```

        **Returns (Success):**
        ```json
        {
          "success": true,
          "message": "Upserted 2 points to collection 'my_documents'",
          "num_points": 2
        }
        ```

        **Errors:**
        - 400: Missing points or invalid format
        - 404: Collection not found
        - 500: Database error or vector dimension mismatch

        **Note:** IDs must be unique within collection. Duplicate IDs will overwrite existing points.
        """
        data = await request.json()
        points = data.get("points")
        timeout = data.get("timeout", 30)
        if not points:
            raise HTTPException(status_code=400, detail="points required")
        return orchestrator.qdrant_service.upsert_points(service_id, collection_name, points, timeout)
    
    @router.post("/vector-db/{service_id}/collections/{collection_name}/search")
    async def search_points(service_id: str, collection_name: str, request: Request):
        """Search for similar vectors in a collection (nearest neighbor search).

        Performs semantic similarity search to find vectors most similar to the query vector.
        Returns top-k most similar points with their scores and payloads.

        **Path Parameters:**
        - `service_id`: SLURM job ID of the vector DB service
        - `collection_name`: Name of the collection to search

        **Request Body:**
        - `query_vector` (required): The query vector to find similar items
            - Must be array of floats matching collection's vector_size
        - `limit` (optional): Maximum number of results (default: 10)
        - `timeout` (optional): Request timeout in seconds (default: 10)

        **Example Request:**
        ```json
        {
          "query_vector": [0.1, 0.2, 0.3, 0.4, ...],
          "limit": 5
        }
        ```

        **Returns (Success):**
        ```json
        {
          "success": true,
          "results": [
            {
              "id": 42,
              "score": 0.95,
              "payload": {
                "text": "Very similar document",
                "category": "documentation"
              }
            },
            {
              "id": 13,
              "score": 0.87,
              "payload": {"text": "Somewhat similar document"}
            }
          ],
          "num_results": 2
        }
        ```

        **Score Interpretation (Cosine distance):**
        - **1.0**: Identical vectors (perfect match)
        - **0.9-0.99**: Very high similarity
        - **0.7-0.89**: High similarity
        - **0.5-0.69**: Moderate similarity
        - **< 0.5**: Low similarity

        **Errors:**
        - 400: Missing query_vector or invalid format
        - 404: Collection not found or empty
        - 500: Database error or dimension mismatch

        **Note:** Returns fewer results if collection has fewer than `limit` points.
        """
        data = await request.json()
        query_vector = data.get("query_vector")
        limit = data.get("limit", 10)
        timeout = data.get("timeout", 10)
        if not query_vector:
            raise HTTPException(status_code=400, detail="query_vector required")
        return orchestrator.qdrant_service.search_points(service_id, collection_name, query_vector, limit, timeout)
    
    return router
