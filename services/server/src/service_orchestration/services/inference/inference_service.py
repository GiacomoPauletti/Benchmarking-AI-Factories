"""Abstract base class for inference services (vLLM, TGI, etc.)."""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from service_orchestration.services.base_service import BaseService


class InferenceService(BaseService, ABC):
    """Abstract base class for all inference service implementations.
    
    This class defines the common interface that all inference services
    (vLLM, Text Generation Inference, etc.) must implement.
    """

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

    @abstractmethod
    def _check_ready_and_discover_model(self, service_id: str, service_info: Dict[str, Any]) -> tuple[bool, str, Any]:
        """Check if an inference service is ready AND discover its model name in one call.
        
        This method should implement service-specific readiness checks and model discovery
        to eliminate redundant HTTP calls.
        
        Args:
            service_id: The service ID to check
            service_info: The service information dict
            
        Returns:
            Tuple of (is_ready: bool, status: str, model: Optional[str])
        """
        pass
