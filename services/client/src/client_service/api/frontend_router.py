from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import logging

from client_service.client_manager.client_manager import ClientManager, ClientManagerResponseStatus

# configure module logger
logger = logging.getLogger("client_service.frontend_router")
logger.addHandler(logging.NullHandler())

frontend_router = APIRouter()
client_manager = ClientManager()


class AddGroupPayload(BaseModel):
    num_clients: int
    time_limit: int = 5  # Default 5 minutes



@frontend_router.post("/client-group/{benchmark_id}", status_code=status.HTTP_201_CREATED)
async def add_client_group(benchmark_id: int, payload: AddGroupPayload):
    """
    Create a client group for a benchmark. Expects JSON { "num_clients": <int>, "time_limit": <int> }.
    """
    logger.debug(f"Received request to create client group {benchmark_id} expecting {payload.num_clients} with time_limit {payload.time_limit}")
    res = client_manager.add_client_group(benchmark_id, payload.num_clients, payload.time_limit)
    if res != ClientManagerResponseStatus.OK:
        logger.debug(f"Failed to create client group {benchmark_id} (already exists)")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group already exists")
    logger.info(f"Created client group {benchmark_id} expecting {payload.num_clients}")
    return {"status": "created", "benchmark_id": benchmark_id, "num_clients": payload.num_clients}


@frontend_router.delete("/client-group/{benchmark_id}", status_code=status.HTTP_200_OK)
async def delete_client_group(benchmark_id: int):
    """
    Remove a client group.
    """
    logger.debug(f"Received request to delete client group {benchmark_id}")
    client_manager.remove_client_group(benchmark_id)
    logger.info(f"Deleted client group {benchmark_id}")
    return {"status": "deleted", "benchmark_id": benchmark_id}



@frontend_router.post("/client-group/{benchmark_id}/run", status_code=status.HTTP_200_OK)
async def run_client_group(benchmark_id: int):
    """
    Trigger the registered client process to spawn (up to) payload.num_clients internal clients.
    For groups where a single process manages all internal clients, this proxies the /run request.
    """
    logger.debug(f"Run request for benchmark {benchmark_id}")
    try:
        results = client_manager.run_client_group(benchmark_id)
    except ValueError as e:
        logger.warning(f"Run failed for unknown benchmark {benchmark_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error while running client group")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    logger.info(f"Dispatched run to benchmark {benchmark_id}: results={results}")
    return {"status": "dispatched", "benchmark_id": benchmark_id, "results": results}


@frontend_router.get("/client-group/{benchmark_id}", status_code=status.HTTP_200_OK)
async def get_client_group_info(benchmark_id: int):
    """
    Return information about a client group (num_clients, registered client process).
    """
    info = client_manager.get_group_info(benchmark_id)
    if info is None:
        logger.debug(f"Info requested for unknown benchmark {benchmark_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark id not found")
    return {"benchmark_id": benchmark_id, "info": info}