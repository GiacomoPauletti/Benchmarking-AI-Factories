"""
Client service main module.
"""

import sys
import argparse
from fastapi import FastAPI
import uvicorn
import logging
import socket
import os
import atexit
import glob

from api.routes import router
from client_manager.client_manager import ClientManager

# =================================== LOGGING CONFIG ====================================
# Set up logging to both console and file
log_dir = "/app/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "client.log")

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode='w')  
    ],
    force=True 
)

# Suppress some uvicorn logs but keep our application logs visible
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# =================================== CLEANUP HANDLER ===================================
def cleanup_logs():
    """Clean up synced logs on service shutdown."""
    log_dir = "/app/logs"
    logger.info(f"Cleaning up logs in {log_dir}...")
    
    try:
        # Remove all loadgen log files
        for pattern in ["loadgen-*.out", "loadgen-*.err", "loadgen-*-container.log", "loadgen-results-*.json"]:
            for file in glob.glob(os.path.join(log_dir, pattern)):
                try:
                    os.remove(file)
                    logger.debug(f"Removed {file}")
                except Exception as e:
                    logger.warning(f"Could not remove {file}: {e}")
        
        # Remove snapshot directories
        snapshots_dir = os.path.join(log_dir, "snapshots")
        if os.path.exists(snapshots_dir):
            import shutil
            shutil.rmtree(snapshots_dir, ignore_errors=True)
            logger.debug(f"Removed {snapshots_dir}")
        
        logger.info("Log cleanup complete")
    except Exception as e:
        logger.error(f"Error during log cleanup: {e}")

# Register cleanup handler
atexit.register(cleanup_logs)

app = FastAPI(
    title="AI Factory Client Service",
    description="Manages client groups for local load testing. Provides job execution, metrics collection via Prometheus, and log management. Client groups can be used by benchmark orchestrators or other services.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "System", "description": "Health checks and system status"},
        {"name": "Client Groups", "description": "Create and manage client groups"},
        {"name": "Execution", "description": "Trigger client group execution"},
        {"name": "Monitoring", "description": "Prometheus metrics and targets"},
        {"name": "Logs", "description": "Sync and manage load test logs"}
    ]
)
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

app.include_router(router, prefix="/api/v1")



# ======================================== MAIN =========================================
if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="AI Factory Client Service")
    parser.add_argument("server_addr", nargs="?", default="http://localhost:8001", 
                       help="Server address (default: http://localhost:8001)")
    parser.add_argument("--host", default="0.0.0.0", 
                       help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8002, 
                       help="Port to bind to (default: 8002)")
    
    args = parser.parse_args()
    
    # Extract values
    server_addr = args.server_addr
    host = args.host
    logging.debug(f"args.port: {args.port}")
    port = args.port
    
    # Initialize client manager
    client_manager = ClientManager()
    client_manager.configure(
        server_addr=server_addr
    )

    logging.info(f"Starting Client Service on {host}:{port}")
    logging.info(f"Server address: {server_addr}")

    # Start the FastAPI server
    uvicorn.run("main:app", host=host, port=port)
