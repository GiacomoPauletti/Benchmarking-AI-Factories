"""
Main FastAPI application entry point for the Server Service.
SLURM + Apptainer orchestration for AI workloads.
"""

import os
import logging
import signal
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Clean package imports
from api.routes import router, set_orchestrator_proxy
from logging_setup import setup_logging
from orchestrator_initializer import initialize_orchestrator_proxy

# Global logger and orchestrator proxy
logger = None
orchestrator_proxy = None

def shutdown_handler(signum, frame):
    """Handle graceful shutdown by stopping all running services and orchestrator."""
    global logger, orchestrator_proxy
    
    if logger:
        logger.info(f"Received shutdown signal {signum}. Stopping all services...")
    else:
        print(f"Received shutdown signal {signum}. Stopping all services...")
    
    try:
        # First, stop the orchestrator to prevent new jobs
        if orchestrator_proxy:
            try:
                if logger:
                    logger.info("Stopping orchestrator job...")
                else:
                    print("Stopping orchestrator job...")
                orchestrator_proxy.stop_orchestrator()
            except Exception as e:
                if logger:
                    logger.error(f"Failed to stop orchestrator: {e}")
                else:
                    print(f"Failed to stop orchestrator: {e}")
        
        # Get all running services from orchestrator
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
                except Exception as e:
                    if logger:
                        logger.error(f"Failed to stop service {service_id}: {e}")
                    else:
                        print(f"Failed to stop service {service_id}: {e}")
        
        if logger:
            logger.info("All services stopped. Exiting...")
        else:
            print("All services stopped. Exiting...")
    except Exception as e:
        if logger:
            logger.error(f"Error during shutdown: {e}")
        else:
            print(f"Error during shutdown: {e}")
    
    sys.exit(0)

# Register shutdown handlers for SIGTERM and SIGINT
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
    """Health check endpoint - server is healthy but may not be ready."""
    global orchestrator_proxy
    
    return {
        "status": "healthy",
        "orchestrator_initialized": orchestrator_proxy is not None,
        "ready": orchestrator_proxy is not None
    }

@app.get("/ready")
async def ready():
    """Readiness check endpoint - server is ready to accept requests."""
    global orchestrator_proxy
    
    if orchestrator_proxy is None:
        from fastapi import Response
        import os
        
        # Provide helpful error message
        remote_base = os.getenv("REMOTE_BASE_PATH", "~/ai-factory-benchmarks")
        error_detail = {
            "status": "not ready",
            "reason": "orchestrator not initialized",
            "details": (
                "The orchestrator failed to initialize. This is a critical error that prevents "
                "the server from accepting service deployment requests."
            ),
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
            content=str(error_detail).replace("'", '"'),
            status_code=503,
            media_type="application/json"
        )
    
    return {"status": "ready", "orchestrator": "available"}

# Include API routes
app.include_router(router, prefix="/api/v1")

@app.on_event("startup")
async def on_startup():
    """FastAPI startup event handler - set up SSH tunnel and wait for orchestrator."""
    global logger, orchestrator_proxy
    
    if logger:
        logger.info("Setting up SSH tunnel to SLURM REST API...")
    else:
        print("Setting up SSH tunnel to SLURM REST API...")
    
    try:
        from ssh_manager import SSHManager
        ssh_manager = SSHManager()
        ssh_manager.setup_slurm_rest_tunnel(local_port=6820)
        
        if logger:
            logger.info("SSH tunnel established successfully on port 6820")
        else:
            print("SSH tunnel established successfully on port 6820")
            
        # Initialize OrchestratorProxy - this blocks until orchestrator is ready
        if logger:
            logger.info("Initializing orchestrator (may take up to 2 minutes)...")
        else:
            print("Initializing orchestrator (may take up to 2 minutes)...")
            
        orchestrator_proxy = initialize_orchestrator_proxy(ssh_manager)
        
        if orchestrator_proxy:
            # Inject orchestrator proxy into routes module
            set_orchestrator_proxy(orchestrator_proxy)
            
            if logger:
                logger.info("✓ Server is ready - orchestrator initialized successfully")
            else:
                print("✓ Server is ready - orchestrator initialized successfully")
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
    global logger, orchestrator_proxy
    
    if logger:
        logger.info("FastAPI shutdown event triggered. Stopping orchestrator and services...")
    else:
        print("FastAPI shutdown event triggered. Stopping orchestrator and services...")
    
    try:
        # Stop orchestrator first
        if orchestrator_proxy:
            try:
                if logger:
                    logger.info("Stopping orchestrator job...")
                orchestrator_proxy.stop_orchestrator()
            except Exception as e:
                if logger:
                    logger.error(f"Failed to stop orchestrator: {e}")
        
        # Get all running services from orchestrator
        if orchestrator_proxy:
            services = orchestrator_proxy.list_services()
            
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
    except Exception as e:
        if logger:
            logger.error(f"Error during FastAPI shutdown: {e}")

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
