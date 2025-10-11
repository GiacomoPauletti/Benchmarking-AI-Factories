from fastapi import FastAPI, APIRouter, HTTPException, status
from pydantic import BaseModel
from client_service.client_manager.client_manager import ClientManager, ClientManagerResponseStatus

monitor_router  = APIRouter()

client_manager = ClientManager()

@monitor_router.get("/client-group-ip/{benchmark_id}")
async def get_client_group_ip(benchmark_id : int) -> list[int]:
    response = client_manager.get_client_group_ip(benchmark_id)
    if response.status != ClientManagerResponseStatus.OK:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    else:
        return response.body
    