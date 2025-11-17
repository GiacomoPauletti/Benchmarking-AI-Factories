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
from api.routes import router
from logging_setup import setup_logging

# Global logger and server service instance
logger = None
server_service_instance = None

def shutdown_handler(signum, frame):
    """Handle graceful shutdown by stopping all running services."""
    global server_service_instance, logger
    
    if logger:
        logger.info(f"Received shutdown signal {signum}. Stopping all services...")
    else:
        print(f"Received shutdown signal {signum}. Stopping all services...")
    
    try:
        if server_service_instance is None:
            # Import here to avoid circular dependency
            from server_service import ServerService
            server_service_instance = ServerService()
        
        # Get all running services
        services = server_service_instance.list_running_services()
        
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
                server_service_instance.stop_service(service_id)
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
    """Health check endpoint."""
    return {"status": "healthy"}

# Include API routes
app.include_router(router, prefix="/api/v1")

@app.on_event("startup")
async def on_startup():
    """FastAPI startup event handler - set up SSH tunnel."""
    global logger
    
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
    except Exception as e:
        if logger:
            logger.warning(f"Failed to set up SSH tunnel: {e}")
            logger.warning("The server will attempt to create tunnels on-demand, but this may cause delays.")
        else:
            print(f"WARNING: Failed to set up SSH tunnel: {e}")
            print("The server will attempt to create tunnels on-demand, but this may cause delays.")

@app.on_event("shutdown")
async def on_shutdown():
    """FastAPI shutdown event handler."""
    global server_service_instance, logger
    
    if logger:
        logger.info("FastAPI shutdown event triggered. Stopping all services...")
    else:
        print("FastAPI shutdown event triggered. Stopping all services...")
    
    try:
        if server_service_instance is None:
            from server_service import ServerService
            server_service_instance = ServerService()
        
        services = server_service_instance.list_running_services()
        
        for service in services:
            service_id = service.get("id")
            service_name = service.get("name", "unknown")
            try:
                if logger:
                    logger.info(f"Stopping service {service_id} ({service_name})...")
                server_service_instance.stop_service(service_id)
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

