"""
Client service main module.
"""

import sys
from fastapi import FastAPI
import uvicorn
import logging

from client_service.api.frontend_router import frontend_router
from client_service.client_manager.slurm_config import SlurmConfig
from client_service.client_manager.client_dispatcher import SlurmClientDispatcher
from client_service.client_manager.client_manager import ClientManager

# =================================== LOGGING CONFIG ====================================
# Suppress all uvicorn logs
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.INFO)

app = FastAPI()
app.include_router(frontend_router)


class ClientService:
    """Main client service class."""
    pass


# ======================================== MAIN =========================================
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python main.py <path_to_slurm_config_file>")
        sys.exit(1)

    slurm_config_path = sys.argv[1]
    SlurmClientDispatcher.slurm_config = SlurmConfig.load_from_file(slurm_config_path)

    #r = requests.post("http://localhost:8001/client-group/71", params={"num_clients": 2})
    
    uvicorn.run("main:app", host="0.0.0.0", port=8001)