"""Abstract base class for inference services (vLLM, TGI, etc.)."""

from abc import abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from service_orchestration.services.base_service import BaseService


class InferenceService(BaseService):
    """Abstract base class for all inference service implementations.
    
    This class defines the common interface that all inference services
    (vLLM, Text Generation Inference, etc.) must implement.
    
    Inherits from BaseService which provides:
    - HTTP request helpers (_make_request, _success_response, _error_response)
    - Service validation helpers (_validate_service_exists)
    - Readiness checking (_check_service_ready_http)
    """
    
    # Default health check path for inference services
    HEALTH_CHECK_PATH = "/v1/models"

    @abstractmethod
    def get_models(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Query a running inference service for available models.
        
        Args:
            service_id: The service ID to query
            timeout: Request timeout in seconds
            
        Returns:
            Dict with either:
            - {"success": True, "models": [list of model ids]}
            - {"success": False, "error": "...", "message": "..."}
        """
        pass

    @abstractmethod
    def prompt(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a running inference service.
        
        Args:
            service_id: The service ID to send the prompt to
            prompt: The prompt text
            **kwargs: Additional parameters (model, temperature, max_tokens, etc.)
            
        Returns:
            Dict with either:
            - {"success": True, "response": "...", ...}
            - {"success": False, "error": "...", "message": "..."}
        """
        pass

    def _check_service_ready(self, service_id: str, service_info: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if an inference service is ready using base class HTTP health check.
        
        Subclasses can override this for custom readiness checks.
        """
        return self._check_service_ready_http(service_id, self.HEALTH_CHECK_PATH)
