from typing import Iterable
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from client_manager.client_manager import ClientManager

class ClientGroupCollector:
    """
    Prometheus collector that generates metrics for client groups on demand.
    """
    def __init__(self, client_manager: ClientManager):
        self.client_manager = client_manager

    def collect(self) -> Iterable[GaugeMetricFamily]:
        """
        Collect metrics for all client groups.
        This is called by Prometheus client on every scrape.
        """
        # Metric to track the status of client groups
        # Labels: group_id
        # Value: Status code (0=Pending, 1=Starting, 2=Running, 3=Completed, 4=Failed, 5=Cancelled)
        status_gauge = GaugeMetricFamily(
            "client_group_status_info",
            "Current status of the client group",
            labels=["group_id"]
        )

        # Iterate over all groups and get their status
        # Note: This might be slow if there are many groups as it queries SLURM via SSH
        # We might need to optimize this later (e.g. bulk query or caching)
        groups = self.client_manager.get_all_groups()
        
        for group in groups:
            try:
                group_id = str(group.get_group_id())
                status_code = group.get_status_code()
                status_gauge.add_metric([group_id], status_code)
            except Exception as e:
                # Log error but continue with other groups
                # We can't easily log here without importing logging, but we should avoid crashing the scrape
                pass
                
        yield status_gauge
