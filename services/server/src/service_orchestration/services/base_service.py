"""Base service class for service-specific handlers."""

from abc import ABC, abstractmethod
from typing import Callable, List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
import requests


class BaseService(ABC):
    """Base class for all service-specific handlers.
    
    Provides common functionality for:
    - HTTP request handling with endpoint resolution
    - Standardized response formatting
    - Service filtering and discovery
    - Readiness checking with SLURM status integration
    """

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

    # ========== Abstract Properties ==========
    
    @property
    @abstractmethod
    def default_port(self) -> int:
        """Default port for this service type."""
        pass

    @property
    @abstractmethod
    def service_type_name(self) -> str:
        """Human-readable name for this service type (e.g., 'vLLM', 'Qdrant')."""
        pass

    # ========== Response Helpers ==========

    def _success_response(self, **kwargs) -> Dict[str, Any]:
        """Create a standardized success response.
        
        Args:
            **kwargs: Additional fields to include in the response
            
        Returns:
            Dict with success=True and all provided fields
        """
        return {"success": True, **kwargs}

    def _error_response(self, error: str, message: str, **kwargs) -> Dict[str, Any]:
        """Create a standardized error response.
        
        Args:
            error: Short error description (for programmatic use)
            message: Human-readable error message
            **kwargs: Additional fields to include in the response
            
        Returns:
            Dict with success=False, error, message, and all provided fields
        """
        return {"success": False, "error": error, "message": message, **kwargs}

    # ========== HTTP Request Helpers ==========

    def _resolve_endpoint_parts(self, service_id: str) -> Optional[Tuple[str, int]]:
        """Resolve service endpoint and return host/port tuple.
        
        Args:
            service_id: The service ID to resolve
            
        Returns:
            Tuple of (hostname, port) or None if not resolvable
        """
        endpoint = self.endpoint_resolver.resolve(service_id, default_port=self.default_port)
        if not endpoint:
            return None
        
        parsed = urlparse(endpoint)
        hostname = parsed.hostname
        port = parsed.port or self.default_port
        return (hostname, port)

    def _make_request(
        self,
        service_id: str,
        path: str,
        method: str = "GET",
        json_data: Optional[Dict[str, Any]] = None,
        timeout: int = 10,
        expected_status: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request to a service with standard error handling.
        
        Handles endpoint resolution, request execution, and error formatting.
        
        Args:
            service_id: The service ID to send the request to
            path: The API path (e.g., "/collections", "/v1/models")
            method: HTTP method (GET, POST, PUT, DELETE)
            json_data: Optional JSON body for the request
            timeout: Request timeout in seconds
            expected_status: List of acceptable status codes (default: [200, 201, 204])
            
        Returns:
            Dict with either:
            - {"success": True, "data": response_json, "status_code": int, "endpoint": str}
            - {"success": False, "error": str, "message": str, ...}
        """
        if expected_status is None:
            expected_status = [200, 201, 204]
        
        # Resolve endpoint
        endpoint_parts = self._resolve_endpoint_parts(service_id)
        if not endpoint_parts:
            return self._error_response(
                error="Service endpoint not available",
                message=f"The {self.service_type_name} service endpoint is not available yet.",
                service_id=service_id
            )
        
        hostname, port = endpoint_parts
        url = f"http://{hostname}:{port}{path}"
        endpoint_str = f"http://{hostname}:{port}"
        
        self.logger.debug(f"{method} {url} (timeout={timeout}s)")
        
        try:
            response = requests.request(
                method=method,
                url=url,
                json=json_data,
                timeout=timeout
            )
            
            if response.status_code not in expected_status:
                return self._error_response(
                    error=f"HTTP {response.status_code} from {path}",
                    message=f"Request to {self.service_type_name} service failed (HTTP {response.status_code}).",
                    service_id=service_id,
                    endpoint=endpoint_str,
                    status_code=response.status_code
                )
            
            # Parse JSON response if available
            try:
                data = response.json() if response.text else {}
            except ValueError:
                data = {"raw_text": response.text}
            
            return self._success_response(
                data=data,
                status_code=response.status_code,
                endpoint=endpoint_str,
                service_id=service_id
            )
            
        except requests.exceptions.Timeout:
            return self._error_response(
                error=f"Request timeout after {timeout}s",
                message=f"The {self.service_type_name} service did not respond in time.",
                service_id=service_id,
                endpoint=endpoint_str,
                timeout=timeout
            )
        except requests.exceptions.ConnectionError as e:
            return self._error_response(
                error="Connection failed",
                message=f"Cannot connect to {self.service_type_name} service. It may still be starting up.",
                service_id=service_id,
                endpoint=endpoint_str,
                technical_details=str(e)
            )
        except Exception as e:
            self.logger.exception(f"Request to {url} failed")
            return self._error_response(
                error=f"Request failed: {str(e)}",
                message=f"An error occurred while communicating with the {self.service_type_name} service.",
                service_id=service_id,
                endpoint=endpoint_str
            )

    # ========== Service Validation Helpers ==========

    def _validate_service_exists(self, service_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Check if a service exists in the service manager.
        
        Args:
            service_id: The service ID to check
            
        Returns:
            Tuple of (exists: bool, service_info: Optional[Dict], error_response: Optional[Dict])
            - If exists: (True, service_info, None)
            - If not exists: (False, None, error_response_dict)
        """
        service_info = self.service_manager.get_service(service_id)
        if not service_info:
            return (False, None, self._error_response(
                error=f"Service {service_id} not found",
                message=f"The requested {self.service_type_name} service could not be found.",
                service_id=service_id
            ))
        return (True, service_info, None)

    def _check_service_ready_http(
        self,
        service_id: str,
        health_path: str,
        timeout: int = 8
    ) -> Tuple[bool, str]:
        """Check if a service is ready using SLURM status + HTTP health probe.
        
        Common pattern used by both inference and vector DB services:
        1. Check SLURM status first (fast filter for pending/building jobs)
        2. For RUNNING jobs, test HTTP connection to health endpoint
        
        Args:
            service_id: The service ID to check
            health_path: The health check endpoint path (e.g., "/collections", "/v1/models")
            timeout: HTTP request timeout in seconds
            
        Returns:
            Tuple of (is_ready: bool, status: str)
        """
        # For composite replica IDs (e.g., "3713478:8001"), skip SLURM check
        if ":" in service_id:
            self.logger.debug(f"Checking replica {service_id} via direct HTTP test")
            basic_status = "running"
        else:
            # Get SLURM status
            try:
                basic_status = self.deployer.get_job_status(service_id).lower()
            except Exception as e:
                self.logger.warning(f"Failed to get status for service {service_id}: {e}")
                basic_status = "unknown"
        
        # If not running yet, return basic status
        if basic_status != "running":
            is_ready = basic_status not in ["pending", "building", "starting", "unknown"]
            return is_ready, basic_status
        
        # For RUNNING jobs, test HTTP connection
        endpoint_parts = self._resolve_endpoint_parts(service_id)
        if not endpoint_parts:
            self.logger.debug(f"Service {service_id} is RUNNING but endpoint not resolved yet")
            return False, "starting"
        
        hostname, port = endpoint_parts
        
        try:
            response = requests.get(
                f"http://{hostname}:{port}{health_path}",
                timeout=timeout
            )
            
            if response.ok:
                self.logger.debug(f"Service {service_id} is ready (HTTP {response.status_code})")
                return True, "running"
            else:
                self.logger.debug(f"Service {service_id} returned HTTP {response.status_code}")
                return False, "starting"
                
        except Exception as e:
            self.logger.debug(f"Service {service_id} health check failed: {e}")
            return False, "starting"

    # ========== Service Discovery ==========

    def _filter_services(self, predicate: Callable[[Dict[str, Any]], bool]) -> List[Dict[str, Any]]:
        """Filter running services based on a predicate function.

        Args:
            predicate: A function that takes a service dict and returns True if it matches

        Returns:
            List of service dictionaries that match the predicate
        """
        try:
            services = self.service_manager.list_services()
            self.logger.debug(f"Filtering from {len(services)} total services")
            
            filtered = []
            for svc in services:
                if predicate(svc):
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

    @abstractmethod
    def find_services(self) -> List[Dict[str, Any]]:
        """Find services of this specific type.

        Returns:
            List of service dictionaries matching this service type
        """
        pass

    @abstractmethod
    def _check_service_ready(self, service_id: str, service_info: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if a service is ready to accept requests.
        
        Args:
            service_id: The service ID to check
            service_info: The service information dict
            
        Returns:
            Tuple of (is_ready: bool, status: str)
        """
        pass
