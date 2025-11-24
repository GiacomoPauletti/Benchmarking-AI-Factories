"""
API Request and Response Schemas for Client Service

Pydantic models for request validation and response formatting.

NOTE: This service manages client groups - it does NOT orchestrate benchmarks.
A separate benchmark orchestrator service will use this client service to create
and manage client groups as needed for benchmark runs.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union


# ==================== Request Schemas ====================

class CreateClientGroupRequest(BaseModel):
    """Request to create a new client group for load testing."""
    
    # Load generation parameters
    # Note: `target_url` is no longer required. The client service should be
    # provided a `service_id` and will resolve the orchestrator `prompt_url`
    # internally when available.
    service_id: str = Field(
        ...,
        description="Service ID of the vLLM service to test",
        example="3732769"
    )
    num_clients: int = Field(
        ...,
        gt=0,
        description="Number of concurrent clients to spawn",
        example=10
    )
    requests_per_second: float = Field(
        default=10.0,
        gt=0,
        description="Target requests per second across all clients",
        example=10.0
    )
    duration_seconds: int = Field(
        default=60,
        gt=0,
        description="Load test duration in seconds",
        example=60
    )
    prompts: List[str] = Field(
        default=["Tell me a story about AI."],
        min_length=1,
        description="List of prompts to randomly select from during testing",
        example=["What is machine learning?", "Explain neural networks."]
    )
    
    # vLLM API parameters
    max_tokens: int = Field(
        default=100,
        gt=0,
        le=4096,
        description="Maximum tokens to generate per request",
        example=100
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for generation",
        example=0.7
    )
    
    # SLURM parameters
    time_limit: int = Field(
        default=5,
        gt=0,
        le=1440,
        description="SLURM job time limit in minutes (should be > duration_seconds/60)",
        example=5
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "service_id": "3732769",
                    "num_clients": 5,
                    "requests_per_second": 5.0,
                    "duration_seconds": 60,
                    "prompts": ["What is AI?", "Explain deep learning."],
                    "max_tokens": 50,
                    "time_limit": 10
                },
                {
                    "service_id": "3732769",
                    "num_clients": 100,
                    "requests_per_second": 100.0,
                    "duration_seconds": 300,
                    "prompts": ["Tell me a story.", "Write a poem."],
                    "max_tokens": 200,
                    "temperature": 0.9,
                    "time_limit": 15
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
    job_id: Optional[str] = Field(None, description="SLURM job ID for this load test")
    load_config: Optional[dict] = Field(None, description="Load test configuration")


class ClientGroupResponse(BaseModel):
    """Response after creating or updating a client group."""
    status: str = Field(..., description="Operation status", example="created")
    group_id: int = Field(..., description="Unique identifier for the client group")
    num_clients: Optional[int] = Field(None, description="Number of clients in the group")
    message: Optional[str] = Field(None, description="Additional information")


class ClientGroupListResponse(BaseModel):
    """Response listing all client groups."""
    groups: List[int] = Field(..., description="List of active group IDs")
    count: int = Field(..., description="Total number of active groups")


class ClientGroupInfoResponse(BaseModel):
    """Response with detailed client group information."""
    group_id: int = Field(..., description="Client group identifier")
    info: ClientGroupInfo = Field(..., description="Detailed group information")


class RunClientGroupResponse(BaseModel):
    """Response after triggering a client group to run."""
    status: str = Field(..., description="Operation status", example="dispatched")
    group_id: int = Field(..., description="Client group identifier")
    results: List[Dict[str, Any]] = Field(..., description="Results from client processes")


class ObserverRegistrationResponse(BaseModel):
    """Response after registering an observer."""
    status: str = Field(..., description="Registration status", example="registered")
    group_id: int = Field(..., description="Client group identifier")
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
    group_id: Union[int, str] = Field(..., description="Group ID or 'all'", example=12345)
    groups: Optional[List[int]] = Field(None, description="List of synced groups (when syncing all)", example=[12345, 12346])
