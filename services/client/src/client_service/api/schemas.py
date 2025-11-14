"""
API Request and Response Schemas for Client Service

Pydantic models for request validation and response formatting.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union


# ==================== Request Schemas ====================

class CreateClientGroupRequest(BaseModel):
    """Request to create a new client group."""
    num_clients: int = Field(
        ...,
        gt=0,
        description="Number of concurrent clients to spawn",
        example=100
    )
    time_limit: int = Field(
        default=5,
        gt=0,
        le=1440,
        description="Time limit for SLURM job in minutes (max: 24 hours)",
        example=30
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "num_clients": 10,
                    "time_limit": 5
                },
                {
                    "num_clients": 100,
                    "time_limit": 30
                },
                {
                    "num_clients": 1000,
                    "time_limit": 60
                }
            ]
        }


class RegisterObserverRequest(BaseModel):
    """Request to register a metrics observer for a client group."""
    ip_address: str = Field(
        ...,
        description="IP address of the observer/monitor service",
        example="192.168.1.100"
    )
    port: int = Field(
        ...,
        gt=0,
        lt=65536,
        description="Port of the observer/monitor service",
        example=9090
    )
    update_preferences: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional preferences for metric updates"
    )


# ==================== Response Schemas ====================

class ClientGroupInfo(BaseModel):
    """Information about a client group."""
    num_clients: int = Field(..., description="Number of clients in the group")
    client_address: Optional[str] = Field(None, description="Address of the registered client process")
    created_at: float = Field(..., description="Unix timestamp when the group was created")
    status: str = Field(default="pending", description="Current status: pending, running, stopped")


class ClientGroupResponse(BaseModel):
    """Response after creating or updating a client group."""
    status: str = Field(..., description="Operation status", example="created")
    benchmark_id: int = Field(..., description="Unique identifier for the benchmark")
    num_clients: Optional[int] = Field(None, description="Number of clients in the group")
    message: Optional[str] = Field(None, description="Additional information")


class ClientGroupListResponse(BaseModel):
    """Response listing all client groups."""
    groups: List[int] = Field(..., description="List of active benchmark IDs")
    count: int = Field(..., description="Total number of active groups")


class ClientGroupInfoResponse(BaseModel):
    """Response with detailed client group information."""
    benchmark_id: int = Field(..., description="Benchmark identifier")
    info: ClientGroupInfo = Field(..., description="Detailed group information")


class RunClientGroupResponse(BaseModel):
    """Response after triggering a client group to run."""
    status: str = Field(..., description="Operation status", example="dispatched")
    benchmark_id: int = Field(..., description="Benchmark identifier")
    results: List[Dict[str, Any]] = Field(..., description="Results from client processes")


class ObserverRegistrationResponse(BaseModel):
    """Response after registering an observer."""
    status: str = Field(..., description="Registration status", example="registered")
    benchmark_id: int = Field(..., description="Benchmark identifier")
    observer: str = Field(..., description="Observer endpoint", example="192.168.1.100:9090")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service health status", example="healthy")
    version: str = Field(default="1.0.0", description="Service version")
    uptime: Optional[float] = Field(None, description="Service uptime in seconds")


class MetricsTarget(BaseModel):
    """Prometheus scrape target configuration."""
    targets: List[str] = Field(..., description="List of target endpoints")
    labels: Dict[str, str] = Field(..., description="Labels for the target")


class ErrorResponse(BaseModel):
    """Error response model"""
    detail: str = Field(..., description="Error message", example="Client group not found")
    status_code: int = Field(..., description="HTTP status code", example=404)


class LogSyncResponse(BaseModel):
    """Response for log synchronization"""
    success: bool = Field(..., description="Whether sync was successful", example=True)
    message: str = Field(..., description="Status message", example="Logs synced successfully")
    local_path: str = Field(..., description="Local directory where logs were synced", example="./logs")
    benchmark_id: Union[int, str] = Field(..., description="Benchmark ID or 'all'", example=12345)
    groups: Optional[List[int]] = Field(None, description="List of synced groups (when syncing all)", example=[12345, 12346])
