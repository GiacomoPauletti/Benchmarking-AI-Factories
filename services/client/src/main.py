"""
Client service main module.
"""

import sys
import argparse
from fastapi import FastAPI
import uvicorn
import logging
import socket

from client_service.api.frontend_router import frontend_router
from client_service.api.monitor_router import monitor_router
from client_service.deployment.slurm_config import SlurmConfig
from client_service.deployment.client_dispatcher import SlurmClientDispatcher
from client_service.client_manager.client_manager import ClientManager

# =================================== LOGGING CONFIG ====================================
# Always log to console (stdout) with debug level
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Suppress some uvicorn logs but keep our application logs visible
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.INFO)

app = FastAPI(
    title="AI Factory Client Service",
    description="Spawns clients for testing Server Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)
app.include_router(frontend_router, prefix="/api/v1")
app.include_router(monitor_router, prefix="/api/v1")



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
    parser.add_argument("--slurm-config", 
                       help="Path to SLURM configuration file")
    parser.add_argument("--container", action="store_true",
                       help="Enable container mode for client execution")
    
    args = parser.parse_args()
    
    # Extract values
    server_addr = args.server_addr
    host = args.host
    port = args.port
    use_container = args.container
    slurm_config_path = args.slurm_config
    
    if use_container:
        logging.info("Container mode enabled for client execution")
    
    # Load Slurm configuration
    if slurm_config_path:
        # Use provided config file
        SlurmClientDispatcher.slurm_config = SlurmConfig.load_from_file(slurm_config_path)
        logging.info(f"Loaded Slurm config from file: {slurm_config_path}")
    else:
        # Use auto-detected configuration
        SlurmClientDispatcher.slurm_config = SlurmConfig.tmp_load_default()
        logging.info("Using auto-detected Slurm configuration")

    # Initialize client manager
    client_manager = ClientManager()
    client_manager.configure(
        server_addr=server_addr, 
        use_container=use_container
    )

    logging.info(f"Starting Client Service on {host}:{port}")
    logging.info(f"Server address: {server_addr}")
    
    # Start the FastAPI server
    uvicorn.run("main:app", host=host, port=port)