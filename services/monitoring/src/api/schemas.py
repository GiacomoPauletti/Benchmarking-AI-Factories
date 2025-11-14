"""
Pydantic schemas for the Monitoring Service API.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List


# -------------------- Session Schemas --------------------

class SessionCreateRequest(BaseModel):
    """Request to create a new monitoring session."""
    run_id: Optional[str] = Field(None, description="Optional session identifier (auto-generated if not provided)")
    scrape_interval: str = Field("15s", description="Prometheus scrape interval (e.g., '15s', '1m')")
    labels: Optional[Dict[str, str]] = Field(None, description="Additional labels for this session")


class SessionCreateResponse(BaseModel):
    """Response for session creation."""
    session_id: str
    prometheus_url: str
    status: str
    workdir: str
    targets_count: int


class SessionStatusResponse(BaseModel):
    """Response for session status."""
    session_id: str
    status: str
    prometheus: Dict[str, Any]
    targets_count: int
    created_at: Optional[str] = None
    started_at: Optional[str] = None


class SessionStopResponse(BaseModel):
    """Response for session stop."""
    success: bool
    message: str


class SessionDeleteResponse(BaseModel):
    """Response for session deletion."""
    success: bool
    message: str


# -------------------- Target Registration Schemas --------------------

class ClientRegistrationRequest(BaseModel):
    """Request to register a client for monitoring."""
    session_id: str = Field(..., description="Monitoring session ID")
    client_id: str = Field(..., description="Unique client identifier")
    node: str = Field(..., description="Node name where client runs")
    exporters: Dict[str, str] = Field(..., description="Dict of exporter types to endpoints")
    preferences: Dict[str, bool] = Field(..., description="Dict of enabled exporters")


class ClientRegistrationResponse(BaseModel):
    """Response for client registration."""
    ok: bool
    client_id: str


class ServiceRegistrationRequest(BaseModel):
    """Request to register a service for monitoring.
    
    Provide the service_id from the Server API, and the Monitoring service will
    automatically resolve the metrics endpoint using /api/v1/services/{service_id}/metrics.
    The service_id is used as the Prometheus job label name.
    """
    session_id: str = Field(..., description="Monitoring session ID")
    service_id: str = Field(..., description="Server API service ID (also used as Prometheus job label)")
    labels: Optional[Dict[str, str]] = Field(None, description="Prometheus labels for filtering/grouping (e.g., {'environment': 'prod', 'team': 'ml'})")


class ServiceRegistrationResponse(BaseModel):
    """Response for service registration."""
    ok: bool
    service_id: str
    endpoint: str


# -------------------- Collection Schemas --------------------

class CollectionRequest(BaseModel):
    """Request to collect metrics."""
    window_start: str = Field(..., description="Start time as ISO string")
    window_end: str = Field(..., description="End time as ISO string")
    out_dir: str = Field(..., description="Output directory for collected metrics")
    run_id: str = Field("run", description="Run identifier for the collection")


class CollectionResponse(BaseModel):
    """Response for metrics collection."""
    artifacts: Dict[str, str]
