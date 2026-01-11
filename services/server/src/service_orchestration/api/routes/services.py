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
        """List all services managed by the orchestrator.

        Returns all services that were started through this API across all categories:
        - **vLLM services**: LLM inference services (recipe: "inference/vllm*")
        - **Vector database services**: Qdrant instances (recipe: "vector-db/*")

        **Returns:**
        - Array of service objects, each containing:
            - `id`: SLURM job ID (service identifier)
            - `name`: Service name (derived from recipe)
            - `status`: Current status (pending/building/starting/running/completed/failed/cancelled)
            - `recipe_name`: Recipe used to create the service
            - `config`: Resource configuration (nodes, cpus, memory, time, environment variables)
            - `created_at`: Service creation timestamp (ISO format)

        **Service Identification:**
        - Filter by `recipe_name` patterns to find specific service types
        - Example: `recipe_name.startswith("inference/vllm")` for vLLM services

        **Example Response:**
        ```json
        [
          {
            "id": "3642874",
            "name": "vllm-service",
            "status": "running",
            "recipe_name": "inference/vllm-single-node",
            "config": {"nodes": 1, "cpus": 4, "memory": "16G", "environment": {"VLLM_MODEL": "gpt2"}},
            "created_at": "2025-10-14T10:30:00"
          },
          {
            "id": "3642875",
            "name": "qdrant-service",
            "status": "running",
            "recipe_name": "vector-db/qdrant",
            "config": {"nodes": 1, "cpus": 2, "memory": "8G"},
            "created_at": "2025-10-14T11:00:00"
          }
        ]
        ```

        **Status Values:**
        - `pending`: Job queued in SLURM
        - `building`: Apptainer container image being built
        - `starting`: Container started, application initializing
        - `running`: Service fully operational and ready
        - `completed`: Service finished successfully
        - `failed`: Service encountered an error
        - `cancelled`: Service was stopped by user

        **Note:** Does not include unrelated SLURM jobs (other users' jobs, interactive sessions)
        """
        return orchestrator.list_services()
    
    @router.post("/start")
    async def start_service(request: Request):
        """Start a new service using SLURM + Apptainer.

        This endpoint submits a job to the SLURM cluster using a predefined recipe template.
        The service will be containerized using Apptainer and scheduled on compute nodes.

        **Request Body:**
        - `recipe_name` (required): Path to the recipe (e.g., "inference/vllm-single-node", "vector-db/qdrant")
        - `config` (optional): Configuration object with:
            - **SLURM resource requirements** (all optional, override recipe defaults):
                - `nodes`: Number of compute nodes (default: 1)
                - `resources`: Resource overrides object:
                    - `cpu`: Number of CPUs (e.g., "2", "8")
                    - `memory`: Memory per CPU (e.g., "8G", "16G", "32G")
                    - `time_limit`: Time limit in minutes (e.g., 15, 60, 120)
                    - `gpu`: GPU allocation (e.g., "1", "2", null for CPU-only)
            - **Environment variables** (all optional, override recipe defaults):
                - `environment`: Environment variable overrides:
                    - `VLLM_MODEL`: Model to load (e.g., "gpt2", "Qwen/Qwen2.5-0.5B-Instruct")
                    - `VLLM_MAX_MODEL_LEN`: Max sequence length
                    - `VLLM_GPU_MEMORY_UTILIZATION`: GPU memory fraction (0.0-1.0)
                    - Any other environment variables supported by the container

        **Examples:**

        Simple creation with defaults:
        ```json
        {
          "recipe_name": "inference/vllm-single-node"
        }
        ```

        Custom model:
        ```json
        {
          "recipe_name": "inference/vllm-single-node",
          "config": {
            "environment": {
              "VLLM_MODEL": "gpt2"
            }
          }
        }
        ```

        Custom model + resources:
        ```json
        {
          "recipe_name": "inference/vllm-single-node",
          "config": {
            "nodes": 1,
            "environment": {
              "VLLM_MODEL": "meta-llama/Llama-2-7b-chat-hf"
            },
            "resources": {
              "cpu": "8",
              "memory": "64G",
              "time_limit": 120,
              "gpu": "1"
            }
          }
        }
        ```

        **Returns:**
        - Service object with:
            - `id`: SLURM job ID (service identifier)
            - `name`: Service name
            - `status`: Initial status (typically "pending")
            - `recipe_name`: Recipe used
            - `config`: Applied configuration
            - `created_at`: ISO timestamp

        **Status Flow:**
        1. `pending`: Job queued in SLURM
        2. `building`: Apptainer container image being built
        3. `starting`: Container started, application initializing
        4. `running`: Service fully operational and ready

        **Errors:**
        - 400: Invalid recipe_name or configuration
        - 500: SLURM submission failed

        **Note:** Services run until time limit expires or manually stopped
        """
        data = await request.json()
        recipe_name = data.get("recipe_name")
        config = data.get("config", {})
        
        if not recipe_name:
            raise HTTPException(status_code=400, detail="recipe_name required")
        
        return orchestrator.start_service(recipe_name, config)
    
    @router.post("/stop/{service_id}")
    async def stop_service(service_id: str):
        """Stop a running service by cancelling its SLURM job.

        This endpoint cancels the SLURM job associated with the service, which will:
        1. Terminate the running container gracefully
        2. Free up allocated compute resources (CPUs, memory, GPUs)
        3. Mark the service as cancelled in SLURM

        **Path Parameters:**
        - `service_id`: The SLURM job ID of the service to stop

        **Returns:**
        - Success: `{"success": True, "message": "Service {service_id} stopped successfully"}`
        - Failure: `{"success": False, "error": "Service not found or already stopped"}`

        **Example Request:**
        ```bash
        curl -X POST http://orchestrator:8000/api/services/stop/3642874
        ```

        **Note:** This operation is immediate and cannot be undone. Service logs and metadata
        are preserved for post-mortem analysis.

        **Alternative:** For better metadata preservation (useful for Grafana integration),
        consider using status update endpoints if available.
        """
        return orchestrator.stop_service(service_id)
    
    @router.get("/{service_id}")
    async def get_service(service_id: str):
        """Get detailed information about a specific service or service group.

        Automatically detects whether the ID refers to an individual service or service group
        and returns appropriate details.

        **Path Parameters:**
        - `service_id`: SLURM job ID (individual service) or group name (e.g., "vllm-group-123")

        **For Individual Services:**
        Returns service details including:
        - `id`: SLURM job ID
        - `name`: Service name
        - `status`: Current status (pending/building/starting/running/failed/cancelled/completed)
        - `recipe_name`: Recipe used to create the service
        - `config`: Service configuration (resources, environment variables)
        - `created_at`: ISO timestamp

        **For Service Groups:**
        Returns group metadata and member services:
        - `group_id`: Group identifier
        - `recipe_name`: Recipe used for the group
        - `members`: Array of member services with their statuses and endpoints
        - `load_balancer`: Load balancing configuration (if applicable)
        - `total_replicas`, `healthy_replicas`, etc.
        - `created_at`: ISO timestamp

        **Example Response (Individual):**
        ```json
        {
          "id": "3642874",
          "name": "vllm-gpt2-3642874",
          "status": "running",
          "recipe_name": "inference/vllm-single-node",
          "config": {
            "environment": {"VLLM_MODEL": "gpt2"}
          },
          "created_at": "2024-01-15T10:30:00"
        }
        ```

        **Example Response (Group):**
        ```json
        {
          "group_id": "vllm-group-123",
          "recipe_name": "inference/vllm-replica-group",
          "members": [
            {"id": "3642874", "status": "running", "endpoint": "http://mel2133:8001"},
            {"id": "3642875", "status": "running", "endpoint": "http://mel2134:8001"}
          ],
          "total_replicas": 2,
          "healthy_replicas": 2,
          "load_balancer": {"type": "round_robin", "endpoint": "http://load-balancer:8000"},
          "created_at": "2024-01-15T10:30:00"
        }
        ```

        **Errors:**
        - 404: Service or group not found

        **Note:** Service groups are collections of replica services managed as a unit,
        useful for load balancing and high availability scenarios.
        """
        service = orchestrator.get_service(service_id)
        if service is None:
            raise HTTPException(status_code=404, detail=f"Service {service_id} not found")
        return service
    
    @router.get("/{service_id}/status")
    async def get_service_status(service_id: str):
        """Get the current detailed status of a service.

        This endpoint returns real-time status by checking both SLURM state and parsing
        log files to determine the exact stage of service initialization.

        **Path Parameters:**
        - `service_id`: The SLURM job ID of the service

        **Returns:**
        - Object with `status` field containing one of:
            - `pending`: Job waiting in SLURM queue for available resources
            - `building`: Apptainer container image being built
            - `starting`: Container launched, application initializing (e.g., vLLM loading model)
            - `running`: Service fully operational and ready to accept requests
            - `completed`: Service finished successfully (time limit reached or graceful shutdown)
            - `failed`: Service encountered an error during startup or runtime
            - `cancelled`: Service was manually stopped by user
            - `unknown`: Unable to determine status (check logs for details)

        **Example Response:**
        ```json
        {
          "status": "running"
        }
        ```

        **Status Detection Logic:**
        - Queries SLURM for job state (pending, running, completed, failed)
        - For running jobs, parses logs to detect:
            - Container build messages → "building"
            - Application startup messages → "starting"
            - Ready messages (e.g., "Uvicorn running") → "running"
        - Uses heuristics specific to service type (vLLM, Qdrant, etc.)

        **Note:** Status may be cached briefly. For the most up-to-date status,
        check logs endpoint directly.
        """
        return orchestrator.get_service_status(service_id)
    
    @router.get("/{service_id}/logs")
    async def get_service_logs(service_id: str):
        """Get SLURM logs (stdout and stderr) from a service.

        Retrieves the job output logs written by SLURM. These logs contain:
        - Container build output (Apptainer image creation)
        - Application startup messages
        - Runtime logs and errors
        - Container termination information

        **Path Parameters:**
        - `service_id`: The SLURM job ID of the service

        **Returns:**
        - Object with `logs` field containing the combined stdout/stderr output

        **Example Response:**
        ```json
        {
          "logs": "=== SLURM STDOUT ===\\nINFO:     Building Apptainer image from docker://vllm/vllm-openai:latest\\nINFO:     Container build complete\\nINFO:     Starting vLLM server...\\nINFO:     Model gpt2 loaded successfully\\nINFO:     Uvicorn running on http://0.0.0.0:8001\\n\\n=== SLURM STDERR ===\\n(no errors)"
        }
        ```

        **Log Structure:**
        - Logs are divided into `STDOUT` and `STDERR` sections
        - Container build progress shown first
        - Application startup sequence follows
        - Any errors appear in STDERR section

        **Common Log Patterns:**
        - vLLM: "Model ... loaded", "Uvicorn running on"
        - Qdrant: "Qdrant is ready", "REST API listening on"
        - Errors: "ERROR:", "FAILED:", "Exception:"

        **Troubleshooting:**
        - Check logs if service stuck in "starting" status
        - Look for "OOM" messages if service fails (out of memory)
        - Search for "ModuleNotFoundError" or "ImportError" for dependency issues

        **Note:** Logs may not be available immediately after job creation.
        They become available once the job starts running on a compute node.

        **File Location:** Logs are stored in SLURM's output directory as
        `<job_id>.out` and `<job_id>.err` files.
        """
        return orchestrator.get_service_logs(service_id)
    
    @router.get("/{service_id}/metrics")
    async def get_service_metrics(service_id: str):
        """Get Prometheus metrics from any service (auto-detects service type).
        
        This endpoint automatically determines the service type based on the
        service_id and routes to the appropriate metrics fetcher.
        
        Returns metrics in Prometheus text format for running services,
        or error information for services that are not ready.
        """
        from fastapi.responses import PlainTextResponse
        
        result = orchestrator.get_service_metrics(service_id)
        
        # If successful, return metrics as plain text
        if result.get("success"):
            return PlainTextResponse(
                content=result.get("metrics", ""),
                media_type="text/plain; version=0.0.4"
            )
        else:
            # Return error info (service not ready, not found, etc.)
            return result
    
    @router.post("/metrics/batch")
    async def get_batch_metrics(request: Request):
        """Get Prometheus metrics for multiple services in a single request.
        
        This endpoint reduces SSH tunnel contention by fetching metrics for
        multiple services in one HTTP request, instead of making separate
        requests per service.
        
        **Request Body:**
        - `service_ids` (required): List of service IDs to fetch metrics for
        - `timeout` (optional): Timeout per service in seconds (default: 5)
        
        **Returns:**
        - Dict mapping service_id to metrics result:
          - On success: {"success": true, "metrics": "<prometheus text>"}
          - On failure: {"success": false, "error": "<error message>"}
        
        **Example Request:**
        ```json
        {
          "service_ids": ["sg-3941996", "sg-3941997"],
          "timeout": 5
        }
        ```
        
        **Example Response:**
        ```json
        {
          "sg-3941996": {"success": true, "metrics": "# HELP..."},
          "sg-3941997": {"success": true, "metrics": "# HELP..."}
        }
        ```
        """
        body = await request.json()
        service_ids = body.get("service_ids", [])
        timeout = body.get("timeout", 5)
        
        if not service_ids:
            return {}
        
        return orchestrator.get_batch_metrics(service_ids, timeout=timeout)
    
    return router
