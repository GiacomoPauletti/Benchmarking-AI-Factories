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
from prometheus_client import make_asgi_app, REGISTRY

from api.routes import router
from monitoring import ClientGroupCollector
from client_manager.client_manager import ClientManager
from ssh_manager import SSHManager
from fastapi.middleware.cors import CORSMiddleware

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
    # Avoid using the module logger here because the logging system may have
    # already been torn down at interpreter exit (handlers closed). Use
    # stdout/stderr prints as a safe fallback to avoid "I/O operation on closed file.".
    try:
        print(f"[cleanup] Cleaning up logs in {log_dir}...", file=sys.stderr)

        # Remove all loadgen log files (including new format with group and job IDs)
        patterns = [
            "loadgen-*.out", 
            "loadgen-*.err", 
            "loadgen-*-container.log",      # Old format
            "loadgen-group*-container.log", # New format
            "loadgen-results-*.json",       # Old format
            "loadgen-group*-results.json",  # New format
            "loadgen-group*-config.json"    # New format
        ]
        for pattern in patterns:
            for file in glob.glob(os.path.join(log_dir, pattern)):
                try:
                    os.remove(file)
                    print(f"[cleanup] Removed {file}", file=sys.stderr)
                except Exception as e:
                    print(f"[cleanup] Could not remove {file}: {e}", file=sys.stderr)

        # Remove snapshot directories
        snapshots_dir = os.path.join(log_dir, "snapshots")
        if os.path.exists(snapshots_dir):
            import shutil
            shutil.rmtree(snapshots_dir, ignore_errors=True)
            print(f"[cleanup] Removed {snapshots_dir}", file=sys.stderr)

        print("[cleanup] Log cleanup complete", file=sys.stderr)
    except Exception as e:
        # Best-effort: avoid calling logger here since handlers may be closed.
        try:
            print(f"[cleanup] Error during log cleanup: {e}", file=sys.stderr)
        except Exception:
            # Nothing else we can do during shutdown
            pass

# Register cleanup handler
atexit.register(cleanup_logs)

app = FastAPI(
    title="AI Factory Client Service",
    description="Manages client groups on HPC clusters via SLURM. Provides job submission, metrics collection via Prometheus, and log management. Client groups can be used by benchmark orchestrators or other services.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "System", "description": "Health checks and system status"},
        {"name": "Client Groups", "description": "Create and manage client groups"},
        {"name": "Execution", "description": "Trigger client group execution"},
        {"name": "Monitoring", "description": "Prometheus metrics and targets"},
                {"name": "Logs", "description": "Sync and manage SLURM job logs"}
    ]
)

# Initialize ClientManager and register collector
# Note: We rely on env vars for configuration in this context
cm = ClientManager()
try:
    REGISTRY.register(ClientGroupCollector(cm))
except ValueError:
    # Already registered (e.g. during reload)
    pass

# Add Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# =================================== CORS MIDDLEWARE ===================================

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    parser.add_argument("server_addr", nargs="?", default=None, 
                       help="Server address (default: $SERVER_URL or http://server:8001)")
    parser.add_argument("--host", default="0.0.0.0", 
                       help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8002, 
                       help="Port to bind to (default: 8002)")
    parser.add_argument("--container", action="store_true",
                       help="Enable container mode for client execution")
    parser.add_argument("--account", default="p200981",
                       help="SLURM account for job submission (default: p200981)")
    
    args = parser.parse_args()
    
    # Extract values - prefer environment variable over hardcoded default
    server_addr = args.server_addr or os.environ.get("SERVER_URL", "http://server:8001")
    host = args.host
    logging.debug(f"args.port: {args.port}")
    port = args.port
    use_container = args.container
    account = args.account
    
    if use_container:
        logging.info("Container mode enabled for client execution")
    
    logging.info(f"Using SLURM account: {account}")

    # Initialize client manager
    client_manager = ClientManager(
        server_addr=server_addr, 
        use_container=use_container,
        account=account
        )

    # Setup SSH tunnel for SLURM REST API (shared across all client groups)
    logging.info("Setting up SSH tunnel for SLURM REST API...")
    try:
        ssh_manager = SSHManager()
        tunnel_port = ssh_manager.setup_slurm_rest_tunnel(local_port=6821)
        logging.info(f"SSH tunnel established on localhost:{tunnel_port}")
    except Exception as e:
        logging.error(f"Failed to setup SSH tunnel: {e}")
        logging.warning("Service will start but client group creation may fail without tunnel")

    logging.info(f"Starting Client Service on {host}:{port}")
    logging.info(f"Server address: {server_addr}")
    
    remote_base_path_template = os.environ.get(
        'REMOTE_BASE_PATH', 
        '~/ai-factory-benchmarks'
    )
    
    remote_base_path = ""
    # Expand ~ to /home/users/$USER (NOT tier2 - SLURM daemon can't write there)
    if remote_base_path_template.startswith('~'):
        # Use standard home path /home/users/$USER
        remote_base_path = remote_base_path_template.replace('~', f'/home/users/{ssh_manager.ssh_user}', 1)
    else:
        remote_base_path = remote_base_path_template

    import time
    time.sleep(10)
    client_remote_path = f"{remote_base_path.rstrip('/')}/src/client/"
    ssh_manager.sync_directory_to_remote(os.getcwd()+"/src/client/", client_remote_path)

    # Start the FastAPI server
    uvicorn.run("main:app", host=host, port=port)
