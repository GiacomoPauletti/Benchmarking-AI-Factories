"""
Core logic for the server service.
Orchestrates AI workloads using SLURM + Apptainer.
"""

from pathlib import Path
import requests
from typing import Dict, List, Optional, Any
import logging

from slurm import SlurmDeployer
from service_manager import ServiceManager
from utils.recipe_loader import RecipeLoader
from utils.endpoint_resolver import EndpointResolver

class ServerService:
    """Main server service class with SLURM-based orchestration."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Initializing ServerService")
        self.deployer = SlurmDeployer()
        self.recipes_dir = Path(__file__).parent / "recipes"
        self.service_manager = ServiceManager()
        
        # Initialize helper utilities
        self.recipe_loader = RecipeLoader(self.recipes_dir)
        self.endpoint_resolver = EndpointResolver(self.deployer, self.service_manager, self.recipe_loader)
        
        # Lazy-loaded service handlers (instantiated on first access)
        self._vllm_service = None
        self._vector_db_service = None
    
    @property
    def vllm_service(self):
        """Lazy-load VLLM service handler."""
        if self._vllm_service is None:
            from services.vllm_service import VllmService
            self._vllm_service = VllmService(
                self.deployer, 
                self.service_manager, 
                self.endpoint_resolver, 
                self.logger
            )
        return self._vllm_service
    
    @property
    def vector_db_service(self):
        """Lazy-load vector database service handler."""
        if self._vector_db_service is None:
            from services.vector_db_service import VectorDbService
            self._vector_db_service = VectorDbService(
                self.deployer,
                self.service_manager,
                self.endpoint_resolver,
                self.logger
            )
        return self._vector_db_service

    def start_service(self, recipe_name: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Start a service based on recipe using SLURM + Apptainer."""
        try:
            # Use config as-is, with default nodes=1 if not specified
            full_config = config or {}
            if "nodes" not in full_config:
                full_config["nodes"] = 1
            
            # Submit to SLURM
            job_info = self.deployer.submit_job(recipe_name, full_config)
            self.logger.info("Submitted job %s for recipe %s", job_info.get("job_id", job_info.get("id")), recipe_name)
            
            # Store complete service information
            service_data = {
                "id": job_info["id"],  # SLURM job ID is used directly as service ID
                "name": job_info["name"],
                "recipe_name": recipe_name,
                "status": job_info["status"],
                "config": full_config,
                "created_at": job_info["created_at"]
            }
            self.service_manager.register_service(service_data)
            # self.logger.info("Registered service %s", service_data["id"])
            
            return service_data
            
        except Exception as e:
            self.logger.exception("Failed to start service %s: %s", recipe_name, e)
            raise RuntimeError(f"Failed to start service: {str(e)}")
        
    def stop_service(self, service_id: str) -> bool:
        """Stop running service by cancelling SLURM job."""
        return self.deployer.cancel_job(service_id)
        
    def list_available_recipes(self) -> List[Dict[str, Any]]:
        """List all available service recipes."""
        return self.recipe_loader.list_all()
        
    def list_running_services(self) -> List[Dict[str, Any]]:
        """List currently running services (only services started by this server)."""
        # Get all services registered in the service manager
        registered_services = self.service_manager.list_services()
        
        # Update each service with current status from SLURM
        services_with_status = []
        for stored_service in registered_services:
            service_id = stored_service["id"]
            
            # Get current status from SLURM
            try:
                status = self.deployer.get_job_status(service_id)
            except Exception as e:
                self.logger.warning(f"Failed to get status for service {service_id}: {e}")
                status = "unknown"
            
            # Use our stored information and update with current detailed status
            service_data = stored_service.copy()
            service_data["status"] = status
            
            # Update status in manager if it changed
            if service_data["status"] != stored_service.get("status"):
                self.service_manager.update_service_status(service_id, status)
            
            services_with_status.append(service_data)
        
        return services_with_status
    
    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific service."""
        # First check if we have stored information
        stored_service = self.service_manager.get_service(service_id)
        if stored_service:
            # Update with current detailed status from SLURM (detailed=True by default)
            current_status = self.deployer.get_job_status(service_id)
            if current_status != stored_service.get("status"):
                self.service_manager.update_service_status(service_id, current_status)
                stored_service = stored_service.copy()
                stored_service["status"] = current_status
            return stored_service
        return None
    
    def get_service_logs(self, service_id: str) -> str:
        """Get slurm logs from a service."""
        self.logger.debug("Fetching logs for service %s", service_id)
        return self.deployer.get_job_logs(service_id)
    
    def get_service_status(self, service_id: str) -> str:
        """Get current detailed status of a service."""
        return self.deployer.get_job_status(service_id)

    def find_vllm_services(self) -> List[Dict[str, Any]]:
        """Find running VLLM services and their endpoints."""
        return self.vllm_service.find_services()
    
    def find_vector_db_services(self) -> List[Dict[str, Any]]:
        """Find running vector database services and their endpoints."""
        return self.vector_db_service.find_services()
    
    
    def get_vllm_models(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Query a running VLLM service for available models.
        
        Returns a dict with either:
        - {"success": True, "models": [list of model ids]}
        - {"success": False, "error": "...", "message": "...", "models": []}
        """
        return self.vllm_service.get_models(service_id, timeout)
    
    def prompt_vllm_service(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a running VLLM service."""
        return self.vllm_service.prompt(service_id, prompt, **kwargs)
