"""Base service class for service-specific handlers."""

from typing import Callable, List, Dict, Any


class BaseService:
    """Base class for all service-specific handlers."""

    def __init__(self, deployer, service_manager, endpoint_resolver, logger):
        """Initialize the base service.

        Args:
            deployer: The deployer instance for managing service deployments
            service_manager: The service manager instance
            endpoint_resolver: The endpoint resolver instance
            logger: The logger instance
        """
        self.deployer = deployer
        self.service_manager = service_manager
        self.endpoint_resolver = endpoint_resolver
        self.logger = logger

    def _filter_services(self, predicate: Callable[[Dict[str, Any]], bool]) -> List[Dict[str, Any]]:
        """Filter running services based on a predicate function.

        Args:
            predicate: A function that takes a service dict and returns True if it matches

        Returns:
            List of service dictionaries that match the predicate
        """
        try:
            # Get all services from the service manager
            services = self.service_manager.list_services()
            self.logger.debug(f"Filtering from {len(services)} total services")
            
            # Filter and update status from SLURM for each service
            filtered = []
            for svc in services:
                if predicate(svc):
                    # Get current status from SLURM
                    service_id = svc.get("id")
                    try:
                        status = self.deployer.get_job_status(service_id)
                        svc = svc.copy()
                        svc["status"] = status
                    except Exception as e:
                        self.logger.warning(f"Failed to get status for service {service_id}: {e}")
                    filtered.append(svc)
            
            self.logger.debug(f"Filtered to {len(filtered)} matching services")
            return filtered
        except Exception as e:
            self.logger.error(f"Error filtering services: {e}")
            return []

    def find_services(self) -> List[Dict[str, Any]]:
        """Find services of this specific type.

        This method should be implemented by subclasses.

        Returns:
            List of service dictionaries matching this service type
        """
        raise NotImplementedError("Subclasses must implement find_services()")
