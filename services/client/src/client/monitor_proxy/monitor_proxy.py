from .update_preferences import UpdatePreferences
from ..client_observer import ClientObserver

class MonitorProxy(ClientObserver):
    def __init__(self, ip_addr: str, port: str, preferences: UpdatePreferences):
        self._ip_addr = ip_addr 
        self._port = port
        self._preferences = preferences

    def update(self, data: dict):
        """Handle client updates and forward to monitor"""
        # TODO: Send data to monitor at self._ip_addr:self._port
        pass