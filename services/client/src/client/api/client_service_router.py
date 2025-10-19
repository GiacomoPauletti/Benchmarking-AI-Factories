from fastapi import APIRouter, status
from pydantic import BaseModel
import logging
from typing import List

from ..client_group import ClientGroup
from ..client import VLLMClient

logger = logging.getLogger(__name__)

client_service_router = APIRouter()


class RunResponse(BaseModel):
    status: str
    num_clients: int


class StatusResponse(BaseModel):
    benchmark_id: int
    num_clients: int
    server_addr: str
    client_service_addr: str
    local_address: str
    created_at: float


@client_service_router.post("/run", status_code=status.HTTP_200_OK, response_model=RunResponse)
async def run_clients():
    """Start all the created clients when called by client_service"""
    client_group = ClientGroup()
    
    if not client_group.clients:
        logger.error("No clients available to run")
        return RunResponse(status="error", num_clients=0)
    
    logger.info(f"Starting {client_group.num_clients} clients for benchmark {client_group.benchmark_id}")
    
    # Setup benchmark before running clients
    if client_group.server_addr:
        service_id = VLLMClient.setup_benchmark(client_group.server_addr)
        if not service_id:
            logger.error("Failed to setup vLLM benchmark service")
            return RunResponse(status="error", num_clients=0)
        logger.info(f"vLLM benchmark service setup complete with ID: {service_id}")
    else:
        logger.error("Server address not configured")
        return RunResponse(status="error", num_clients=0)
    
    # Use ClientGroup's run_all_clients method
    started_count = client_group.run_all_clients()
    
    return RunResponse(status="started", num_clients=started_count)


@client_service_router.get("/status", status_code=status.HTTP_200_OK, response_model=StatusResponse)
async def get_status():
    """Get the current status of the ClientGroup"""
    client_group = ClientGroup()
    status_data = client_group.get_status()
    return StatusResponse(**status_data)

