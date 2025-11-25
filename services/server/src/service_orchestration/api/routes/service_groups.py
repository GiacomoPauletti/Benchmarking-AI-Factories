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
        """List all service groups with summary information.

        Returns summary information for all service groups (collections of replica services).
        Service groups are typically created when deploying services with multiple replicas for
        load balancing or high availability.

        **Returns:**
        Array of service group summaries, each containing:
        - `id`: Group identifier (e.g., "sg-ba5f6e2462fb")
        - `type`: Group type (typically "replica_group")
        - `recipe_name`: Recipe used to create the group (e.g., "inference/vllm-replicas")
        - `total_replicas`: Total number of replicas in the group
        - `healthy_replicas`: Number of replicas with status "running"
        - `starting_replicas`: Number of replicas still initializing
        - `pending_replicas`: Number of replicas waiting in SLURM queue
        - `failed_replicas`: Number of replicas that failed to start
        - `created_at`: ISO timestamp of group creation

        **Example Response:**
        ```json
        [
          {
            "id": "sg-ba5f6e2462fb",
            "type": "replica_group",
            "recipe_name": "inference/vllm-replicas",
            "total_replicas": 4,
            "healthy_replicas": 3,
            "starting_replicas": 1,
            "pending_replicas": 0,
            "failed_replicas": 0,
            "created_at": "2025-11-10T12:00:00"
          },
          {
            "id": "sg-c7d8e3f94a51",
            "type": "replica_group",
            "recipe_name": "inference/vllm-replicas",
            "total_replicas": 2,
            "healthy_replicas": 2,
            "starting_replicas": 0,
            "pending_replicas": 0,
            "failed_replicas": 0,
            "created_at": "2025-11-10T13:30:00"
          }
        ]
        ```

        **Health Status Interpretation:**
        - **All healthy**: All replicas running, group fully operational
        - **Some starting**: Group partially available, more capacity coming online
        - **Some pending**: Waiting for cluster resources
        - **Some failed**: Group degraded, may need intervention

        **Use Cases:**
        - Monitor multiple deployed replica groups
        - Check overall health before load balancing
        - Identify groups needing attention

        **Note:** Empty array means no service groups exist (individual services only).
        """
        return orchestrator.list_service_groups()
    
    @router.get("/{group_id}")
    async def get_service_group(group_id: str):
        """Get detailed information about a service group and all its replicas.

        Service groups are collections of replica services that share a common group_id.
        This endpoint aggregates information from all replicas in the group, providing
        a complete view of the group's composition and health.

        **Path Parameters:**
        - `group_id`: The service group ID (e.g., "sg-ba5f6e2462fb")

        **Returns:**
        Detailed group object containing:
        - `id`: Group identifier
        - `type`: Group type (typically "replica_group")
        - `recipe_name`: Recipe used (e.g., "inference/vllm-replicas")
        - `replicas`: Array of replica details:
            - `id`: Replica ID (format: "job_id:port")
            - `name`: Replica name
            - `status`: Current status (pending/building/starting/running/failed)
            - `port`: Service port number
            - `gpu_id`: Assigned GPU ID (if applicable)
            - `replica_index`: Position in group (0-based)
            - `job_id`: SLURM job ID
            - `endpoint`: HTTP endpoint URL (if available)
        - `total_replicas`: Total replica count
        - `healthy_replicas`: Number of running replicas
        - `starting_replicas`: Number initializing
        - `pending_replicas`: Number queued
        - `failed_replicas`: Number failed
        - `base_port`: Starting port number for replicas
        - `node_jobs`: Array of SLURM jobs, each containing:
            - `job_id`: SLURM job ID
            - `node_index`: Node position in group
            - `replicas`: Replicas on this node
        - `created_at`: ISO timestamp

        **Example Response:**
        ```json
        {
          "id": "sg-ba5f6e2462fb",
          "type": "replica_group",
          "recipe_name": "inference/vllm-replicas",
          "replicas": [
            {
              "id": "3713894:8001",
              "name": "vllm-replicas-3713894-replica-0",
              "status": "running",
              "port": 8001,
              "gpu_id": 0,
              "replica_index": 0,
              "job_id": "3713894",
              "endpoint": "http://mel2133:8001"
            },
            {
              "id": "3713894:8002",
              "name": "vllm-replicas-3713894-replica-1",
              "status": "starting",
              "port": 8002,
              "gpu_id": 1,
              "replica_index": 1,
              "job_id": "3713894",
              "endpoint": "http://mel2133:8002"
            }
          ],
          "total_replicas": 2,
          "healthy_replicas": 1,
          "starting_replicas": 1,
          "pending_replicas": 0,
          "failed_replicas": 0,
          "base_port": 8001,
          "node_jobs": [
            {
              "job_id": "3713894",
              "node_index": 0,
              "replicas": [...]
            }
          ],
          "created_at": "2025-11-10T12:00:00"
        }
        ```

        **Replica Status Flow:**
        1. `pending`: Queued in SLURM
        2. `building`: Container being built
        3. `starting`: Loading models/initializing
        4. `running`: Ready to serve requests
        5. `failed`: Encountered error

        **Use Cases:**
        - Check which replicas are ready for load balancing
        - Identify failed replicas needing restart
        - Monitor group-wide deployment progress
        - Get endpoints for direct replica access

        **Errors:**
        - 404: Service group not found (no services with this group_id)

        **Note:** Individual replicas within a group share the same model/configuration
        but run on different ports or nodes for load distribution.
        """
        group = orchestrator.get_service_group(group_id)
        if group is None:
            raise HTTPException(status_code=404, detail=f"Service group {group_id} not found")
        return group
    
    @router.get("/{group_id}/status")
    async def get_service_group_status(group_id: str):
        """Get aggregated status summary of a service group.

        Returns a summary of the group's overall health and replica statuses without
        full replica details. Use this for quick health checks and monitoring.

        **Path Parameters:**
        - `group_id`: The service group ID (e.g., "sg-ba5f6e2462fb")

        **Returns:**
        Status summary object containing:
        - `group_id`: Group identifier
        - `overall_status`: Aggregated health status (see values below)
        - `total_replicas`: Total number of replicas
        - `healthy_replicas`: Number with status "running"
        - `starting_replicas`: Number still initializing
        - `pending_replicas`: Number waiting in queue
        - `failed_replicas`: Number that failed
        - `replica_statuses`: Array of minimal replica status objects:
            - `id`: Replica ID
            - `status`: Current status

        **Example Response:**
        ```json
        {
          "group_id": "sg-ba5f6e2462fb",
          "overall_status": "healthy",
          "total_replicas": 4,
          "healthy_replicas": 4,
          "starting_replicas": 0,
          "pending_replicas": 0,
          "failed_replicas": 0,
          "replica_statuses": [
            {"id": "3713894:8001", "status": "running"},
            {"id": "3713894:8002", "status": "running"},
            {"id": "3713894:8003", "status": "running"},
            {"id": "3713894:8004", "status": "running"}
          ]
        }
        ```

        **Overall Status Values:**
        - `healthy`: All replicas are running (100% availability)
        - `partial`: Some replicas running, others starting/pending (reduced capacity)
        - `starting`: All replicas are starting or pending (0% availability)
        - `failed`: All replicas have failed (0% availability, requires intervention)
        - `degraded`: Some replicas failed, others running (reduced capacity with failures)

        **Status Interpretation for Load Balancing:**
        - **healthy**: Use all replicas, full capacity
        - **partial**: Use running replicas only, degraded performance
        - **starting**: Wait for replicas to become ready
        - **degraded**: Use running replicas, investigate failures
        - **failed**: Group non-functional, troubleshoot or recreate

        **Use Cases:**
        - Health checks for monitoring systems
        - Load balancer health probes
        - Autoscaling decisions
        - Alert triggering (e.g., when failed_replicas > 0)

        **Polling Recommendations:**
        - During deployment: Poll every 10-30 seconds
        - Production monitoring: Poll every 1-5 minutes
        - Health endpoint is lightweight (< 100ms response)

        **Errors:**
        - 404: Service group not found

        **Note:** For detailed replica information (endpoints, GPU IDs, etc.),
        use GET /{group_id} instead.
        """
        status = orchestrator.get_service_group_status(group_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Service group {group_id} not found")
        return status
    
    @router.post("/{group_id}/stop")
    async def stop_service_group(group_id: str):
        """Stop all replicas in a service group.

        This endpoint cancels all SLURM jobs associated with the service group,
        stopping all replicas at once. This is the recommended way to tear down
        a replica group rather than stopping individual replicas.

        **Path Parameters:**
        - `group_id`: The service group ID (e.g., "sg-ba5f6e2462fb")

        **Returns (Success):**
        ```json
        {
          "success": true,
          "message": "Service group sg-ba5f6e2462fb stopped successfully",
          "group_id": "sg-ba5f6e2462fb",
          "replicas_stopped": 4,
          "jobs_cancelled": ["3713894", "3713895"]
        }
        ```

        **Returns (Not Found):**
        ```json
        {
          "success": false,
          "error": "Service group 'sg-ba5f6e2462fb' not found"
        }
        ```

        **Returns (Partial Failure):**
        ```json
        {
          "success": false,
          "error": "Failed to stop some replicas",
          "group_id": "sg-ba5f6e2462fb",
          "replicas_stopped": 3,
          "replicas_failed": 1,
          "failed_jobs": ["3713895"]
        }
        ```

        **Operation Details:**
        1. Identifies all SLURM jobs in the group
        2. Cancels each job (sends SIGTERM to containers)
        3. Frees compute resources (CPUs, memory, GPUs)
        4. Marks replicas as cancelled in SLURM

        **What Gets Stopped:**
        - All replica containers on all nodes
        - All associated SLURM jobs
        - Load balancer (if configured)
        - Port allocations released

        **What Gets Preserved:**
        - Service metadata and configuration
        - SLURM log files (stdout/stderr)
        - Group ID and creation history
        - Useful for post-mortem analysis

        **Example Request:**
        ```bash
        curl -X POST http://orchestrator:8000/api/service-groups/sg-ba5f6e2462fb/stop
        ```

        **Errors:**
        - 404: Service group not found (may already be stopped)
        - 500: Failed to stop one or more replicas

        **Warning:** This operation is immediate and cannot be undone. All replicas
        will be terminated gracefully (SIGTERM followed by SIGKILL if needed).

        **Note:** Individual replicas cannot be stopped separately - the entire group
        is managed as a unit. To reduce replicas, recreate the group with fewer replicas.

        **Recovery:** To restart a stopped group, you must create a new service group
        using the same recipe and configuration.
        """
        result = orchestrator.stop_service_group(group_id)
        
        # Normalize response format for consistency
        # Orchestrator returns {"status": "error"|"success"|"partial", ...}
        # Convert to {"success": bool, ...} format expected by clients
        if isinstance(result, dict):
            status = result.get("status")
            if status == "error":
                return {
                    "success": False,
                    "error": result.get("message", "Unknown error"),
                    "group_id": group_id
                }
            elif status in ("success", "partial"):
                return {
                    "success": True,
                    "message": result.get("message"),
                    "group_id": result.get("group_id", group_id),
                    "replicas_stopped": result.get("stopped", 0),
                    "jobs_cancelled": list(result.get("stopped_jobs", [])) if "stopped_jobs" in result else []
                }
        
        return result
    
    return router
