import logging 
import threading
from typing import List, Optional
import time

import requests

from client.client_observer import ClientObserver
logging.basicConfig(level=logging.DEBUG)

class VLLMClient:
    num_clients : int = 0
    _service_id: Optional[str] = None  # Static variable for service ID
    _server_base_url: Optional[str] = None  # Static variable for server URL
    
    def __init__(self, recipe: str = "inference/vllm"):
        # Private attributes
        self._observers : List[ClientObserver] = []
        self._recipe = recipe

        # Public attributes
        self.client_id = VLLMClient.num_clients
        self.thread : threading.Thread

        VLLMClient.num_clients += 1

    @staticmethod
    def setup_benchmark(server_base_url: str) -> Optional[str]:
        """
        Setup benchmark by creating a vLLM service and returning the service ID.
        This should be called once before starting all clients.
        
        Args:
            server_base_url: Base URL of the server (e.g., "http://server:8000")
            
        Returns:
            service_id if successful, None if failed
        """
        VLLMClient._server_base_url = server_base_url
        
        payload = {
            "recipe_name": "inference/vllm",
            "config": {"nodes": 1, "cpus": 2, "memory": "8G"}
        }
        
        try:
            resp = requests.post(f"{server_base_url}/api/v1/services", json=payload)
            if resp.status_code == 200:
                service_data = resp.json()
                service_id = service_data.get("id")
                VLLMClient._service_id = str(service_id) if service_id else None
                logging.info(f"vLLM service created with ID: {VLLMClient._service_id}")
                return VLLMClient._service_id
            else:
                logging.error(f"Failed to create vLLM service: {resp.status_code} - {resp.text}")
                return None
        except Exception as e:
            logging.error(f"Error creating vLLM service: {e}")
            return None

    def run(self):
        """Run the vLLM client - makes requests to the vLLM service"""
        logging.debug(f"VLLMClient {self.client_id} is running.")

        # Check if service is set up
        if not VLLMClient._service_id or not VLLMClient._server_base_url:
            logging.error(f"VLLMClient {self.client_id}: Service not set up. Call setup_benchmark() first.")
            return

        # Make a prompt request to the vLLM service
        payload = {
            "prompt": "How many r has the word 'apple'?",
            "max_tokens": 500,
            "temperature": 0.7
        }
        
        try:
            resp = requests.post(
                f"{VLLMClient._server_base_url}/api/v1/vllm/{VLLMClient._service_id}/prompt", 
                json=payload
            )
            if resp.status_code == 200:
                result = resp.json()
                logging.info(f"VLLMClient {self.client_id}: Prompt response received")
                logging.debug(f"VLLMClient {self.client_id}: Response: {result}")
            else:
                logging.error(f"VLLMClient {self.client_id}: Prompt request failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logging.error(f"VLLMClient {self.client_id}: Error making prompt request: {e}")

        # Notify observers
        for observer in self._observers:
            observer.update({})

    def subscribe(self, observer: ClientObserver):
        self._observers.append(observer)
