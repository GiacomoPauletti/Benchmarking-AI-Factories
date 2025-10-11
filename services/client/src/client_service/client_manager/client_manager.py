from client_service.client_manager.client_group import ClientGroup
from typing import Optional, TypeVar, Generic, List
from enum import Enum, auto
from client_service.client_manager.client_dispatcher import SlurmClientDispatcher

import logging

logging.basicConfig(level=logging.DEBUG)

class ClientManagerResponseStatus(Enum):
    """
        Enumeration class whose values are the response status of ClientManager.
        The status says about the correctness of a method call on a ClientManager instance.

        For example, OK means everything was done correctly; NOT_FOUND has a negative meaning,
        something went wrong (NOT_FOUND meaning depends on the context)
    """

    OK              = auto()
    NOT_FOUND       = auto()
    ALREADY_PRESENT = auto()

T = TypeVar("T")
class ClientManagerResponse(Generic[T]):
    """ 
        Class representing the output of a generic method of ClientManager.
        It wraps the actual output attaching to it the ClientManagerResponseStatus.
        The status and the actual output (here called "value") are accessible both
        with the homonymous attribute or with get_* method
    """
    def __init__(self, 
                 response_status : ClientManagerResponseStatus,
                 response_body   : T):
        self.status = response_status
        self.body   = response_body

    def get_status(self) -> ClientManagerResponseStatus:
        return self.status
    def get_value(self) -> T:
        return self.body


class ClientManager:
    """
    Singleton class thatanages the many ClientGroup instances, which means it stores them, 
    it eventually removes them upon request, it returns their ip addres + port.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        print ("Creating ClientManager instance")
        if not cls._instance:
            cls._instance = super(ClientManager, cls).__new__(cls)
        return cls._instance
        

    def __init__(self):
        self._client_groups : dict[int, ClientGroup] = {}

    def get_client_group_ip(self, benchmark_id: int) -> ClientManagerResponse[List[int]]:
        """
            description: returns ip address and port of the ClientGroup identified by benchmark_id
            params:
             - benchmark_id (int): id which identifies the benchmark and hence this client group
            returns: 
             - ClientManagerResponse[list[int]]: a response status (ClientManagerResponseStatus) plus
                                                 a 2-element list containing the ip address (index=0)
                                                 and the port (index=1)
        """
        if not benchmark_id in self._client_groups.keys():
            return ClientManagerResponse(
                        ClientManagerResponseStatus.NOT_FOUND, 
                        [0,0]
                    )
        else:
           client_group = self._client_groups[benchmark_id]
           return ClientManagerResponse(
                        ClientManagerResponseStatus.OK, 
                        [ 
                            client_group.get_group_ip(), 
                            client_group.get_group_port()
                        ]
                  )

    def add_client_group(self, benchmark_id: int, num_clients : int) -> ClientManagerResponseStatus:
        """
            creates a ClientGroup with num_clients clients and assigning it the benchmark_id id
            params:
             - benchmark_id (int): id which identifies the benchmark and hence this client group
             - num_clients (int) : number of clients in the group to be formed
            returns: 
             - ClientManagerResponseStatus: OK if all went correctly, else ALREADY_PRESENT
        """
        if benchmark_id in self._client_groups.keys():
            logging.debug(f"Attempt to add already present client group for benchmark_id {benchmark_id}.")
            return ClientManagerResponseStatus.ALREADY_PRESENT
        else:

            logging.debug(f"Adding client group for benchmark_id {benchmark_id} with {num_clients} clients.")
            self._client_groups[benchmark_id] = ClientGroup(num_clients, SlurmClientDispatcher())
            logging.debug(f"Successfully added client group for benchmark_id {benchmark_id} with {num_clients} clients.")
            return ClientManagerResponseStatus.OK
        
    def remove_client_group(self, benchmark_id : int) -> ClientManagerResponseStatus:
        """
            removes a ClientGroup assigned to the benchmark_id id
            params:
             - benchmark_id (int): id which identifies the benchmark and hence this client group
            returns: 
             - ClientManagerResponseStatus: OK even if benchmark_id is not assigned to any ClientGroup
        """
        self._client_groups.pop(benchmark_id)
        return ClientManagerResponseStatus.OK
