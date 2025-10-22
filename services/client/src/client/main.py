"""
Client main module - manages individual clients and exposes FastAPI endpoints
"""

import sys
import logging
import socket
from typing import List
from fastapi import FastAPI
import uvicorn

from client.client import VLLMClient
from client.api.client_service_router import client_service_router
from client.api.monitor_router import monitor_proxy_router
from client.client_group import ClientGroup

# =================================== LOGGING CONFIG ====================================
logging.basicConfig(level=logging.DEBUG)

# Suppress some verbose logs
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.INFO)

# =================================== FASTAPI APP ====================================
app = FastAPI(
    title="AI Factory Client Process",
    description="Individual client process that runs clients and handles commands from client_service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Include routers
app.include_router(client_service_router)
app.include_router(monitor_proxy_router)

# =================================== GLOBAL VARIABLES ====================================
# No global variables needed anymore

# ======================================== MAIN =========================================
if __name__ == "__main__":
    if len(sys.argv) != 5:
        logging.fatal("Invalid number of arguments. Required: num_clients server_addr client_service_addr benchmark_id")
        sys.exit(1)

    print("Starting Client Process...")

    client_count = int(sys.argv[1])
    server_addr = sys.argv[2]
    client_service_addr = sys.argv[3]
    benchmark_id = int(sys.argv[4])
    
    logging.debug(f"Command line parameters: {sys.argv[1]} {sys.argv[2]} {sys.argv[3]} {sys.argv[4]}")

    logging.debug(f"Creating {client_count} clients for benchmark {benchmark_id}.")
    # Create clients but don't start them yet
    clients = []
    for i in range(client_count):
        client = VLLMClient()
        clients.append(client)

    # Get the local IP address for registration
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    local_addr = f"http://{local_ip}:8080"
    
    # Configure the client service router with all parameters
    client_group = ClientGroup()
    client_group.configure(
        benchmark_id=benchmark_id,
        clients=clients,
        server_addr=server_addr,
        client_service_addr=client_service_addr,
        local_address=local_addr
    )

    logging.debug(f"Client service router configured with {len(clients)} clients for benchmark {benchmark_id}")
    

    # Register this client process with the client_service
    import requests
    try:
        response = requests.post(
            f"{client_service_addr}/api/v1/client-group/{benchmark_id}/connect",
            json={"client_address": local_addr}
        )
        if response.status_code == 201:
            logging.info(f"Successfully registered with client_service for benchmark {benchmark_id} at {local_addr}")
        else:
            logging.error(f"Failed to register with client_service: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Error registering with client_service: {e}")

    # Start the FastAPI server
    logging.info(f"Starting FastAPI server on port 8080 for benchmark {benchmark_id}")
    uvicorn.run(app, host=local_ip, port=8080) # type: ignore
