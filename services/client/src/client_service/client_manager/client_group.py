from .client_dispatcher import AbstractClientDispatcher



class ClientGroup:
    def __init__(self, num_clients: int, dispatcher: AbstractClientDispatcher): 
        self._group_ip    : int
        self._group_port  : int
        self._num_clients = num_clients

        # Here starts a slurm job
        dispatcher.dispatch(num_clients)
        

    def get_group_ip(self) -> int:
        return self._group_ip

    def get_group_port(self) -> int:
        return self._group_port