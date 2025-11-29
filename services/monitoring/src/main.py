"""
Main FastAPI application entry point for the Monitoring Service.
Prometheus-based metrics collection via SLURM.
"""

import os
import logging
import signal
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Clean package imports
from src.api.routes import router

# Global logger and monitoring service instance
logger = None
monitoring_service_instance = None


def setup_logging(log_dir: str | Path = "logs") -> Path:
    """
    Set up logging configuration for the monitoring service.
    Overwrites log file on each startup to keep logs fresh.
    
    Args:
        log_dir: Directory where log files will be stored
        
    Returns:
        Path to the log file
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    log_file = log_path / "monitoring_service.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # mode='w' overwrites the log file on startup instead of appending
            logging.FileHandler(log_file, mode='w'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return log_file


def shutdown_handler(signum, frame):
    """Handle graceful shutdown by stopping all running monitoring sessions."""
    global monitoring_service_instance, logger
    
    if logger:
        logger.info(f"Received shutdown signal {signum}. Stopping all monitoring sessions...")
    else:
        print(f"Received shutdown signal {signum}. Stopping all monitoring sessions...")
    
    try:
        if monitoring_service_instance is None:
            from src.monitoring_service import MonitoringService
            monitoring_service_instance = MonitoringService()
        
        # Get all sessions and stop them
        sessions = monitoring_service_instance.list_sessions()
        
        if logger:
            logger.info(f"Found {len(sessions)} sessions to stop")
        else:
            print(f"Found {len(sessions)} sessions to stop")
        
        # Stop each session
        for session in sessions:
            session_id = session.get("session_id")
            try:
                if logger:
                    logger.info(f"Stopping monitoring session {session_id}...")
                else:
                    print(f"Stopping monitoring session {session_id}...")
                monitoring_service_instance.stop(session_id)
            except Exception as e:
                if logger:
                    logger.error(f"Failed to stop session {session_id}: {e}")
                else:
                    print(f"Failed to stop session {session_id}: {e}")
        
        if logger:
            logger.info("All monitoring sessions stopped. Exiting...")
        else:
            print("All monitoring sessions stopped. Exiting...")
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
    title="AI Factory Monitoring Service",
    description="Prometheus-based metrics collection via SLURM",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

log_dir = os.environ.get("APP_LOG_DIR", "logs")
try:
    server_log_path = setup_logging(log_dir)
    logger = logging.getLogger(__name__)
    logger.info(f"Logging to {server_log_path}")
except Exception as e:
    # If logging setup fails, fall back to basic config that writes to stdout
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.warning(f"Failed to setup file logging: {e}. Using stdout only.")

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
        "service": "AI Factory Monitoring Service",
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


@app.on_event("shutdown")
async def on_shutdown():
    """FastAPI shutdown event handler."""
    global monitoring_service_instance, logger
    
    if logger:
        logger.info("FastAPI shutdown event triggered. Stopping all monitoring sessions...")
    else:
        print("FastAPI shutdown event triggered. Stopping all monitoring sessions...")
    
    try:
        if monitoring_service_instance is None:
            from src.monitoring_service import MonitoringService
            monitoring_service_instance = MonitoringService()
        
        sessions = monitoring_service_instance.list_sessions()
        
        for session in sessions:
            session_id = session.get("session_id")
            try:
                if logger:
                    logger.info(f"Stopping monitoring session {session_id}...")
                monitoring_service_instance.stop(session_id)
            except Exception as e:
                if logger:
                    logger.error(f"Failed to stop session {session_id}: {e}")
    except Exception as e:
        if logger:
            logger.error(f"Error during FastAPI shutdown: {e}")


if __name__ == "__main__":
    import uvicorn
    print("Starting AI Factory Monitoring Service...")
    print(f"Node: {os.environ.get('SLURMD_NODENAME', 'unknown')}")
    print(f"Job ID: {os.environ.get('SLURM_JOB_ID', 'unknown')}")
    print("Shutdown handlers registered (SIGTERM, SIGINT, FastAPI shutdown event)")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8004,
        log_level="info"
    )
