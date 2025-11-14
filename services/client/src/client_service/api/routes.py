"""
Client Service API Routes

Unified API endpoints for managing client groups and monitoring.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Body
from fastapi.responses import PlainTextResponse
from typing import Dict, Any, List
import logging
import time

from client_service.client_manager.client_manager import ClientManager, ClientManagerResponseStatus
from client_service.api.schemas import (
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

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    tags=["System"]
)
async def health_check():
    """Check the health status of the Client Service.
    
    Returns service health, version, and uptime information.
    
    **Returns:**
    ```json
    {
      "status": "healthy",
      "version": "1.0.0",
      "uptime": 3600.5
    }
    ```
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "uptime": time.time() - _start_time
    }


# ==================== Client Group Management ====================

@router.post(
    "/client-groups/{benchmark_id}",
    response_model=ClientGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new client group",
    tags=["Client Groups"],
    responses={
        201: {"description": "Client group created successfully"},
        409: {"description": "Client group already exists", "model": ErrorResponse}
    }
)
async def create_client_group(
    benchmark_id: int,
    payload: CreateClientGroupRequest = Body(
        ...,
        examples={
            "small": {
                "summary": "Small test group",
                "description": "Create a group with 10 clients for 5 minutes",
                "value": {"num_clients": 10, "time_limit": 5}
            },
            "medium": {
                "summary": "Medium benchmark group",
                "description": "Create a group with 100 clients for 30 minutes",
                "value": {"num_clients": 100, "time_limit": 30}
            },
            "large": {
                "summary": "Large stress test group",
                "description": "Create a group with 1000 clients for 60 minutes",
                "value": {"num_clients": 1000, "time_limit": 60}
            }
        }
    ),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Create a new client group for benchmark testing.
    
    A client group represents a SLURM job that will spawn multiple concurrent clients
    to send requests to the AI services. Each client runs independently and can be
    monitored via Prometheus metrics.
    
    **Path Parameters:**
    - `benchmark_id`: Unique identifier for this benchmark run (must be unique)
    
    **Request Body:**
    - `num_clients`: Number of concurrent clients to spawn (1-10000)
    - `time_limit`: SLURM job time limit in minutes (default: 5, max: 1440)
    
    **Returns (Success):**
    ```json
    {
      "status": "created",
      "benchmark_id": 12345,
      "num_clients": 100,
      "message": "Client group created and SLURM job submitted"
    }
    ```
    
    **Returns (Error - Already Exists):**
    ```json
    {
      "detail": "Client group with this benchmark_id already exists",
      "status_code": 409
    }
    ```
    
    **Example:**
    ```bash
    curl -X POST "http://localhost:8002/api/v1/client-groups/12345" \\
      -H "Content-Type: application/json" \\
      -d '{"num_clients": 100, "time_limit": 30}'
    ```
    
    **Workflow:**
    1. Client Service validates the request
    2. Creates a ClientGroup object
    3. Submits a SLURM job to HPC cluster
    4. SLURM job starts client processes on compute nodes
    5. Client processes register back with Client Service
    6. Returns immediately (job submitted asynchronously)
    
    **Note:** The client processes will take time to start. Use the `/client-groups/{benchmark_id}`
    endpoint to check the status and get the client process address.
    """
    logger.debug(f"Creating client group {benchmark_id} with {payload.num_clients} clients, time_limit={payload.time_limit}")
    
    res = client_manager.add_client_group(benchmark_id, payload.num_clients, payload.time_limit)
    
    if res == ClientManagerResponseStatus.ALREADY_EXISTS:
        logger.debug(f"Client group {benchmark_id} already exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client group with this benchmark_id already exists"
        )
    elif res == ClientManagerResponseStatus.ERROR:
        logger.error(f"Failed to create client group {benchmark_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create client group. Check SSH connectivity and SLURM configuration."
        )
    
    logger.info(f"Created client group {benchmark_id} with {payload.num_clients} clients")
    return {
        "status": "created",
        "benchmark_id": benchmark_id,
        "num_clients": payload.num_clients,
        "message": "Client group created and SLURM job submitted"
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
    "/client-groups/{benchmark_id}",
    response_model=ClientGroupInfoResponse,
    summary="Get client group information",
    tags=["Client Groups"],
    responses={
        200: {"description": "Client group information retrieved"},
        404: {"description": "Client group not found", "model": ErrorResponse}
    }
)
async def get_client_group_info(
    benchmark_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Get detailed information about a specific client group.
    
    Returns the number of clients, registration status, and client process address.
    
    **Path Parameters:**
    - `benchmark_id`: Unique identifier for the benchmark
    
    **Returns (Success):**
    ```json
    {
      "benchmark_id": 12345,
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
    - `pending`: SLURM job submitted, waiting for client process to register
    - `running`: Client process registered and ready to accept commands
    - `stopped`: Client group has been terminated
    """
    info = client_manager.get_group_info(benchmark_id)
    
    if info is None:
        logger.debug(f"Client group {benchmark_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client group not found"
        )
    
    return {
        "benchmark_id": benchmark_id,
        "info": info
    }


@router.delete(
    "/client-groups/{benchmark_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a client group",
    tags=["Client Groups"]
)
async def delete_client_group(
    benchmark_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Remove a client group and stop its associated SLURM job.
    
    **Path Parameters:**
    - `benchmark_id`: Unique identifier for the benchmark
    
    **Returns:**
    ```json
    {
      "status": "deleted",
      "benchmark_id": 12345
    }
    ```
    
    **Example:**
    ```bash
    curl -X DELETE http://localhost:8002/api/v1/client-groups/12345
    ```
    
    **Note:** This only removes the group from the Client Service's tracking.
    The SLURM job will continue running until its time limit or manual cancellation.
    """
    logger.debug(f"Deleting client group {benchmark_id}")
    client_manager.remove_client_group(benchmark_id)
    logger.info(f"Deleted client group {benchmark_id}")
    
    return {
        "status": "deleted",
        "benchmark_id": benchmark_id
    }


# ==================== Client Group Execution ====================

@router.post(
    "/client-groups/{benchmark_id}/run",
    response_model=RunClientGroupResponse,
    summary="Trigger client group to start benchmark",
    tags=["Execution"],
    responses={
        200: {"description": "Benchmark run triggered successfully"},
        404: {"description": "Client group not found or not ready", "model": ErrorResponse},
        500: {"description": "Internal error during execution", "model": ErrorResponse}
    }
)
async def run_client_group(
    benchmark_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Trigger a registered client group to start sending requests.
    
    This endpoint forwards the run command to the client process(es) that were spawned
    by the SLURM job. The client processes will then start sending concurrent requests
    to the configured AI services.
    
    **Path Parameters:**
    - `benchmark_id`: Unique identifier for the benchmark
    
    **Returns (Success):**
    ```json
    {
      "status": "dispatched",
      "benchmark_id": 12345,
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
      "detail": "Client process not registered yet. Wait for SLURM job to start.",
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
    this endpoint will work. Check status with `GET /client-groups/{benchmark_id}`.
    """
    logger.debug(f"Run request for benchmark {benchmark_id}")
    
    try:
        results = client_manager.run_client_group(benchmark_id)
    except ValueError as e:
        logger.warning(f"Run failed for unknown benchmark {benchmark_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Unexpected error while running client group {benchmark_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    
    logger.info(f"Dispatched run to benchmark {benchmark_id}: {len(results)} client(s) responded")
    return {
        "status": "dispatched",
        "benchmark_id": benchmark_id,
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
    Use this to dynamically configure Prometheus to monitor all active benchmarks.
    
    **Returns:**
    ```json
    [
      {
        "targets": ["mel2079:8000"],
        "labels": {
          "job": "client-group-12345",
          "benchmark_id": "12345",
          "num_clients": "100",
          "status": "running"
        }
      },
      {
        "targets": ["mel2080:8000"],
        "labels": {
          "job": "client-group-12346",
          "benchmark_id": "12346",
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
    
    for benchmark_id in client_manager.list_groups():
        info = client_manager.get_group_info(benchmark_id)
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
                    "job": f"client-group-{benchmark_id}",
                    "benchmark_id": str(benchmark_id),
                    "num_clients": str(info.get("num_clients", "unknown")),
                    "status": info.get("status", "unknown")
                }
            })
    
    return targets


@router.get(
    "/client-groups/{benchmark_id}/metrics",
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
    benchmark_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Get Prometheus-compatible metrics from a specific client group.
    
    This endpoint proxies the /metrics endpoint from the client process running on HPC.
    Client processes expose metrics about requests sent, latencies, errors, and more.
    
    **Path Parameters:**
    - `benchmark_id`: Unique identifier for the benchmark
    
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
    client_requests_total{benchmark_id="12345"} 1500.0
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
    
    info = client_manager.get_group_info(benchmark_id)
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client group not found"
        )
    
    client_addr = info.get("client_address")
    if not client_addr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client process not registered yet. Wait for SLURM job to start."
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

@router.post(
    "/client-groups/{benchmark_id}/logs/sync",
    response_model=LogSyncResponse,
    summary="Sync SLURM logs from remote to local",
    tags=["Logs"],
    responses={
        200: {"description": "Logs synced successfully"},
        404: {"description": "Client group not found", "model": ErrorResponse}
    }
)
async def sync_benchmark_logs(
    benchmark_id: int,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Sync SLURM job logs from MeluXina to local directory for a specific benchmark.
    
    This endpoint uses rsync over SSH to download log files from the remote HPC cluster
    to the local `./logs` directory.
    
    **Path Parameters:**
    - `benchmark_id`: Unique identifier for the benchmark
    
    **Returns (Success):**
    ```json
    {
      "success": true,
      "message": "Logs synced successfully",
      "local_path": "./logs",
      "benchmark_id": 12345
    }
    ```
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8002/api/v1/client-groups/12345/logs/sync
    ```
    
    **Log Files:**
    - Pattern: `client-{benchmark_id}-{job_id}.out`
    - Pattern: `client-{benchmark_id}-{job_id}.err`
    - Location: `./logs/` directory
    
    **Note:** Requires rsync to be installed and SSH access to MeluXina configured.
    """
    logger.info(f"Syncing logs for benchmark {benchmark_id}")
    
    result = client_manager.sync_logs(benchmark_id=benchmark_id)
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"]
        )
    
    return result


@router.post(
    "/logs/sync",
    response_model=LogSyncResponse,
    summary="Sync all SLURM logs from remote to local",
    tags=["Logs"]
)
async def sync_all_logs(client_manager: ClientManager = Depends(get_client_manager)):
    """Sync all SLURM job logs from MeluXina to local directory.
    
    Downloads logs for all client groups in a single rsync operation.
    
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
    - All files matching `client-*.out` and `client-*.err`
    - Synced from remote MeluXina to local `./logs/` directory
    
    **Use Cases:**
    - Debugging failed jobs
    - Collecting performance data
    - Post-mortem analysis
    - Archiving benchmark results
    """
    logger.info("Syncing all logs")
    
    result = client_manager.sync_logs(benchmark_id=None)
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"]
        )
    
    return result


# ==================== Legacy Observer Endpoint (Deprecated) ====================

@router.post(
    "/client-groups/{benchmark_id}/observer",
    response_model=ObserverRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a metrics observer (DEPRECATED - Use Prometheus)",
    tags=["Monitoring"],
    deprecated=True
)
async def add_observer(
    benchmark_id: int,
    payload: RegisterObserverRequest,
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Register a monitor/observer for a client group.
    
    **DEPRECATED:** This endpoint is deprecated. Use Prometheus with the
    `/client-groups/targets` and `/client-groups/{benchmark_id}/metrics` endpoints instead.
    
    Prometheus provides better:
    - Time-series storage
    - Query capabilities (PromQL)
    - Visualization (Grafana)
    - Alerting
    
    **Migration Path:**
    1. Configure Prometheus to scrape `/client-groups/{benchmark_id}/metrics`
    2. Use `/client-groups/targets` for service discovery
    3. Visualize metrics in Grafana
    4. Set up alerts in Prometheus/Alertmanager
    """
    import requests
    
    # Find the registered client process for this benchmark
    with client_manager._lock:
        group = client_manager._client_groups.get(benchmark_id)
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Benchmark id not found"
            )
        client_addr = group.get_client_address()

    if client_addr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No client process registered for this benchmark"
        )

    # Forward the observer registration to the client group's REST API
    url = f"{client_addr.rstrip('/')}/observer"
    json_payload = {
        "ip_address": payload.ip_address,
        "port": payload.port,
        "update_preferences": payload.update_preferences or {}
    }
    
    try:
        r = requests.post(url, json=json_payload, timeout=5.0)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to contact client process: {e}"
        )

    if r.status_code not in (200, 201):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Client process returned {r.status_code}: {r.text}"
        )

    return {
        "status": "registered",
        "benchmark_id": benchmark_id,
        "observer": f"{payload.ip_address}:{payload.port}"
    }
