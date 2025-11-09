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
        """Lazy-load vLLM service handler."""
        if self._vllm_service is None:
            from services.inference import VllmService
            self._vllm_service = VllmService(
                self.deployer, 
                self.service_manager, 
                self.endpoint_resolver, 
                self.logger
            )
        return self._vllm_service
    
    @property
    def vector_db_service(self):
        """Lazy-load Qdrant vector database service handler."""
        if self._vector_db_service is None:
            from services.vector_db import QdrantService
            self._vector_db_service = QdrantService(
                self.deployer,
                self.service_manager,
                self.endpoint_resolver,
                self.logger
            )
        return self._vector_db_service

    def start_service(self, recipe_name: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Start a service based on recipe using SLURM + Apptainer.
        
        If the recipe or config specifies replicas > 1, creates a service group
        with multiple independent SLURM jobs.
        """
        try:
            import yaml
            
            # Load recipe to check for replicas
            recipe_path = self.deployer._find_recipe(recipe_name)
            with open(recipe_path, 'r') as f:
                recipe = yaml.safe_load(f)
            
            # Use config as-is - let deployer merge with recipe defaults
            full_config = config or {}
            
            # Determine number of replicas (config overrides recipe)
            replicas = full_config.get('replicas', recipe.get('replicas', 1))
            
            # If replicas == 1, use standard single-service flow
            if replicas == 1:
                return self._start_single_service(recipe_name, full_config)
            
            # If replicas > 1, create a service group
            return self._start_service_group(recipe_name, full_config, replicas)
            
        except Exception as e:
            self.logger.exception("Failed to start service %s: %s", recipe_name, e)
            raise RuntimeError(f"Failed to start service: {str(e)}")
    
    def _start_single_service(self, recipe_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start a single service (no replicas)."""
        # Submit to SLURM
        job_info = self.deployer.submit_job(recipe_name, config)
        self.logger.info("Submitted job %s for recipe %s", job_info.get("job_id", job_info.get("id")), recipe_name)
        
        # Store complete service information
        service_data = {
            "id": job_info["id"],  # SLURM job ID is used directly as service ID
            "name": job_info["name"],
            "recipe_name": recipe_name,
            "status": job_info["status"],
            "config": config,
            "created_at": job_info["created_at"]
        }
        self.service_manager.register_service(service_data)
        
        return service_data
    
    def _start_service_group(self, recipe_name: str, config: Dict[str, Any], replicas: int) -> Dict[str, Any]:
        """Start a service group with multiple replicas."""
        self.logger.info(f"Creating service group with {replicas} replicas for recipe {recipe_name}")
        
        # Create service group
        group_id = self.service_manager.group_manager.create_group(
            recipe_name=recipe_name,
            num_replicas=replicas,
            config=config
        )
        
        # Port for all replicas (same port is fine since they're on different nodes)
        replica_port = config.get('port', 8001)
        
        # Submit SLURM jobs for each replica
        replica_jobs = []
        for i in range(replicas):
            # Create replica-specific config
            replica_config = config.copy()
            replica_config['replica_index'] = i
            replica_config['replica_port'] = replica_port
            
            # Remove replicas field from replica config to avoid recursion
            replica_config.pop('replicas', None)
            
            # Submit job
            try:
                job_info = self.deployer.submit_job(recipe_name, replica_config)
                replica_id = job_info["id"]
                
                self.logger.info(f"Submitted replica {i} (job {replica_id}) for group {group_id}")
                
                # Register replica as a regular service
                replica_data = {
                    "id": replica_id,
                    "name": f"{job_info['name']}-replica-{i}",
                    "recipe_name": recipe_name,
                    "status": job_info["status"],
                    "config": replica_config,
                    "created_at": job_info["created_at"],
                    "group_id": group_id,  # Link back to group
                    "replica_index": i
                }
                self.service_manager.register_service(replica_data)
                
                # Add replica to group
                self.service_manager.group_manager.add_replica(
                    group_id=group_id,
                    replica_id=replica_id,
                    replica_index=i,
                    status=job_info["status"]
                )
                
                replica_jobs.append(replica_data)
                
            except Exception as e:
                self.logger.exception(f"Failed to submit replica {i}: {e}")
                # Continue with other replicas
        
        # Get group info to return
        group_info = self.service_manager.group_manager.get_group(group_id)
        
        # Return group information
        return {
            "id": group_id,
            "name": f"{recipe_name}-group",
            "recipe_name": recipe_name,
            "status": group_info["status"],
            "type": "group",
            "replicas": group_info["replicas"],
            "num_replicas": replicas,
            "config": config,
            "created_at": group_info["created_at"]
        }
        
    def stop_service(self, service_id: str) -> bool:
        """Stop running service by cancelling SLURM job.
        
        If service_id is a group, stops all replicas in the group.
        """
        # Check if this is a service group
        if self.service_manager.is_group(service_id):
            self.logger.info(f"Stopping service group {service_id}")
            replica_ids = self.service_manager.get_all_replica_ids(service_id)
            
            # Cancel all replica jobs
            success = True
            for replica_id in replica_ids:
                if not self.deployer.cancel_job(replica_id):
                    self.logger.warning(f"Failed to cancel replica {replica_id}")
                    success = False
            
            # Delete the group
            self.service_manager.group_manager.delete_group(service_id)
            
            return success
        else:
            # Regular single service
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
            recipe_name = stored_service.get("recipe_name", "")
            
            # Get detailed status based on service type
            try:
                # Determine service type from recipe name
                if recipe_name.startswith("inference/vllm"):
                    is_ready, status = self.vllm_service._check_service_ready(service_id, stored_service)
                elif recipe_name.startswith("vector-db/"):
                    is_ready, status = self.vector_db_service._check_service_ready(service_id, stored_service)
                else:
                    # Fallback to basic SLURM status for unknown types
                    status = self.deployer.get_job_status(service_id)
            except Exception as e:
                self.logger.exception(f"Failed to get status for service {service_id}: {e}")
                print(f"ERROR: Failed to get status for service {service_id}: {e}")
                import traceback
                traceback.print_exc()
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
        """Get details of a specific service or service group."""
        # Check if this is a service group
        if self.service_manager.is_group(service_id):
            group_info = self.service_manager.get_group_info(service_id)
            if group_info:
                # Update replica statuses
                for replica in group_info["replicas"]:
                    replica_id = replica["id"]
                    status_dict = self.get_service_status(replica_id)
                    replica["status"] = status_dict.get("status", "unknown")
                    self.service_manager.update_replica_status(replica_id, replica["status"])
                
                # Ensure group_info has 'name' field for API compatibility
                if "name" not in group_info:
                    group_info["name"] = f"{group_info['recipe_name']}-group"
                
                # Group status is automatically updated by ServiceGroupManager
                return group_info
            return None
        
        # Regular single service
        stored_service = self.service_manager.get_service(service_id)
        if stored_service:
            status_dict = self.get_service_status(service_id)
            current_status = status_dict.get("status")
            if current_status != stored_service.get("status"):
                self.service_manager.update_service_status(service_id, current_status)
                stored_service = stored_service.copy()
                stored_service["status"] = current_status
            return stored_service
        return None

    def get_service_logs(self, service_id: str) -> Dict[str, str]:
        """Get slurm logs from a service.
        
        Returns:
            Dictionary with 'logs' field containing the log output
        """
        self.logger.debug("Fetching logs for service %s", service_id)
        logs = self.deployer.get_job_logs(service_id)
        return {"logs": logs}
    
    def get_service_status(self, service_id: str) -> Dict[str, str]:
        """Get current detailed status of a service.
        
        Returns:
            Dictionary with 'status' field containing the current service status
        """
        # Get detailed status based on service type
        stored_service = self.service_manager.get_service(service_id)
        if not stored_service:
            return {"status": "not_found"}
        
        try:
            recipe_name = stored_service.get("recipe_name", "")
            if recipe_name.startswith("inference/vllm"):
                is_ready, current_status = self.vllm_service._check_service_ready(service_id, stored_service)
            elif recipe_name.startswith("vector-db/"):
                is_ready, current_status = self.vector_db_service._check_service_ready(service_id, stored_service)
            else:
                # Fallback to basic SLURM status for unknown types
                current_status = self.deployer.get_job_status(service_id)
        except Exception as e:
            self.logger.exception(f"Failed to get status for service {service_id}: {e}")
            print(f"ERROR: Failed to get status for service {service_id}: {e}")
            import traceback
            traceback.print_exc()
            current_status = "unknown"
        return {"status": current_status}

    def find_vllm_services(self) -> List[Dict[str, Any]]:
        """Find running VLLM services and their endpoints."""
        return self.vllm_service.find_services()
    
    def find_vector_db_services(self) -> List[Dict[str, Any]]:
        """Find running vector database services and their endpoints."""
        return self.vector_db_service.find_services()
    
    def get_collections(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Get list of collections from a vector database service."""
        return self.vector_db_service.get_collections(service_id, timeout)
    
    def get_collection_info(self, service_id: str, collection_name: str, timeout: int = 5) -> Dict[str, Any]:
        """Get detailed information about a specific collection."""
        return self.vector_db_service.get_collection_info(service_id, collection_name, timeout)
    
    def create_collection(self, service_id: str, collection_name: str, vector_size: int, 
                         distance: str = "Cosine", timeout: int = 10) -> Dict[str, Any]:
        """Create a new collection in the vector database."""
        return self.vector_db_service.create_collection(service_id, collection_name, vector_size, distance, timeout)
    
    def delete_collection(self, service_id: str, collection_name: str, timeout: int = 10) -> Dict[str, Any]:
        """Delete a collection from the vector database."""
        return self.vector_db_service.delete_collection(service_id, collection_name, timeout)
    
    def upsert_points(self, service_id: str, collection_name: str, points: List[Dict[str, Any]], 
                     timeout: int = 30) -> Dict[str, Any]:
        """Insert or update points in a collection."""
        return self.vector_db_service.upsert_points(service_id, collection_name, points, timeout)
    
    def search_points(self, service_id: str, collection_name: str, query_vector: List[float], 
                     limit: int = 10, timeout: int = 10) -> Dict[str, Any]:
        """Search for similar vectors in a collection."""
        return self.vector_db_service.search_points(service_id, collection_name, query_vector, limit, timeout)
    
    def get_vllm_models(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Query a running VLLM service for available models.
        
        Returns a dict with either:
        - {"success": True, "models": [list of model ids]}
        - {"success": False, "error": "...", "message": "...", "models": []}
        """
        return self.vllm_service.get_models(service_id, timeout)
    
    def get_vllm_metrics(self, service_id: str, timeout: int = 10) -> Dict[str, Any]:
        """Get Prometheus metrics from a vLLM service.
        
        Returns a dict with either:
        - {"success": True, "metrics": "prometheus text format", ...}
        - {"success": False, "error": "...", "message": "...", "metrics": ""}
        """
        return self.vllm_service.get_metrics(service_id, timeout)
    
    def get_qdrant_metrics(self, service_id: str, timeout: int = 10) -> Dict[str, Any]:
        """Get Prometheus metrics from a Qdrant service.
        
        Returns a dict with either:
        - {"success": True, "metrics": "prometheus text format", ...}
        - {"success": False, "error": "...", "message": "...", "metrics": ""}
        """
        return self.vector_db_service.get_metrics(service_id, timeout)
    
    def prompt_vllm_service(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a running VLLM service."""
        return self.vllm_service.prompt(service_id, prompt, **kwargs)
    
