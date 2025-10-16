from fastapi import FastAPI, APIRouter, HTTPException, status
from pydantic import BaseModel
from client_service.client_manager.client_manager import ClientManager, ClientManagerResponseStatus

from typing import List

monitor_router  = APIRouter()
client_manager = ClientManager()


class ObserverPayload(BaseModel):
    ip_address: str
    port: int





@monitor_router.post("/client-group/{benchmark_id}/observer", status_code=status.HTTP_201_CREATED)
async def add_observer(benchmark_id: int, payload: ObserverPayload):
    """Register a monitor/observer for a client group. Expects JSON {"ip_address": "x.x.x.x", "port": 9000}."""
    # Find the registered client process for this benchmark
    with client_manager._lock:
        group = client_manager._client_groups.get(benchmark_id)
        if group is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark id not found")
        client_addr = group.get_client_address()

    if client_addr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No client process registered for this benchmark")

    # Forward the observer registration to the client group's REST API
    import requests
    url = f"{client_addr.rstrip('/')}/observer"
    json_payload = {"ip_address": payload.ip_address, "port": payload.port, "update_preferences": {}}
    try:
        r = requests.post(url, json=json_payload, timeout=5.0)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to contact client process: {e}")

    if r.status_code not in (200, 201):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Client process returned {r.status_code}: {r.text}")

    # Observer registration forwarded successfully to client process
    return {"status": "registered", "benchmark_id": benchmark_id, "observer": f"{payload.ip_address}:{payload.port}"}