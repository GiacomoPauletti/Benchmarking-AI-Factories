from fastapi import FastAPI, APIRouter, HTTPException, status
from pydantic import BaseModel
from client_manager.client_manager import ClientManager, ClientManagerResponseStatus

app = FastAPI()



frontend_router = APIRouter()

client_manager = ClientManager()

@frontend_router.post("/client-group/{benchmark_id}")
async def add_client_group(benchmark_id : int, num_clients: int):
    response = client_manager.add_client_group(benchmark_id, num_clients)
    if response != ClientManagerResponseStatus.OK:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)

@frontend_router.delete("/client-group/{benchmark_id}")
async def delete_client_group(benchmark_id : int):
    client_manager.remove_client_group(benchmark_id)
