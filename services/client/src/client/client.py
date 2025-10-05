from services.client.src.client.server_proxy.server_proxy import ServerProxy
from client_observer import ClientObserver

class Client:
    def __init__(self, server_proxy: ServerProxy, recipe: str):
        self._observers : list[ClientObserver]
        pass

    def run(self):
        # Do something here

        for observer in self._observers:
            observer.update({})

    def subscribe(self, observer: ClientObserver):
        self._observers.append(observer)
