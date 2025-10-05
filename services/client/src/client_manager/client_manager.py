from client_group import ClientGroup
from typing import Optional, TypeVar, Generic
from enum import Enum, auto

class ClientManagerResponseStatus(Enum):
    OK              = auto()
    NOT_FOUND       = auto()
    ALREADY_PRESENT = auto()

T = TypeVar("T")
class ClientManagerResponse(Generic[T]):
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
    def __init__(self):
        self._client_groups : dict[int, ClientGroup]
        pass

    def get_client_group_ip(self, benchmark_id: int) -> ClientManagerResponse[list[int]]:
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
        if benchmark_id in self._client_groups.keys():
            return ClientManagerResponseStatus.ALREADY_PRESENT
        else:
            self._client_groups[benchmark_id] = ClientGroup(num_clients)
            return ClientManagerResponseStatus.OK
        
    def remove_client_group(self, benchmark_id : int) -> ClientManagerResponseStatus:
        self._client_groups.pop(benchmark_id)
        return ClientManagerResponseStatus.OK
