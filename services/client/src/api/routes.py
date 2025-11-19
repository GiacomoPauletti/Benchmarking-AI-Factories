"""
Client Service API Routes

Unified API endpoints for managing client groups and monitoring.

The service provides endpoints to:
- Create/delete client groups
- Query group status  
- Trigger group execution
- Sync logs
- Expose Prometheus metrics

A separate benchmark orchestrator service should use this client service
(along with the server service) to coordinate benchmark runs.

For backward compatibility, URL paths use `/client-groups/{group_id}` where
group_id is a unique integer identifier for the client group.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Body
from fastapi.responses import PlainTextResponse
from typing import Dict, Any, List
import logging
import time
import os

from client_manager.client_manager import ClientManager, ClientManagerResponseStatus
from api.schemas import (
    CreateClientGroupRequest,
    RegisterObserverRequest,
    ClientGroupResponse,
    ClientGroupListResponse,
    ClientGroupInfoResponse,
    RunClientGroupResponse,
    ObserverRegistrationResponse,
    HealthResponse,
    MetricsTarget,
    ErrorResponse,
    LogSyncResponse
)

# Configure module logger
logger = logging.getLogger("client_service.api.routes")
logger.addHandler(logging.NullHandler())

router = APIRouter()

# Service start time for uptime calculation
_start_time = time.time()


# ==================== Dependency Injection ====================

def get_client_manager() -> ClientManager:
    """Get the ClientManager singleton instance."""
    return ClientManager()


# ==================== Health & Status Endpoints ====================

# @router.get(
#     "/health",
#     response_model=HealthResponse,
#     summary="Health check endpoint",
#     tags=["System"]
# )
# async def health_check():
#     """Check the health status of the Client Service.
    
#     Returns service health, version, and uptime information.
    
#     **Returns:**
#     ```json
#     {
#       "status": "healthy",
#       "version": "1.0.0",
#       "uptime": 3600.5
#     }
#     ```
#     """
#     return {
#         "status": "healthy",
#         "version": "1.0.0",
#         "uptime": time.time() - _start_time
#     }


# ==================== Client Group Management ====================

@router.post(
    "/client-groups",
    response_model=ClientGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new client group",
    tags=["Client Groups"],
    responses={
        201: {"description": "Client group created successfully"}
    }
)
async def create_client_group(
    payload: CreateClientGroupRequest = Body(
        ...,
        examples={
            "small": {
                "summary": "Small test group",
                "description": "Low-rate load test with 2 clients",
                "value": {
                    "target_url": "http://mel2133:8001",
                    "num_clients": 2,
                    "requests_per_second": 0.5,
                    "duration_seconds": 60,
                    "prompts": ["What is AI?", "Explain machine learning."],
                    "max_tokens": 50,
                    "time_limit": 10
                }
            },
            "medium": {
                "summary": "Medium load test",
                "description": "Moderate load with 10 clients",
                "value": {
                    "target_url": "http://mel2133:8001",
                    "num_clients": 10,
                    "requests_per_second": 10.0,
                    "duration_seconds": 300,
                    "prompts": ["Tell me a story.", "Write a poem.", "Explain quantum computing."],
                    "max_tokens": 100,
                    "time_limit": 15
                }
            },
            "large": {
                "summary": "Large stress test",
                "description": "High load with 100 clients",
                "value": {
                    "target_url": "http://mel2133:8001",
                    "num_clients": 100,
                    "requests_per_second": 100.0,
                    "duration_seconds": 600,
                    "prompts": ["What is AI?", "Explain machine learning.", "Tell me about neural networks."],
                    "max_tokens": 200,
                    "time_limit": 20
                }
            }
        }
    ),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Create a new client group for load testing.
    
    A client group represents a local process that will spawn multiple concurrent clients
    to send requests to AI inference services. The service automatically generates a unique
    group ID and returns it in the response.
    
    **Request Body:**
    - `target_url`: vLLM endpoint URL (e.g., "http://mel2133:8001")
    - `num_clients`: Number of concurrent clients (1-10000)
    - `requests_per_second`: Target RPS across all clients (e.g., 10.0)
    - `duration_seconds`: Load test duration (e.g., 60)
    - `prompts`: List of prompts to randomly select from
    - `max_tokens`: Maximum tokens per request (default: 100)
    - `temperature`: Sampling temperature (default: 0.7)
    - `model`: Model name (optional, uses server default)
    - `time_limit`: Process time limit in minutes (default: 30)
    
    **Returns (Success):**
    ```json
    {
      "status": "created",
      "group_id": 12345,
      "num_clients": 10,
      "message": "Load generator process started targeting http://mel2133:8001"
    }
    ```
    
    **Example:**
    ```bash
    curl -X POST "http://localhost:8002/api/v1/client-groups" \\
      -H "Content-Type: application/json" \\
      -d '{
        "target_url": "http://mel2133:8001",
        "num_clients": 5,
        "requests_per_second": 2.0,
        "duration_seconds": 60,
        "prompts": ["What is AI?", "Explain machine learning."],
        "max_tokens": 50,
        "time_limit": 10
      }'
    ```
    
    **Workflow:**
    1. Client Service generates a unique group ID
    2. Validates the request
    3. Creates a ClientGroup object with load test configuration
    4. Starts a local Python process to run the load generator
    5. Load generator sends requests to target vLLM endpoint
    6. Results are saved to logs directory
    7. Returns immediately with the group ID (process runs asynchronously)
    
    **Note:** The load test runs asynchronously. Use `GET /client-groups/{group_id}`
    to check status and retrieve results after completion.
    """
    # Generate unique group ID
    import time
    group_id = int(time.time() * 1000) % 1000000  # Millisecond timestamp mod 1M
    
    logger.debug(f"Creating client group {group_id} for load testing {payload.target_url}")
    
    # Convert payload to dict for storage
    load_config = payload.dict()
    
    res = client_manager.add_client_group(group_id, load_config)
    
    if res == ClientManagerResponseStatus.ALREADY_EXISTS:
        # Unlikely with timestamp-based ID, but handle it
        logger.warning(f"Client group {group_id} already exists, regenerating ID")
        group_id = (group_id + 1) % 1000000
        res = client_manager.add_client_group(group_id, load_config)
    
    if res == ClientManagerResponseStatus.ERROR:
        logger.error(f"Failed to create client group {group_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create client group. Check configuration and system resources."
        )
    
    logger.info(f"Created client group {group_id}: {payload.num_clients} clients @ {payload.requests_per_second} RPS")
    return {
        "status": "created",
        "group_id": group_id,
        "num_clients": payload.num_clients,
        "message": f"Load generator process started targeting {payload.target_url}"
    }


@router.get(
    "/client-groups",
    response_model=ClientGroupListResponse,
    summary="List all client groups",
    tags=["Client Groups"]
)
async def list_client_groups(client_manager: ClientManager = Depends(get_client_manager)):
    """List all active client groups.
    
    Returns a list of benchmark IDs for all currently managed client groups.
    
    **Returns:**
    ```json
    {
      "groups": [12345, 12346, 12347],
      "count": 3
    }
    ```
    
    **Example:**
    ```bash
    curl http://localhost:8002/api/v1/client-groups
    ```
    """
    groups = client_manager.list_groups()
    return {
        "groups": groups,
        "count": len(groups)
    }


@router.get(
    "/client-groups/{group_id}",
    response_model=ClientGroupInfoResponse,
    summary="Get client group information",
    tags=["Client Groups"],
    responses={
        200: {"description": "Client group information retrieved"},
        404: {"description": "Client group not found", "model": ErrorResponse}
    }
)
async def get_client_group_info(
    group_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Get detailed information about a specific client group.
    
    Returns the number of clients, registration status, and client process address.
    
    **Path Parameters:**
    - `group_id`: Unique identifier for the client group
    
    **Returns (Success):**
    ```json
    {
      "group_id": 12345,
      "info": {
        "num_clients": 100,
        "client_address": "http://mel2079:8000",
        "created_at": 1699999999.123,
        "status": "running"
      }
    }
    ```
    
    **Returns (Not Found):**
    ```json
    {
      "detail": "Client group not found",
      "status_code": 404
    }
    ```
    
    **Example:**
    ```bash
    curl http://localhost:8002/api/v1/client-groups/12345
    ```
    
    **Status Values:**
    - `pending`: Process starting, waiting for initialization
    - `running`: Client process running and executing load test
    - `stopped`: Client group has completed or been terminated
    """
    info = client_manager.get_group_info(group_id)
    
    if info is None:
        logger.debug(f"Client group {group_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client group not found"
        )
    
    return {
        "group_id": group_id,
        "info": info
    }


@router.delete(
    "/client-groups/{group_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a client group",
    tags=["Client Groups"]
)
async def delete_client_group(
    group_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Remove a client group and stop its associated process.
    
    **Path Parameters:**
    - `group_id`: Unique identifier for the client group
    
    **Returns:**
    ```json
    {
      "status": "deleted",
      "group_id": 12345
    }
    ```
    
    **Example:**
    ```bash
    curl -X DELETE http://localhost:8002/api/v1/client-groups/12345
    ```
    
    **Note:** This removes the group from the Client Service's tracking.
    The load generator process will continue running until completion or manual termination.
    """
    logger.debug(f"Deleting client group {group_id}")
    client_manager.remove_client_group(group_id)
    logger.info(f"Deleted client group {group_id}")
    
    return {
        "status": "deleted",
        "group_id": group_id
    }


# ==================== Client Group Execution ====================

@router.post(
    "/client-groups/{group_id}/run",
    response_model=RunClientGroupResponse,
    summary="Trigger client group to start load test",
    tags=["Execution"],
    responses={
        200: {"description": "Load test triggered successfully"},
        404: {"description": "Client group not found or not ready", "model": ErrorResponse},
        500: {"description": "Internal error during execution", "model": ErrorResponse}
    }
)
async def run_client_group(
    group_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Trigger a registered client group to start sending requests.
    
    This endpoint forwards the run command to the client process(es) that were spawned
    by the load generator. The client processes will then start sending concurrent requests
    to the configured AI services.
    
    **Path Parameters:**
    - `group_id`: Unique identifier for the client group
    
    **Returns (Success):**
    ```json
    {
      "status": "dispatched",
      "group_id": 12345,
      "results": [
        {
          "client_process": "http://mel2079:8000",
          "status_code": 200,
          "body": "Started 100 clients"
        }
      ]
    }
    ```
    
    **Returns (Not Ready):**
    ```json
    {
      "detail": "Client process not registered yet. Wait for process to start.",
      "status_code": 404
    }
    ```
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8002/api/v1/client-groups/12345/run
    ```
    
    **Workflow:**
    1. Client Service looks up the registered client process address
    2. Forwards POST /run request to the client process
    3. Client process spawns configured number of client threads
    4. Each client thread starts sending requests to AI services
    5. Metrics are collected and exposed via Prometheus
    
    **Note:** The client process must be in "running" status (registered) before
    this endpoint will work. Check status with `GET /client-groups/{group_id}`.
    """
    logger.debug(f"Run request for client group {group_id}")
    
    try:
        results = client_manager.run_client_group(group_id)
    except ValueError as e:
        logger.warning(f"Run failed for unknown client group {group_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Unexpected error while running client group {group_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    
    logger.info(f"Dispatched run to client group {group_id}: {len(results)} client(s) responded")
    return {
        "status": "dispatched",
        "group_id": group_id,
        "results": results
    }


# ==================== Monitoring & Metrics ====================

@router.get(
    "/client-groups/targets",
    response_model=List[MetricsTarget],
    summary="Get Prometheus scrape targets for all client groups",
    tags=["Monitoring"]
)
async def get_client_group_targets(client_manager: ClientManager = Depends(get_client_manager)):
    """Get Prometheus scrape targets for all managed client groups.
    
    This endpoint returns a list of Prometheus scrape targets for running client processes.
    Use this to dynamically configure Prometheus to monitor all active client groups.
    
    **Returns:**
    ```json
    [
      {
        "targets": ["mel2079:8000"],
        "labels": {
          "job": "client-group-12345",
          "group_id": "12345",
          "num_clients": "100",
          "status": "running"
        }
      },
      {
        "targets": ["mel2080:8000"],
        "labels": {
          "job": "client-group-12346",
          "group_id": "12346",
          "num_clients": "50",
          "status": "running"
        }
      }
    ]
    ```
    
    **Integration with Prometheus:**
    Save this output to a file and configure Prometheus file-based service discovery:
    
    ```yaml
    # prometheus.yml
    scrape_configs:
      - job_name: 'client-groups'
        file_sd_configs:
          - files:
            - 'targets/client_groups.json'
        refresh_interval: 30s
    ```
    
    Update the file periodically:
    ```bash
    curl http://localhost:8002/api/v1/client-groups/targets > targets/client_groups.json
    ```
    
    **Example:**
    ```bash
    curl http://localhost:8002/api/v1/client-groups/targets
    ```
    """
    targets = []
    
    for group_id in client_manager.list_groups():
        info = client_manager.get_group_info(group_id)
        if info and info.get("client_address"):
            # Extract host:port from http://host:port format
            client_addr = info["client_address"]
            if client_addr.startswith("http://"):
                client_addr = client_addr[7:]  # Remove http://
            elif client_addr.startswith("https://"):
                client_addr = client_addr[8:]  # Remove https://
            
            targets.append({
                "targets": [client_addr],
                "labels": {
                    "job": f"client-group-{group_id}",
                    "group_id": str(group_id),
                    "num_clients": str(info.get("num_clients", "unknown")),
                    "status": info.get("status", "unknown")
                }
            })
    
    return targets


@router.get(
    "/client-groups/{group_id}/metrics",
    summary="Get Prometheus metrics from a client group",
    tags=["Monitoring"],
    responses={
        200: {
            "description": "Metrics in Prometheus text format",
            "content": {"text/plain": {"example": "# HELP client_requests_total Total requests sent\\n# TYPE client_requests_total counter\\nclient_requests_total 1500\\n"}}
        },
        404: {"description": "Client group not found or not ready", "model": ErrorResponse}
    }
)
async def get_client_group_metrics(
    group_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Get Prometheus-compatible metrics from a specific client group.
    
    This endpoint proxies the /metrics endpoint from the client process running on HPC.
    Client processes expose metrics about requests sent, latencies, errors, and more.
    
    **Path Parameters:**
    - `group_id`: Unique identifier for the client group
    
    **Available Metrics (typical):**
    - `client_requests_total` - Total number of requests sent
    - `client_requests_success` - Number of successful requests
    - `client_requests_failed` - Number of failed requests
    - `client_latency_seconds` - Request latency histogram
    - `client_tokens_per_second` - Throughput in tokens/second
    - `client_active_connections` - Number of active client threads
    
    **Returns (Success):**
    - Content-Type: `text/plain; version=0.0.4`
    - Body: Prometheus text format metrics
    
    **Example Success Response:**
    ```
    # HELP client_requests_total Total requests sent by clients
    # TYPE client_requests_total counter
    client_requests_total{group_id="12345"} 1500.0
    # HELP client_latency_seconds Request latency distribution
    # TYPE client_latency_seconds histogram
    client_latency_seconds_bucket{le="0.1"} 800
    client_latency_seconds_bucket{le="0.5"} 1200
    client_latency_seconds_bucket{le="1.0"} 1450
    client_latency_seconds_bucket{le="+Inf"} 1500
    client_latency_seconds_sum 456.7
    client_latency_seconds_count 1500
    ```
    
    **Returns (Not Ready):**
    ```json
    {
      "detail": "Client process not registered yet",
      "status_code": 404
    }
    ```
    
    **Integration with Prometheus:**
    Use the `/client-groups/targets` endpoint for automatic discovery, or configure manually:
    
    ```yaml
    scrape_configs:
      - job_name: 'client-group-12345'
        static_configs:
          - targets: ['localhost:8002']
        metrics_path: '/api/v1/client-groups/12345/metrics'
        scrape_interval: 15s
    ```
    
    **Example:**
    ```bash
    curl http://localhost:8002/api/v1/client-groups/12345/metrics
    ```
    
    **Note:** Metrics are collected from the actual client process running on HPC.
    If the client process hasn't registered yet, this endpoint will return 404.
    """
    import requests
    
    info = client_manager.get_group_info(group_id)
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client group not found"
        )
    
    client_addr = info.get("client_address")
    if not client_addr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client process not registered yet. Wait for process to start."
        )
    
    # Proxy metrics request to the client process
    try:
        metrics_url = f"{client_addr.rstrip('/')}/metrics"
        response = requests.get(metrics_url, timeout=10)
        
        if response.status_code == 200:
            return PlainTextResponse(
                content=response.text,
                media_type="text/plain; version=0.0.4"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Client process returned status {response.status_code}"
            )
    except requests.RequestException as e:
        logger.error(f"Failed to fetch metrics from {client_addr}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to connect to client process: {str(e)}"
        )


# ==================== Log Management ====================

@router.get(
    "/client-groups/{group_id}/logs",
    summary="Get logs for a client group",
    tags=["Logs"],
    responses={
        200: {"description": "Logs retrieved successfully"},
        404: {"description": "Client group not found", "model": ErrorResponse}
    }
)
async def get_group_logs(
    group_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Get logs (stdout and stderr) from a client group's load generator process.
    
    Retrieves the process output logs. These logs contain:
    - Process execution details
    - Load test output and statistics
    - Any errors or warnings
    
    **Path Parameters:**
    - `group_id`: Unique identifier for the client group
    
    **Returns:**
    ```json
    {
      "logs": "=== STDOUT ===\\nStarting load test...\\n\\n=== STDERR ===\\n..."
    }
    ```
    
    **Example:**
    ```bash
    curl http://localhost:8002/api/v1/client-groups/500008/logs
    ```
    """
    logger.debug(f"Fetching logs for client group {group_id}")
    
    group = client_manager.get_group_info(group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client group {group_id} not found"
        )
    
    job_id = group.get("job_id")
    if not job_id:
        return {"logs": "=== NO JOB ID ===\nProcess not yet started or job ID not available"}
    
    # Get the dispatcher to fetch logs
    groups = client_manager.list_groups()
    if not groups:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No client groups available"
        )
    
    any_group_info = client_manager.get_group_info(group_id)
    if not any_group_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client group {group_id} not found"
        )
    
    # Create a temporary dispatcher to fetch logs
    from deployment.client_dispatcher import LocalClientDispatcher
    dispatcher = LocalClientDispatcher(
        load_config=any_group_info.get("load_config", {})
    )
    
    logs = dispatcher.get_job_logs(job_id, group_id)
    return {"logs": logs}


@router.post(
    "/client-groups/{group_id}/logs/sync",
    response_model=LogSyncResponse,
    summary="Sync logs for a client group",
    tags=["Logs"],
    responses={
        200: {"description": "Logs synced successfully"},
        404: {"description": "Client group not found", "model": ErrorResponse}
    }
)
async def sync_group_logs(
    group_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Sync process logs to local directory for a specific client group.
    
    This endpoint copies log files from the process output to the local `./logs` directory.
    
    **Path Parameters:**
    - `group_id`: Unique identifier for the client group
    
    **Returns (Success):**
    ```json
    {
      "success": true,
      "message": "Logs synced successfully",
      "local_path": "./logs",
      "group_id": 12345
    }
    ```
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8002/api/v1/client-groups/12345/logs/sync
    ```
    
    **Log Files:**
    - Pattern: `loadgen-{group_id}.out`
    - Pattern: `loadgen-{group_id}.err`
    - Location: `./logs/` directory
    """
    logger.info(f"Syncing logs for client group {group_id}")
    
    result = client_manager.sync_logs(group_id=group_id)
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"]
        )
    
    return result


@router.post(
    "/logs/sync",
    response_model=LogSyncResponse,
    summary="Sync all logs from local processes",
    tags=["Logs"]
)
async def sync_all_logs(client_manager: ClientManager = Depends(get_client_manager)):
    """Sync all process logs to local directory.
    
    Copies logs for all client groups to the local directory.
    
    **Returns:**
    ```json
    {
      "success": true,
      "message": "Logs synced successfully",
      "local_path": "./logs",
      "benchmark_id": "all",
      "groups": [12345, 12346, 12347]
    }
    ```
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8002/api/v1/logs/sync
    ```
    
    **Synced Files:**
    - All files matching `loadgen-*.out` and `loadgen-*.err`
    - Synced to local `./logs/` directory
    
    **Use Cases:**
    - Debugging failed jobs
    - Collecting performance data
    - Post-mortem analysis
    - Archiving benchmark results
    """
    logger.info("Syncing all logs")
    
    result = client_manager.sync_logs(group_id=None)
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"]
        )
    
    return result