import logging 
import threading
from typing import List
import time

import requests

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

        BASE_URL = "http://mel0398:8001"


        payload = {
            "recipe_name": "inference/vllm",
            "config": {"nodes": 1, "cpus": 2, "memory": "8G"}
        }
        resp = requests.post(f"{BASE_URL}/api/v1/services", json=payload)
        print(resp.json())

        # response = requests.get(f"{BASE_URL}/api/v1/services")
        # if ( response.status_code != 200 ):
        #     services = response.json()
        #     logging.debug(f"Client {self.client_id} failed to get services: {response.status_code}")
        #     logging.debug(f"Client {self.client_id} got services: {services}")
        #     return
        # else:
        #     services = response.json()
        #     logging.debug(f"Client {self.client_id} got services: {services}")
        
        # resp = requests.get(f"{BASE_URL}/api/v1/vllm/services")
        # print(resp.json())
        service_id = "3639826"
        payload = {
            "prompt": "How many r has the word 'apple'?",
            "max_tokens": 500,
            "temperature": 0.7
        }
        resp = requests.post(f"{BASE_URL}/api/v1/vllm/{service_id}/prompt", json=payload)
        print(resp.json())

        for observer in self._observers:
            observer.update({})

    def subscribe(self, observer: ClientObserver):
        self._observers.append(observer)
