import logging 
import threading
from typing import List

from client.server_proxy.server_proxy import ServerProxy
from client.client_observer import ClientObserver
logging.basicConfig(level=logging.DEBUG)

class Client:
    num_clients : int = 0
    def __init__(self, server_proxy: ServerProxy, recipe: str):
        # Private attributes
        self._observers : List[ClientObserver] = []
        self._server_proxy = server_proxy
        self._recipe = recipe

        # Public attributes
        self.client_id = Client.num_clients
        self.thread : threading.Thread

        Client.num_clients += 1
        pass

    def run(self):
        # Do something here
        logging.debug(f"Client {self.client_id} is running.")

        for observer in self._observers:
            observer.update({})

    def subscribe(self, observer: ClientObserver):
        self._observers.append(observer)
