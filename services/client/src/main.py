"""
Client service main module.
"""

import sys
from fastapi import FastAPI
import uvicorn
import logging
import socket

from client_service.api.frontend_router import frontend_router
from client_service.api.client_router import client_router
from client_service.api.monitor_router import monitor_router
from client_service.deployment.slurm_config import SlurmConfig
from client_service.deployment.client_dispatcher import SlurmClientDispatcher
from client_service.client_manager.client_manager import ClientManager

"""
Client service main module.
"""

import sys
from fastapi import FastAPI
import uvicorn
import logging
import socket

from client_service.api.frontend_router import frontend_router
from client_service.api.client_router import client_router
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
app.include_router(client_router, prefix="/api/v1")
app.include_router(monitor_router, prefix="/api/v1")


class ClientService:
    """Main client service class."""
    pass


# ======================================== MAIN =========================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        logging.fatal("Usage: python main.py <server_addr> [path_to_slurm_config_file] [--container]")
        sys.exit(1)

    server_addr = sys.argv[1]
    use_container = False
    slurm_config_path = None
    
    # Parse remaining arguments
    for i in range(2, len(sys.argv)):
        arg = sys.argv[i]
        if arg == "--container":
            use_container = True
            logging.info("Container mode enabled for client execution")
        elif not arg.startswith("--") and slurm_config_path is None:
            # This is the slurm config file path
            slurm_config_path = arg
    
    # Load Slurm configuration
    if slurm_config_path:
        # Use provided config file
        SlurmClientDispatcher.slurm_config = SlurmConfig.load_from_file(slurm_config_path)
        logging.info(f"Loaded Slurm config from file: {slurm_config_path}")
    else:
        # Use auto-detected configuration
        SlurmClientDispatcher.slurm_config = SlurmConfig.tmp_load_default()
        logging.info("Using auto-detected Slurm configuration")

    #r = requests.post("http://localhost:8001/client-group/71", params={"num_clients": 2})
    
    CLIENT_SERVICE_IP   = socket.gethostname()
    CLIENT_SERVICE_PORT = 8001

    client_manager = ClientManager()
    client_manager.configure(server_addr=server_addr, client_service_addr=f"http://{CLIENT_SERVICE_IP}:{CLIENT_SERVICE_PORT}", use_container=use_container)

    uvicorn.run("main:app", host=CLIENT_SERVICE_IP, port=CLIENT_SERVICE_PORT)