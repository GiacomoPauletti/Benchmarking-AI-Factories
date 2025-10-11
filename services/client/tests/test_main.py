"""
Client service main module.
"""

import sys
from fastapi import FastAPI
from api.frontend_router import frontend_router
from slurm_config import SlurmConfig
import uvicorn

app = FastAPI()
app.include_router(frontend_router)


class ClientService:
    """Main client service class."""
    pass


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python main.py <path_to_slurm_config_file>")
        sys.exit(1)

    slurm_config_path = sys.argv[1]
    SlurmConfig.load_from_file(slurm_config_path)

    
    uvicorn.run(app, host="0.0.0.0", port=8001)