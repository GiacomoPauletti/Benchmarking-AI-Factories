from fastapi import APIRouter, status
from pydantic import BaseModel
import logging
from typing import List
from client.monitor_proxy.monitor_proxy import MonitorProxy
from client.monitor_proxy.update_preferences import UpdatePreferences

from ..client_group import ClientGroup

logger = logging.getLogger(__name__)

monitor_proxy_router = APIRouter()


class ObserverPayload(BaseModel):
    ip_address: str
    port: str
    update_preferences: dict = {}


class ObserverResponse(BaseModel):
    status: str


@monitor_proxy_router.post("/observer", status_code=status.HTTP_200_OK, response_model=ObserverResponse)
async def add_observer(payload: ObserverPayload):
    """Handle observer registration from monitor_router"""
    client_group = ClientGroup()
    
    if not client_group.clients:
        logger.error("No clients available for observer registration")
        return ObserverResponse(status="error")
    
    try:
        # Convert dict to UpdatePreferences
        prefs = UpdatePreferences()
        observer = MonitorProxy(payload.ip_address, payload.port, prefs)
        
        # Use ClientGroup's register_observer method
        success = client_group.register_observer(observer)
        
        if success:
            logger.info(f"Added observer {payload.ip_address}:{payload.port} to {client_group.num_clients} clients")
            return ObserverResponse(status="observer_added")
        else:
            return ObserverResponse(status="error")
        
    except Exception as e:
        logger.error(f"Failed to add observer: {e}")
        return ObserverResponse(status="error")


def set_clients(client_list: List):
    """Update the clients list in the ClientGroup singleton"""
    client_group = ClientGroup()
    # If ClientGroup is already configured, just update the clients
    if client_group.benchmark_id is not None:
        client_group._clients = client_list
    else:
        # If not configured yet, just add the clients for now
        client_group._clients = client_list
    logger.info(f"Monitor router configured with {len(client_list)} clients")