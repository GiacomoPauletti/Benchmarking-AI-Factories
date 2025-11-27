"""
Main FastAPI application entry point for the Server Service.
SLURM + Apptainer orchestration for AI workloads.
"""

import asyncio
import os
import logging
import signal
import sys
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

# Clean package imports
from api.routes import router, set_orchestrator_proxy
from logging_setup import setup_logging
from orchestrator_initializer import initialize_orchestrator_proxy

# Global logger and orchestrator proxy
logger = None
orchestrator_proxy = None
orchestrator_monitor_task: Optional[asyncio.Task] = None


@dataclass
class OrchestratorHealthState:
    """Lightweight shared state for orchestrator availability."""

    alive: bool = False
    last_check: Optional[str] = None
    last_error: Optional[str] = "Orchestrator not initialized"


orchestrator_health = OrchestratorHealthState()


def _set_orchestrator_health(alive: bool, error: Optional[str] = None) -> None:
    """Update orchestrator health state and log transitions."""

    global orchestrator_health, logger

    previous = orchestrator_health.alive
    orchestrator_health.alive = alive
    orchestrator_health.last_check = datetime.utcnow().isoformat() + "Z"
    orchestrator_health.last_error = error

    if logger and previous != alive:
        if alive:
            logger.info("Orchestrator marked healthy")
        else:
            logger.warning("Orchestrator marked unhealthy: %s", error)


async def _orchestrator_monitor_loop(poll_interval: int = 10) -> None:
    """Continuously poll orchestrator health endpoint."""

    global orchestrator_proxy

    while True:
        try:
            if orchestrator_proxy:
                try:
                    orchestrator_proxy.check_health()
                    _set_orchestrator_health(True, None)
                except Exception as exc:  # noqa: BLE001 - log unhealthy reason
                    _set_orchestrator_health(False, str(exc))
            else:
                _set_orchestrator_health(False, "Orchestrator proxy not initialized")

            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            if logger:
                logger.exception("Unexpected error in orchestrator monitor: %s", exc)
            await asyncio.sleep(poll_interval)


def shutdown_handler(signum, frame):
    """Handle graceful shutdown by stopping all running services and orchestrator."""
    global logger, orchestrator_proxy

    _set_orchestrator_health(False, f"Server received shutdown signal {signum}")

    if logger:
        logger.info(f"Received shutdown signal {signum}. Stopping all services...")
    else:
        print(f"Received shutdown signal {signum}. Stopping all services...")

    try:
        # First, stop all service groups (before individual services)
        if orchestrator_proxy:
            try:
                service_groups = orchestrator_proxy.list_service_groups()
                if logger:
                    logger.info(f"Found {len(service_groups)} service groups to stop")
                else:
                    print(f"Found {len(service_groups)} service groups to stop")

                for group in service_groups:
                    group_id = group.get("id")
                    group_name = group.get("name", "unknown")
                    try:
                        if logger:
                            logger.info(f"Stopping service group {group_id} ({group_name})...")
                        else:
                            print(f"Stopping service group {group_id} ({group_name})...")
                        orchestrator_proxy.stop_service_group(group_id)
                    except Exception as e:  # noqa: BLE001
                        if logger:
                            logger.error(f"Failed to stop service group {group_id}: {e}")
                        else:
                            print(f"Failed to stop service group {group_id}: {e}")
            except Exception as e:  # noqa: BLE001
                if logger:
                    logger.error(f"Failed to list service groups: {e}")
                else:
                    print(f"Failed to list service groups: {e}")

        # Then stop individual services
        if orchestrator_proxy:
            services = orchestrator_proxy.list_services()

            if logger:
                logger.info(f"Found {len(services)} services to stop")
            else:
                print(f"Found {len(services)} services to stop")

            # Cancel each service
            for service in services:
                service_id = service.get("id")
                service_name = service.get("name", "unknown")
                try:
                    if logger:
                        logger.info(f"Stopping service {service_id} ({service_name})...")
                    else:
                        print(f"Stopping service {service_id} ({service_name})...")
                    orchestrator_proxy.stop_service(service_id)
                except Exception as e:  # noqa: BLE001
                    if logger:
                        logger.error(f"Failed to stop service {service_id}: {e}")
                    else:
                        print(f"Failed to stop service {service_id}: {e}")

        # Finally, stop the orchestrator job itself
        if orchestrator_proxy:
            try:
                if logger:
                    logger.info("Stopping orchestrator job...")
                else:
                    print("Stopping orchestrator job...")
                orchestrator_proxy.stop_orchestrator()
            except Exception as e:  # noqa: BLE001
                if logger:
                    logger.error(f"Failed to stop orchestrator: {e}")
                else:
                    print(f"Failed to stop orchestrator: {e}")

        if logger:
            logger.info("All services and orchestrator stopped. Exiting...")
        else:
            print("All services and orchestrator stopped. Exiting...")
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.error(f"Error during shutdown: {e}")
        else:
            print(f"Error during shutdown: {e}")

    sys.exit(0)
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# Create FastAPI application
app = FastAPI(
    title="AI Factory Server Service",
    description="SLURM + Apptainer orchestration for AI workloads",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

log_dir = os.environ.get("APP_LOG_DIR", "/app/logs")
try:
    server_log_path = setup_logging(log_dir)
    logger = logging.getLogger(__name__)
except Exception:
    # If logging setup fails for any reason, fall back to a basic config that writes to stdout
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "AI Factory Server Service",
        "version": "1.0.0",
        "status": "running",
        "node": os.environ.get("SLURMD_NODENAME", "unknown"),
        "job_id": os.environ.get("SLURM_JOB_ID", "unknown"),
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    """Health check endpoint - returns degraded if orchestrator is down."""
    global orchestrator_proxy

    is_ready = orchestrator_proxy is not None and orchestrator_health.alive
    status = "healthy" if is_ready else "degraded"

    return {
        "status": status,
        "orchestrator_initialized": orchestrator_proxy is not None,
        "orchestrator_alive": orchestrator_health.alive,
        "last_orchestrator_check": orchestrator_health.last_check,
        "last_orchestrator_error": orchestrator_health.last_error,
        "ready": is_ready
    }

@app.get("/ready")
async def ready():
    """Readiness check endpoint - server is ready to accept requests."""
    global orchestrator_proxy

    remote_base = os.getenv("REMOTE_BASE_PATH", "~/ai-factory-benchmarks")
    orchestrator_ready = orchestrator_proxy is not None and orchestrator_health.alive

    if not orchestrator_ready:
        reason = "orchestrator not initialized" if orchestrator_proxy is None else "orchestrator heartbeat failed"
        error_detail = {
            "status": "not ready",
            "reason": reason,
            "details": (
                "The orchestrator is currently unavailable. The server cannot accept new "
                "service requests until the orchestrator job is running again."
            ),
            "orchestrator_alive": orchestrator_health.alive,
            "last_orchestrator_error": orchestrator_health.last_error,
            "troubleshooting": {
                "check_logs": f"{remote_base}/logs/orchestrator_job.err",
                "common_issues": [
                    "Orchestrator container (.sif) is corrupted - it will be rebuilt on next attempt",
                    "SLURM job failed to start - check SLURM queue with 'squeue'",
                    "Network connectivity issues between server and MeluXina",
                    "SSH authentication failure"
                ],
                "next_steps": [
                    "Check the orchestrator job logs on MeluXina",
                    "Restart the server service to trigger a rebuild",
                    "Verify SSH connectivity to MeluXina"
                ]
            }
        }

        return Response(
            content=json.dumps(error_detail),
            status_code=503,
            media_type="application/json"
        )

    return {"status": "ready", "orchestrator": "available"}

# Include API routes
app.include_router(router, prefix="/api/v1")

@app.on_event("startup")
async def on_startup():
    """FastAPI startup event handler - set up SSH tunnel and wait for orchestrator."""
    global logger, orchestrator_proxy, orchestrator_monitor_task
    
    # SLURM REST API now uses the same SOCKS5 proxy as the orchestrator
    # No separate tunnel needed - SlurmClient will route through socks5h://localhost:1080
    if logger:
        logger.info("SLURM REST API will use SOCKS5 proxy (no separate tunnel needed)")
    else:
        print("SLURM REST API will use SOCKS5 proxy (no separate tunnel needed)")

    try:
        from ssh_manager import SSHManager
        ssh_manager = SSHManager()
            
        # Initialize OrchestratorProxy - this blocks until orchestrator is ready
        if logger:
            logger.info("Initializing orchestrator (may take up to 2 minutes)...")
        else:
            print("Initializing orchestrator (may take up to 2 minutes)...")
            
        orchestrator_proxy = initialize_orchestrator_proxy(ssh_manager)
        
        if orchestrator_proxy:
            # Inject orchestrator proxy into routes module
            set_orchestrator_proxy(orchestrator_proxy)
            _set_orchestrator_health(True, None)

            if logger:
                logger.info("✓ Server is ready - orchestrator initialized successfully")
            else:
                print("✓ Server is ready - orchestrator initialized successfully")

            orchestrator_monitor_task = asyncio.create_task(_orchestrator_monitor_loop())
        else:
            error_msg = (
                "✗ CRITICAL: Orchestrator initialization FAILED - server is NOT ready!\n"
                "The orchestrator container may be corrupted or failed to build.\n"
                "Check logs.\n"
                "The server will remain in unhealthy state until this is resolved."
            )
            if logger:
                logger.error(error_msg)
            else:
                print(error_msg)
            # Don't raise - let the server run but mark as not ready
            # This allows health checks to show the issue
            _set_orchestrator_health(False, "Failed to initialize orchestrator")
                
    except Exception as e:
        error_msg = (
            f"✗ CRITICAL: Server initialization FAILED: {e}\n"
            "The orchestrator is required for the server to function.\n"
            "Possible causes:\n"
            "  - SSH connection to MeluXina failed\n"
            "  - SLURM REST API tunnel failed\n"
            "  - Orchestrator container build failed\n"
            "  - Network connectivity issues\n"
            "Check logs for more details."
        )
        if logger:
            logger.error(error_msg)
            logger.exception("Detailed error:")
        else:
            print(error_msg)
            import traceback
            traceback.print_exc()
        # Don't raise - let health endpoint report the issue
        _set_orchestrator_health(False, str(e))

@app.get("/orchestrator/services")
async def get_orchestrator_services():
    """Get services from orchestrator"""
    from fastapi import HTTPException
    if not orchestrator_proxy:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    return orchestrator_proxy.list_services()

@app.get("/orchestrator/metrics")
async def get_orchestrator_metrics():
    """Get metrics from orchestrator"""
    from fastapi import HTTPException
    if not orchestrator_proxy:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    return orchestrator_proxy.get_metrics()

@app.post("/orchestrator/configure")
async def configure_orchestrator(strategy: str):
    """Configure orchestrator load balancing"""
    from fastapi import HTTPException
    if not orchestrator_proxy:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    return orchestrator_proxy.configure_load_balancer(strategy)

@app.on_event("shutdown")
async def on_shutdown():
    """FastAPI shutdown event handler."""
    global logger, orchestrator_proxy, orchestrator_monitor_task
    
    if logger:
        logger.info("FastAPI shutdown event triggered. Stopping service groups, services, and orchestrator...")
    else:
        print("FastAPI shutdown event triggered. Stopping service groups, services, and orchestrator...")
    
    try:
        # First, stop all service groups (before individual services)
        if orchestrator_proxy:
            try:
                service_groups = orchestrator_proxy.list_service_groups()
                if logger:
                    logger.info(f"Found {len(service_groups)} service groups to stop")
                
                for group in service_groups:
                    group_id = group.get("id")
                    group_name = group.get("name", "unknown")
                    try:
                        if logger:
                            logger.info(f"Stopping service group {group_id} ({group_name})...")
                        orchestrator_proxy.stop_service_group(group_id)
                    except Exception as e:
                        if logger:
                            logger.error(f"Failed to stop service group {group_id}: {e}")
            except Exception as e:
                if logger:
                    logger.error(f"Failed to list service groups: {e}")
        
        # Then stop individual services
        if orchestrator_proxy:
            services = orchestrator_proxy.list_services()
            if logger:
                logger.info(f"Found {len(services)} services to stop")
            
            for service in services:
                service_id = service.get("id")
                service_name = service.get("name", "unknown")
                try:
                    if logger:
                        logger.info(f"Stopping service {service_id} ({service_name})...")
                    orchestrator_proxy.stop_service(service_id)
                except Exception as e:
                    if logger:
                        logger.error(f"Failed to stop service {service_id}: {e}")
        
        # Finally, stop the orchestrator job itself
        if orchestrator_proxy:
            try:
                if logger:
                    logger.info("Stopping orchestrator job...")
                orchestrator_proxy.stop_orchestrator()
            except Exception as e:
                if logger:
                    logger.error(f"Failed to stop orchestrator: {e}")
    except Exception as e:
        if logger:
            logger.error(f"Error during FastAPI shutdown: {e}")
    finally:
        if orchestrator_monitor_task:
            orchestrator_monitor_task.cancel()
            try:
                await orchestrator_monitor_task
            except asyncio.CancelledError:
                pass
            orchestrator_monitor_task = None
        _set_orchestrator_health(False, "Server shut down")

if __name__ == "__main__":
    import uvicorn
    print("Starting AI Factory Server Service...")
    print(f"Node: {os.environ.get('SLURMD_NODENAME', 'unknown')}")
    print(f"Job ID: {os.environ.get('SLURM_JOB_ID', 'unknown')}")
    print("Shutdown handlers registered (SIGTERM, SIGINT, FastAPI shutdown event)")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
