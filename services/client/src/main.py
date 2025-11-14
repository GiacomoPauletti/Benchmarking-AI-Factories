"""
Client service main module.
"""

import sys
import argparse
from fastapi import FastAPI
import uvicorn
import logging
import socket

from client_service.api.routes import router
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
    description="Orchestrates client groups for benchmarking AI services on HPC clusters. Supports SLURM job submission, metrics collection via Prometheus, and dynamic service discovery.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "System", "description": "Health checks and system status"},
        {"name": "Client Groups", "description": "Create and manage client groups for benchmarks"},
        {"name": "Execution", "description": "Trigger benchmark execution"},
        {"name": "Monitoring", "description": "Prometheus metrics and targets"},
        {"name": "Logs", "description": "Sync and manage SLURM job logs"}
    ]
)
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
    parser.add_argument("--container", action="store_true",
                       help="Enable container mode for client execution")
    parser.add_argument("--account", default="p200981",
                       help="SLURM account for job submission (default: p200981)")
    
    args = parser.parse_args()
    
    # Extract values
    server_addr = args.server_addr
    host = args.host
    port = args.port
    use_container = args.container
    account = args.account
    
    if use_container:
        logging.info("Container mode enabled for client execution")
    
    logging.info(f"Using SLURM account: {account}")

    # Initialize client manager
    client_manager = ClientManager()
    client_manager.configure(
        server_addr=server_addr, 
        use_container=use_container,
        account=account
    )

    logging.info(f"Starting Client Service on {host}:{port}")
    logging.info(f"Server address: {server_addr}")
    
    # Start the FastAPI server
    uvicorn.run("main:app", host=host, port=port)