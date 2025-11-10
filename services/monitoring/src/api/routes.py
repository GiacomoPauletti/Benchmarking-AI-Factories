"""
API route definitions for the Monitoring Service.
Prometheus-based metrics collection and management.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from ..monitoring_service import MonitoringService
from .schemas import (
    SessionCreateRequest, SessionCreateResponse,
    SessionStatusResponse, SessionStopResponse, SessionDeleteResponse,
    ClientRegistrationRequest, ClientRegistrationResponse,
    ServiceRegistrationRequest, ServiceRegistrationResponse,
    CollectionRequest, CollectionResponse
)

router = APIRouter()

# Singleton instance of MonitoringService (created once, reused for all requests)
_monitoring_service_instance = None


def get_monitoring_service() -> MonitoringService:
    """Dependency function to get the singleton MonitoringService instance."""
    global _monitoring_service_instance
    if _monitoring_service_instance is None:
        _monitoring_service_instance = MonitoringService()
    return _monitoring_service_instance


# -------------------- Session Lifecycle Endpoints --------------------

@router.post("/sessions", response_model=SessionCreateResponse, 
             summary="Create and start a new monitoring session")
async def create_session(
    request: SessionCreateRequest,
    monitoring_service: MonitoringService = Depends(get_monitoring_service)
):
    """
    Create and start a new monitoring session.
    
    **SINGLE-SESSION MODE**: Only one session can be active (RUNNING) at a time.
    If there's already an active session, you must stop it before creating a new one.
    
    A monitoring session tracks metrics collection for a specific benchmark run.
    The session is created and immediately activated (Prometheus config is updated
    and reloaded).
    
    **Request Body:**
    - `run_id` (optional): Custom session identifier (auto-generated if not provided)
    - `scrape_interval` (optional): How often Prometheus scrapes metrics (default: "15s")
    - `labels` (optional): Additional labels to attach to this session's metrics
    
    **Returns:**
    - Session ID, Prometheus URL, status (RUNNING), workdir, and targets_count
    
    **Example:**
    ```json
    {
      "run_id": "benchmark-001",
      "scrape_interval": "15s",
      "labels": {
        "environment": "production",
        "cluster": "meluxina"
      }
    }
    ```
    
    **Note:** The session is immediately active. You can now register targets
    and they will be scraped automatically.
    
    **Error 409:** Another session is already RUNNING - stop it first
    """
    try:
        result = monitoring_service.create_session(request.dict(exclude_none=True))
        return SessionCreateResponse(**result)
    except RuntimeError as e:
        # Check if it's the single-session conflict
        if "already RUNNING" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/status", response_model=SessionStatusResponse,
            summary="Get monitoring session status")
async def get_session_status(
    session_id: str,
    monitoring_service: MonitoringService = Depends(get_monitoring_service)
):
    """
    Get the current status of a monitoring session.
    
    **Path Parameters:**
    - `session_id`: The monitoring session identifier
    
    **Returns:**
    - Session status, Prometheus health, targets count, and timestamps
    """
    try:
        result = monitoring_service.status(session_id)
        return SessionStatusResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", summary="List all monitoring sessions")
async def list_sessions(
    monitoring_service: MonitoringService = Depends(get_monitoring_service)
):
    """
    List all monitoring sessions (active and historical).
    
    Sessions are sorted by creation time (newest first).
    
    **Returns:**
    - List of all session objects with their metadata
    """
    try:
        sessions = monitoring_service.list_sessions()
        return {"sessions": sessions, "count": len(sessions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/stop", response_model=SessionStopResponse,
             summary="Stop a monitoring session")
async def stop_session(
    session_id: str,
    monitoring_service: MonitoringService = Depends(get_monitoring_service)
):
    """
    Stop a monitoring session.
    
    Marks the session as stopped. In local deployment, Prometheus continues
    running for other sessions.
    
    **Path Parameters:**
    - `session_id`: The monitoring session identifier
    
    **Returns:**
    - Success status and message
    """
    try:
        success = monitoring_service.stop(session_id)
        return SessionStopResponse(
            success=success, 
            message=f"Session {session_id} stopped successfully" if success 
                    else f"Failed to stop session {session_id}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}", response_model=SessionDeleteResponse,
               summary="Delete a monitoring session")
async def delete_session(
    session_id: str,
    monitoring_service: MonitoringService = Depends(get_monitoring_service)
):
    """
    Delete a monitoring session (state only, collected data is preserved).
    
    **Path Parameters:**
    - `session_id`: The monitoring session identifier
    
    **Returns:**
    - Success status and message
    """
    try:
        success = monitoring_service.delete(session_id)
        return SessionDeleteResponse(
            success=success,
            message=f"Session {session_id} deleted successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Target Registration Endpoints --------------------

@router.post("/clients", response_model=ClientRegistrationResponse,
             summary="Register a client for monitoring")
async def register_client(
    request: ClientRegistrationRequest,
    monitoring_service: MonitoringService = Depends(get_monitoring_service)
):
    """
    Register a client with its exporters for monitoring.
    
    Clients are benchmarking processes that expose metrics via exporters (e.g., 
    node_exporter, dcgm_exporter). Registering a client adds its exporters to
    the Prometheus scrape configuration.
    
    **Request Body:**
    - `session_id`: Monitoring session to register with
    - `client_id`: Unique identifier for this client
    - `node`: Node name where the client runs
    - `exporters`: Dictionary mapping exporter types to endpoints
    - `preferences`: Dictionary indicating which exporters to enable
    
    **Example:**
    ```json
    {
      "session_id": "mon-abc123",
      "client_id": "client-001",
      "node": "node-001",
      "exporters": {
        "node": "node-001:9100",
        "dcgm": "node-001:9400"
      },
      "preferences": {
        "enable_node": true,
        "enable_dcgm": true
      }
    }
    ```
    """
    try:
        result = monitoring_service.register_client(request.dict())
        return ClientRegistrationResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/services", response_model=ServiceRegistrationResponse,
             summary="Register a service for monitoring")
async def register_service(
    request: ServiceRegistrationRequest,
    monitoring_service: MonitoringService = Depends(get_monitoring_service)
):
    """
    Register a service endpoint for monitoring.
    
    Services are AI workloads (e.g., vLLM, Qdrant) that expose their own
    metrics endpoints. Registering a service adds it to the Prometheus scrape 
    configuration.
    
    **Request Body:**
    - `session_id`: Monitoring session to register with
    - `client_id`: Associated client identifier
    - `name`: Service name (e.g., "vllm", "qdrant")
    - `endpoint`: HTTP endpoint for metrics (e.g., "http://node-001:8000/metrics")
    - `labels` (optional): Additional labels to attach to metrics
    
    **Example:**
    ```json
    {
      "session_id": "mon-abc123",
      "client_id": "client-001",
      "name": "vllm",
      "endpoint": "http://node-001:8000/metrics",
      "labels": {
        "model": "gpt2",
        "gpu": "a100"
      }
    }
    ```
    """
    try:
        result = monitoring_service.register_service(request.dict())
        return ServiceRegistrationResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Collection Endpoints --------------------

@router.post("/sessions/{session_id}/collect", response_model=CollectionResponse,
             summary="Collect metrics for a time window")
async def collect_metrics(
    session_id: str,
    request: CollectionRequest,
    monitoring_service: MonitoringService = Depends(get_monitoring_service)
):
    """
    Collect metrics for a specific time window and save to disk.
    
    This queries Prometheus for all metrics within the specified time window,
    aggregates them, and saves the results to the specified output directory.
    
    **Path Parameters:**
    - `session_id`: The monitoring session identifier
    
    **Request Body:**
    - `window_start`: Start time as ISO 8601 string (e.g., "2025-11-04T10:00:00Z")
    - `window_end`: End time as ISO 8601 string
    - `out_dir`: Directory path where collected metrics will be saved
    - `run_id`: Identifier for this collection run (default: "run")
    
    **Returns:**
    - Dictionary of artifact file paths created during collection
    
    **Example:**
    ```json
    {
      "window_start": "2025-11-04T10:00:00Z",
      "window_end": "2025-11-04T11:00:00Z",
      "out_dir": "/data/metrics",
      "run_id": "benchmark_001"
    }
    ```
    """
    try:
        result = monitoring_service.collect(
            session_id,
            window=(request.window_start, request.window_end),
            out_dir=request.out_dir,
            run_id=request.run_id
        )
        return CollectionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
