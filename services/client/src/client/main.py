import sys
import logging
from typing import List
import threading

from client.client import Client
from client.server_proxy.server_proxy import ServerProxy

logging.basicConfig(level=logging.DEBUG)

server_proxy = ServerProxy()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        logging.fatal("Invalid number of arguments. At least one argument is required: number of clients to dispatch.")
        sys.exit(1)

    client_count = int(sys.argv[1])
    clients : List[Client]= []

    logging.debug(f"Starting {client_count} clients.")
    # Create and start clients
    for i in range(client_count):
        recipe = "default"

        # Create and start client
        client = Client(server_proxy, recipe)
        thread = threading.Thread(target=client.run)
        thread.start()

        # Store client and its thread
        clients.append(client)
        client.thread = thread
