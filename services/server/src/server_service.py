"""
Core logic for the server service.
Thin client that delegates orchestration to the remote Orchestrator.
"""

from typing import Dict, List, Optional, Any
import logging

class ServerService:
    """Main server service class - thin client for remote orchestration."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Initializing ServerService (thin client mode)")
        
        # Orchestrator proxy (required for all operations)
        self.orchestrator_proxy = None
    
    def set_orchestrator_proxy(self, proxy):
        """Set the orchestrator proxy instance."""
        self.orchestrator_proxy = proxy
        self.logger.info("Orchestrator proxy set in ServerService")
    
    
    def start_service(self, recipe_name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start a new service via the orchestrator.
        
        Args:
            recipe_name: Name of the recipe template to use
            config: Optional configuration overrides
            
        Returns:
            Service information dict
        """
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        response = self.orchestrator_proxy.start_service(recipe_name, config or {})
        
        # Unwrap service_data if present (orchestrator returns {status, job_id, service_data})
        if "service_data" in response:
            return response["service_data"]
        return response
    
    def stop_service(self, service_id: str) -> bool:
        """Stop a running service via the orchestrator.
        
        Args:
            service_id: The service or group ID to stop
            
        Returns:
            True if successful
        """
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.stop_service(service_id)
        
    def list_available_recipes(self) -> List[Dict[str, Any]]:
        """List all available service recipes via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.list_recipes()
        
    def list_running_services(self) -> List[Dict[str, Any]]:
        """List currently running services via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.list_services()

    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific service or service group via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.get_service(service_id)

    def get_service_logs(self, service_id: str) -> Dict[str, str]:
        """Get SLURM logs from a service via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.get_service_logs(service_id)
    
    def get_service_status(self, service_id: str) -> Dict[str, str]:
        """Get current status of a service or service group via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.get_service_status(service_id)
    
    # ===== Service Group Operations =====
    
    def list_service_groups(self) -> List[Dict[str, Any]]:
        """List all service groups via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.list_service_groups()
    
    def get_service_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific service group via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.get_service_group(group_id)
    
    def get_service_group_status(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get aggregated status of a service group via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.get_service_group_status(group_id)
    
    def stop_service_group(self, group_id: str) -> Dict[str, Any]:
        """Stop all replicas in a service group via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.stop_service_group(group_id)

    # ===== Data Plane Operations (vLLM) =====

    def find_vllm_services(self) -> List[Dict[str, Any]]:
        """Find running vLLM services via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.find_vllm_services()
    
    def get_vllm_models(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Query a running vLLM service for available models via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.get_vllm_models(service_id, timeout)
    
    def get_vllm_metrics(self, service_id: str, timeout: int = 10) -> Dict[str, Any]:
        """Get Prometheus metrics from a vLLM service via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.get_vllm_metrics(service_id, timeout)
    
    def prompt_vllm_service(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a running vLLM service via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.prompt_vllm_service(service_id, prompt, **kwargs)

    # ===== Data Plane Operations (Vector DB) =====
    
    def find_vector_db_services(self) -> List[Dict[str, Any]]:
        """Find running vector database services via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.find_vector_db_services()
    
    def get_collections(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Get list of collections from a vector database service via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.get_collections(service_id, timeout)
    
    def get_collection_info(self, service_id: str, collection_name: str, timeout: int = 5) -> Dict[str, Any]:
        """Get detailed information about a specific collection via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.get_collection_info(service_id, collection_name, timeout)
    
    def create_collection(self, service_id: str, collection_name: str, vector_size: int, 
                         distance: str = "Cosine", timeout: int = 10) -> Dict[str, Any]:
        """Create a new collection in the vector database via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.create_collection(service_id, collection_name, vector_size, distance, timeout)
    
    def delete_collection(self, service_id: str, collection_name: str, timeout: int = 10) -> Dict[str, Any]:
        """Delete a collection from the vector database via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.delete_collection(service_id, collection_name, timeout)
    
    def upsert_points(self, service_id: str, collection_name: str, points: List[Dict[str, Any]], 
                     timeout: int = 30) -> Dict[str, Any]:
        """Insert or update points in a collection via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.upsert_points(service_id, collection_name, points, timeout)
    
    def search_points(self, service_id: str, collection_name: str, query_vector: List[float], 
                     limit: int = 10, timeout: int = 10) -> Dict[str, Any]:
        """Search for similar vectors in a collection via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.search_points(service_id, collection_name, query_vector, limit, timeout)
    
    def get_qdrant_metrics(self, service_id: str, timeout: int = 10) -> Dict[str, Any]:
        """Get Prometheus metrics from a Qdrant service via orchestrator."""
        if not self.orchestrator_proxy:
            raise RuntimeError("Orchestrator manager not initialized")
        
        return self.orchestrator_proxy.get_qdrant_metrics(service_id, timeout)
