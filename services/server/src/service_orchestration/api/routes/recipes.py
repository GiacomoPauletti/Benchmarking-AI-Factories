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
        """List all available service recipes.

        Returns a catalog of all service recipes available for deployment. Recipes are
        pre-configured templates that define how to deploy specific types of services
        (vLLM, Qdrant, monitoring tools, etc.) with sensible defaults.

        **Returns:**
        Array of recipe objects, each containing:
        - `name`: Display name (e.g., "vLLM Inference Service")
        - `path`: Recipe identifier used in API calls (e.g., "inference/vllm-single-node")
        - `category`: Recipe category (inference, vector-db, monitoring, etc.)
        - `description`: Human-readable description of what the recipe does
        - `version`: Recipe version string
        - `default_config`: Default configuration values:
            - `nodes`: Default node count
            - `resources`: Default CPU, memory, GPU allocations
            - `environment`: Default environment variables
        - `required_params`: List of parameters that must be specified
        - `optional_params`: List of optional configuration parameters

        **Example Response:**
        ```json
        [
          {
            "name": "vLLM Single Node Inference",
            "path": "inference/vllm-single-node",
            "category": "inference",
            "description": "Deploy a single-node vLLM inference service with GPU support",
            "version": "1.0.0",
            "default_config": {
              "nodes": 1,
              "resources": {
                "cpu": "4",
                "memory": "16G",
                "gpu": "1",
                "time_limit": 60
              },
              "environment": {
                "VLLM_MODEL": "gpt2",
                "VLLM_PORT": "8001"
              }
            },
            "required_params": [],
            "optional_params": ["VLLM_MODEL", "VLLM_MAX_MODEL_LEN", "VLLM_GPU_MEMORY_UTILIZATION"]
          },
          {
            "name": "vLLM Replica Group",
            "path": "inference/vllm-replicas",
            "category": "inference",
            "description": "Deploy multiple vLLM replicas for load balancing",
            "version": "1.0.0",
            "default_config": {
              "nodes": 2,
              "replicas_per_node": 2,
              "resources": {
                "cpu": "8",
                "memory": "32G",
                "gpu": "4",
                "time_limit": 120
              }
            }
          },
          {
            "name": "Qdrant Vector Database",
            "path": "vector-db/qdrant",
            "category": "vector-db",
            "description": "Deploy a Qdrant vector database instance",
            "version": "1.0.0",
            "default_config": {
              "nodes": 1,
              "resources": {
                "cpu": "2",
                "memory": "8G",
                "time_limit": 120
              },
              "environment": {
                "QDRANT_PORT": "6333"
              }
            }
          }
        ]
        ```

        **Recipe Categories:**
        - `inference`: LLM inference services (vLLM, etc.)
        - `vector-db`: Vector databases (Qdrant, Chroma, etc.)
        - `monitoring`: Observability tools (Grafana, Prometheus, Loki)
        - `custom`: Custom containerized services

        **Using Recipes:**
        1. List recipes to find the `path` you need
        2. Review `default_config` to understand defaults
        3. Create service with `POST /services/start`:
           ```json
           {
             "recipe_name": "inference/vllm-single-node",
             "config": {
               "environment": {"VLLM_MODEL": "meta-llama/Llama-2-7b-chat-hf"}
             }
           }
           ```
        4. Override any default values in the `config` object

        **Recipe Configuration:**
        - Recipes provide sensible defaults for quick deployment
        - All default values can be overridden in service creation
        - Resource limits prevent accidental over-allocation
        - Environment variables configure application behavior

        **Adding Custom Recipes:**
        - Place recipe files in the recipes directory
        - Follow the recipe template format
        - Include SLURM batch script and default configuration
        - Recipe path = relative path from recipes root

        **Note:** Recipes are loaded from the file system at orchestrator startup.
        To add new recipes, place them in the recipes directory and restart the orchestrator.
        """
        return orchestrator.list_recipes()
    
    return router
