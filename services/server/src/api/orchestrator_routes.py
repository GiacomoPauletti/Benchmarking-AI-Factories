"""
API routes for orchestrator lifecycle management.
Allows starting/stopping the orchestrator on demand from the frontend.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orchestrator", tags=["Orchestrator Control"])


# ────────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ────────────────────────────────────────────────────────────────────────────────


class OrchestratorStartRequest(BaseModel):
    """Request model for starting the orchestrator."""

    time_limit_minutes: int = Field(
        default=30,
        ge=5,
        le=240,
        description="SLURM job time limit in minutes (5-240)",
    )


class OrchestratorStatusResponse(BaseModel):
    """Response model for orchestrator status."""

    running: bool = Field(description="Whether the orchestrator is currently running")
    job_id: Optional[str] = Field(default=None, description="SLURM job ID if running")
    started_at: Optional[str] = Field(
        default=None, description="ISO timestamp when the orchestrator was started"
    )
    time_limit_minutes: Optional[int] = Field(
        default=None, description="Configured time limit for the session"
    )
    remaining_seconds: Optional[int] = Field(
        default=None, description="Seconds remaining until job timeout"
    )
    orchestrator_url: Optional[str] = Field(
        default=None, description="URL of the running orchestrator"
    )
    last_health_check: Optional[str] = Field(
        default=None, description="ISO timestamp of last health check"
    )
    last_error: Optional[str] = Field(
        default=None, description="Last error message if any"
    )


class OrchestratorStartResponse(BaseModel):
    """Response model for orchestrator start request."""

    success: bool
    message: str
    job_id: Optional[str] = None
    time_limit_minutes: Optional[int] = None


class OrchestratorStopResponse(BaseModel):
    """Response model for orchestrator stop request."""

    success: bool
    message: str


# ────────────────────────────────────────────────────────────────────────────────
# Module-level state accessors (set by main.py)
# ────────────────────────────────────────────────────────────────────────────────

_get_orchestrator_session = None
_start_orchestrator_fn = None
_stop_orchestrator_fn = None


def set_orchestrator_control_functions(
    get_session_fn,
    start_fn,
    stop_fn,
):
    """
    Inject orchestrator control functions from main.py.

    Args:
        get_session_fn: Function that returns current OrchestratorSession state
        start_fn: Async function to start orchestrator (takes time_limit_minutes)
        stop_fn: Async function to stop orchestrator
    """
    global _get_orchestrator_session, _start_orchestrator_fn, _stop_orchestrator_fn
    _get_orchestrator_session = get_session_fn
    _start_orchestrator_fn = start_fn
    _stop_orchestrator_fn = stop_fn


# ────────────────────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────────────────────


@router.get(
    "/status",
    response_model=OrchestratorStatusResponse,
    summary="Get orchestrator status",
)
async def get_orchestrator_status():
    """
    Get the current status of the orchestrator.

    Returns information about whether the orchestrator is running,
    the SLURM job ID, time remaining, and health status.
    """
    if _get_orchestrator_session is None:
        raise HTTPException(
            status_code=500,
            detail="Orchestrator control not initialized",
        )

    session = _get_orchestrator_session()

    # Calculate remaining time if session is active
    remaining_seconds = None
    if session.started_at and session.time_limit_minutes:
        elapsed = (datetime.now(timezone.utc) - session.started_at).total_seconds()
        total_seconds = session.time_limit_minutes * 60
        remaining_seconds = max(0, int(total_seconds - elapsed))

    return OrchestratorStatusResponse(
        running=session.alive,
        job_id=session.job_id,
        started_at=session.started_at.isoformat() if session.started_at else None,
        time_limit_minutes=session.time_limit_minutes,
        remaining_seconds=remaining_seconds,
        orchestrator_url=session.orchestrator_url,
        last_health_check=session.last_check,
        last_error=session.last_error,
    )


@router.post(
    "/start",
    response_model=OrchestratorStartResponse,
    summary="Start the orchestrator",
)
async def start_orchestrator(
    request: OrchestratorStartRequest = Body(
        default=OrchestratorStartRequest(),
        examples={
            "default": {
                "summary": "Start with 30-minute limit",
                "value": {"time_limit_minutes": 30},
            },
            "extended": {
                "summary": "Start with 2-hour limit",
                "value": {"time_limit_minutes": 120},
            },
        },
    ),
):
    """
    Start the orchestrator with a specified time limit.

    This submits a SLURM job to run the orchestrator container on MeluXina.
    The orchestrator will automatically terminate when the time limit is reached.

    **Note:** Only one orchestrator session can be active at a time.
    """
    if _start_orchestrator_fn is None:
        raise HTTPException(
            status_code=500,
            detail="Orchestrator control not initialized",
        )

    # Check if already running
    session = _get_orchestrator_session()
    if session.alive:
        raise HTTPException(
            status_code=409,
            detail=f"Orchestrator is already running (job_id: {session.job_id})",
        )

    try:
        logger.info(
            f"Starting orchestrator with time_limit_minutes={request.time_limit_minutes}"
        )
        result = await _start_orchestrator_fn(request.time_limit_minutes)

        if result.get("success"):
            return OrchestratorStartResponse(
                success=True,
                message="Orchestrator started successfully",
                job_id=result.get("job_id"),
                time_limit_minutes=request.time_limit_minutes,
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to start orchestrator"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to start orchestrator")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start orchestrator: {str(e)}",
        )


@router.post(
    "/stop",
    response_model=OrchestratorStopResponse,
    summary="Stop the orchestrator",
)
async def stop_orchestrator():
    """
    Stop the running orchestrator.

    This will cancel the SLURM job and terminate the orchestrator container.
    All running services should be stopped before calling this endpoint.
    """
    if _stop_orchestrator_fn is None:
        raise HTTPException(
            status_code=500,
            detail="Orchestrator control not initialized",
        )

    session = _get_orchestrator_session()
    if not session.alive and not session.job_id:
        raise HTTPException(
            status_code=409,
            detail="Orchestrator is not running",
        )

    try:
        logger.info(f"Stopping orchestrator (job_id: {session.job_id})")
        result = await _stop_orchestrator_fn()

        if result.get("success"):
            return OrchestratorStopResponse(
                success=True,
                message="Orchestrator stopped successfully",
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to stop orchestrator"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to stop orchestrator")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop orchestrator: {str(e)}",
        )
