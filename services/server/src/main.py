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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

# Clean package imports
from api.routes import router, set_orchestrator_proxy, start_batch_metrics_fetcher, stop_batch_metrics_fetcher
from api.orchestrator_routes import router as orchestrator_router, set_orchestrator_control_functions
from logging_setup import setup_logging
from orchestrator_initializer import (
    initialize_orchestrator_proxy,
    load_orchestrator_settings,
    submit_orchestrator_job,
    wait_for_orchestrator_url,
    wait_for_orchestrator_ready,
)

# Global logger and orchestrator proxy
logger = None
orchestrator_proxy = None
orchestrator_monitor_task: Optional[asyncio.Task] = None
ssh_manager_instance = None  # Keep SSH manager for on-demand orchestrator start


@dataclass
class OrchestratorSession:
    """Extended state for orchestrator session tracking."""

    alive: bool = False
    last_check: Optional[str] = None
    last_error: Optional[str] = "Orchestrator not started"
    job_id: Optional[str] = None
    job_state: Optional[str] = None
    started_at: Optional[datetime] = None
    time_limit_minutes: Optional[int] = None
    orchestrator_url: Optional[str] = None


orchestrator_session = OrchestratorSession()


# Legacy alias for backward compatibility
@dataclass
class OrchestratorHealthState:
    """Lightweight shared state for orchestrator availability."""

    alive: bool = False
    last_check: Optional[str] = None
    last_error: Optional[str] = "Orchestrator not initialized"


orchestrator_health = OrchestratorHealthState()


def _set_orchestrator_health(alive: bool, error: Optional[str] = None) -> None:
    """Update orchestrator health state and log transitions."""

    global orchestrator_health, orchestrator_session, logger

    previous = orchestrator_health.alive
    orchestrator_health.alive = alive
    orchestrator_health.last_check = datetime.now(timezone.utc).isoformat()
    orchestrator_health.last_error = error

    # Sync with session state
    orchestrator_session.alive = alive
    orchestrator_session.last_check = orchestrator_health.last_check
    orchestrator_session.last_error = error

    if logger and previous != alive:
        if alive:
            logger.info("Orchestrator marked healthy")
        else:
            logger.warning("Orchestrator marked unhealthy: %s", error)


def _get_orchestrator_session() -> OrchestratorSession:
    """Get current orchestrator session state."""
    return orchestrator_session


async def _start_orchestrator_async(time_limit_minutes: int) -> dict:
    """
    Start the orchestrator on demand with a specified time limit.

    Args:
        time_limit_minutes: SLURM job time limit in minutes

    Returns:
        dict with 'success', 'job_id', and optionally 'error' keys
    """
    global orchestrator_proxy, orchestrator_session, orchestrator_monitor_task, ssh_manager_instance, logger

    if ssh_manager_instance is None:
        return {"success": False, "error": "SSH manager not initialized"}

    try:
        settings = load_orchestrator_settings()
        # Override time limit with user-provided value
        settings.time_limit_minutes = time_limit_minutes

        remote_base_path = os.environ.get("REMOTE_BASE_PATH", "~/ai-factory-benchmarks")

        # Resolve ~ if present
        if remote_base_path.startswith("~"):
            success, stdout, stderr = ssh_manager_instance.execute_remote_command("echo $HOME")
            if success and stdout:
                home_dir = stdout.strip()
                remote_base_path = remote_base_path.replace("~", home_dir, 1)

        if logger:
            logger.info(f"Starting orchestrator with time_limit={time_limit_minutes} minutes")

        # Clear old orchestrator.env file to avoid reading stale URLs
        remote_env_file = f"{remote_base_path}/orchestrator.env"
        ssh_manager_instance.execute_remote_command(f"rm -f {remote_env_file}")
        if logger:
            logger.info(f"Cleared old orchestrator.env file: {remote_env_file}")

        # Submit SLURM job
        success, message = submit_orchestrator_job(ssh_manager_instance, remote_base_path, settings)

        if not success:
            return {"success": False, "error": message}

        # Extract job ID from message
        job_id = None
        if "Job submitted:" in message:
            job_id = message.split("Job submitted:")[-1].strip()

        # Update session state
        orchestrator_session.job_id = job_id
        orchestrator_session.job_state = "PENDING"
        orchestrator_session.started_at = datetime.now(timezone.utc)
        orchestrator_session.time_limit_minutes = time_limit_minutes

        # Wait for orchestrator URL
        remote_env_file = f"{remote_base_path}/orchestrator.env"
        orchestrator_url = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: wait_for_orchestrator_url(ssh_manager_instance, remote_env_file, timeout=120)
        )

        if not orchestrator_url:
            orchestrator_session.last_error = "Timeout waiting for orchestrator URL"
            return {"success": False, "job_id": job_id, "error": "Timeout waiting for orchestrator URL"}

        orchestrator_session.orchestrator_url = orchestrator_url
        orchestrator_session.job_state = "STARTING"

        # Wait for orchestrator to be ready
        is_ready = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: wait_for_orchestrator_ready(ssh_manager_instance, orchestrator_url, timeout=180, default_port=settings.port)
        )

        if not is_ready:
            orchestrator_session.last_error = "Orchestrator failed to become ready"
            orchestrator_session.job_state = "FAILED"
            return {"success": False, "job_id": job_id, "error": "Orchestrator failed to become ready"}

        # Create OrchestratorProxy
        from orchestrator_proxy import OrchestratorProxy
        orchestrator_proxy = OrchestratorProxy(
            orchestrator_url=orchestrator_url,
            ssh_manager=ssh_manager_instance,
            orchestrator_job_id=job_id
        )

        # Inject into routes
        set_orchestrator_proxy(orchestrator_proxy)
        _set_orchestrator_health(True, None)
        orchestrator_session.job_state = "RUNNING"

        # Start health monitor if not running
        if orchestrator_monitor_task is None or orchestrator_monitor_task.done():
            orchestrator_monitor_task = asyncio.create_task(_orchestrator_monitor_loop())

        # Start batch metrics fetcher to reduce SSH tunnel contention
        start_batch_metrics_fetcher()

        if logger:
            logger.info(f"✓ Orchestrator started successfully (job_id: {job_id})")

        return {"success": True, "job_id": job_id}

    except Exception as e:
        error_msg = f"Failed to start orchestrator: {str(e)}"
        if logger:
            logger.exception(error_msg)
        orchestrator_session.last_error = error_msg
        return {"success": False, "error": error_msg}


async def _stop_orchestrator_async() -> dict:
    """
    Stop the running orchestrator.

    Returns:
        dict with 'success' and optionally 'error' keys
    """
    global orchestrator_proxy, orchestrator_session, orchestrator_monitor_task, logger

    try:
        # Stop batch metrics fetcher first
        stop_batch_metrics_fetcher()
        
        # Stop the orchestrator via proxy
        if orchestrator_proxy:
            try:
                orchestrator_proxy.stop_orchestrator()
            except Exception as e:
                if logger:
                    logger.warning(f"Error stopping orchestrator via proxy: {e}")

        # Clear state
        orchestrator_proxy = None
        orchestrator_session.alive = False
        orchestrator_session.job_id = None
        orchestrator_session.job_state = None
        orchestrator_session.started_at = None
        orchestrator_session.time_limit_minutes = None
        orchestrator_session.orchestrator_url = None
        orchestrator_session.last_error = "Orchestrator stopped by user"

        _set_orchestrator_health(False, "Orchestrator stopped by user")

        if logger:
            logger.info("Orchestrator stopped successfully")

        return {"success": True}

    except Exception as e:
        error_msg = f"Failed to stop orchestrator: {str(e)}"
        if logger:
            logger.exception(error_msg)
        return {"success": False, "error": error_msg}


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
    """Readiness check endpoint - server is ready to accept requests.
    
    With on-demand orchestrator, the server is ready once SSH manager is initialized.
    The orchestrator can be started on-demand via /api/v1/orchestrator/start.
    """
    global ssh_manager_instance, orchestrator_proxy

    # Server is ready if SSH manager is initialized (can accept orchestrator start requests)
    ssh_ready = ssh_manager_instance is not None
    
    if not ssh_ready:
        return Response(
            content=json.dumps({
                "status": "not ready",
                "reason": "SSH manager not initialized",
                "details": "Server is still initializing SSH connection to HPC cluster."
            }),
            status_code=503,
            media_type="application/json"
        )

    # Include orchestrator status in response for informational purposes
    orchestrator_running = orchestrator_proxy is not None and orchestrator_health.alive
    
    return {
        "status": "ready",
        "orchestrator": "running" if orchestrator_running else "not started",
        "message": "Use POST /api/v1/orchestrator/start to launch the orchestrator" if not orchestrator_running else None
    }

# Include API routes
app.include_router(router, prefix="/api/v1")
app.include_router(orchestrator_router, prefix="/api/v1")

@app.on_event("startup")
async def on_startup():
    """FastAPI startup event handler - set up SSH manager for on-demand orchestrator control."""
    global logger, ssh_manager_instance
    
    # SLURM REST API now uses the same SOCKS5 proxy as the orchestrator
    # No separate tunnel needed - SlurmClient will route through socks5h://localhost:1080
    if logger:
        logger.info("SLURM REST API will use SOCKS5 proxy (no separate tunnel needed)")
    else:
        print("SLURM REST API will use SOCKS5 proxy (no separate tunnel needed)")

    try:
        from ssh_manager import SSHManager
        ssh_manager_instance = SSHManager()
        
        # Establish reverse SSH tunnel for Pushgateway
        # This allows processes on MeluXina to push metrics to the local Pushgateway
        pushgateway_host = os.environ.get("PUSHGATEWAY_HOST", "pushgateway")
        pushgateway_port = int(os.environ.get("PUSHGATEWAY_PORT", "9091"))
        if ssh_manager_instance.establish_reverse_tunnel(
            local_host=pushgateway_host,
            local_port=pushgateway_port,
            remote_port=pushgateway_port
        ):
            if logger:
                logger.info(f"✓ Reverse tunnel established for Pushgateway (MeluXina:{pushgateway_port} -> {pushgateway_host}:{pushgateway_port})")
        else:
            if logger:
                logger.warning(f"✗ Failed to establish reverse tunnel for Pushgateway - metrics push from HPC will not work")
        
        # Register orchestrator control functions with the API router
        set_orchestrator_control_functions(
            get_session_fn=_get_orchestrator_session,
            start_fn=_start_orchestrator_async,
            stop_fn=_stop_orchestrator_async,
        )
        
        # Start batch metrics fetcher immediately on startup
        # It will handle gracefully when orchestrator is not yet available
        start_batch_metrics_fetcher()
        if logger:
            logger.info("✓ Background batch metrics fetcher started")
        
        if logger:
            logger.info("✓ Server is ready - orchestrator control available via /api/v1/orchestrator/start")
            logger.info("  Use POST /api/v1/orchestrator/start to launch the orchestrator on demand")
        else:
            print("✓ Server is ready - orchestrator control available via /api/v1/orchestrator/start")
            print("  Use POST /api/v1/orchestrator/start to launch the orchestrator on demand")
        
        # Mark as healthy but orchestrator not yet started
        _set_orchestrator_health(False, "Orchestrator not started - use /api/v1/orchestrator/start")
                
    except Exception as e:
        error_msg = (
            f"✗ CRITICAL: Server initialization FAILED: {e}\n"
            "Possible causes:\n"
            "  - SSH connection to MeluXina failed\n"
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
