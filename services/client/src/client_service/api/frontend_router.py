from fastapi import FastAPI, APIRouter, HTTPException, status
from pydantic import BaseModel
from client_service.client_manager.client_manager import ClientManager, ClientManagerResponseStatus

import logging

logging.basicConfig(level=logging.DEBUG)

frontend_router = APIRouter()

client_manager = ClientManager()

@frontend_router.post("/client-group/{benchmark_id}")
async def add_client_group(benchmark_id : int, num_clients: int):
    print("Endpoint called!")  # <--- Add this
    logging.debug(f"Received request to add client group for benchmark_id {benchmark_id} with {num_clients} clients.")
    response = client_manager.add_client_group(benchmark_id, num_clients)
    if response != ClientManagerResponseStatus.OK:
        logging.debug(f"Failed to add client group for benchmark_id {benchmark_id} with {num_clients} clients.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    logging.debug(f"Successfully added client group for benchmark_id {benchmark_id} with {num_clients} clients.")
    return {"status": "Client group added successfully"}

@frontend_router.delete("/client-group/{benchmark_id}")
async def delete_client_group(benchmark_id : int):
    logging.debug(f"Received request to remove client group for benchmark_id {benchmark_id}.")
    client_manager.remove_client_group(benchmark_id)
    logging.debug(f"Successfully removed client group for benchmark_id {benchmark_id}.")
    return {"status": "Client group removed successfully"}
