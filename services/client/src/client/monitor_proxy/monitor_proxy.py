from update_preferences import UpdatePreferences
class MonitorProxy:
    def __init__(self, ip_addr: str, port: str, preferences: UpdatePreferences):
        self._ip_addr = ip_addr 
        self._port = port
        self._preferences = preferences
    pass