from fastapi import FastAPI, APIRouter, HTTPException, status
from pydantic import BaseModel
from monitor_proxy.monitor_proxy import MonitorProxy
from monitor_proxy.update_preferences import UpdatePreferences

monitor_proxy_router  = APIRouter()

observer_counter = 0

@monitor_proxy_router.post("/observer")
async def add_observer(ip_address : str, port: str, update_preferences: UpdatePreferences ) -> int:
    MonitorProxy(ip_address, port, update_preferences)
    return 0