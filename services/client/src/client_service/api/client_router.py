from fastapi import FastAPI, APIRouter, HTTPException, status
from pydantic import BaseModel
import logging
from typing import List

from client_service.client_manager.client_manager import ClientManager, ClientManagerResponseStatus

logger = logging.getLogger("client_service.client_router")
logger.addHandler(logging.NullHandler())


client_router  = APIRouter()
client_manager = ClientManager()

class ConnectPayload(BaseModel):
    client_address: str

@client_router.post("/client-group/{benchmark_id}/connect", status_code=status.HTTP_201_CREATED)
async def connect_client(benchmark_id: int, payload: ConnectPayload):
    """
    Register a client process address for the given benchmark group.
    The client process registers once and will manage multiple internal clients.
    """
    logger.debug(f"Register request for benchmark {benchmark_id} from {payload.client_address}")
    ok = client_manager.register_client(benchmark_id, payload.client_address)
    if not ok:
        logger.warning(f"Register failed: unknown benchmark {benchmark_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark id not found")
    logger.info(f"Registered client process for benchmark {benchmark_id}: {payload.client_address}")
    return {"status": "registered", "benchmark_id": benchmark_id, "client_address": payload.client_address}