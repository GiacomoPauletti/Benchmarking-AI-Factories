"""
Core logic for the server service.
Orchestrates AI workloads using SLURM + Apptainer.
"""

from pathlib import Path
import requests
from typing import Dict, List, Optional, Any
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        
        Two modes:
        1. Single service: No replicas or gpu_per_replica specified
        2. Service group: replicas or gpu_per_replica specified in recipe/config
        """
        try:
            import yaml
            
            # Load recipe
            recipe_path = self.deployer._find_recipe(recipe_name)
            with open(recipe_path, 'r') as f:
                recipe = yaml.safe_load(f)
            
            # Use config as-is - let deployer merge with recipe defaults
            full_config = config or {}
            
            # Check if replicas or gpu_per_replica is specified (either in config or recipe)
            has_replicas = (full_config.get('replicas') or recipe.get('replicas'))
            has_gpu_per_replica = (full_config.get('gpu_per_replica') or recipe.get('gpu_per_replica'))
            
            print(f"[DEBUG] Recipe: {recipe_name}")
            print(f"[DEBUG] Config: {full_config}")
            print(f"[DEBUG] has_replicas: {has_replicas}, has_gpu_per_replica: {has_gpu_per_replica}")
            print(f"[DEBUG] Recipe gpu_per_replica: {recipe.get('gpu_per_replica')}")
            
            if has_replicas or has_gpu_per_replica:
                # Multi-replica mode: create a service group
                print(f"[DEBUG] Using replica group mode")
                return self._start_service_group(recipe_name, full_config, recipe)
            else:
                # Single service mode: create a single service
                print(f"[DEBUG] Using single service mode")
                return self._start_single_service(recipe_name, full_config)
            
        except Exception as e:
            self.logger.exception("Failed to start service %s: %s", recipe_name, e)
            raise RuntimeError(f"Failed to start service: {str(e)}")
    
    def _start_single_service(self, recipe_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start a single service (no replicas/group)."""
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
    
    def _start_service_group(self, recipe_name: str, config: Dict[str, Any], recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Start a service group with replica architecture.

        This mode runs multiple services within a single SLURM job,
        each process bound to specific CPU/GPU(s) and listening on a different port.
        
        Defaults to 1 replica per node if gpu_per_replica not specified.
        """        
        # Get configuration
        total_gpus = int(config.get('gpu') or recipe.get('resources', {}).get('gpu') or recipe.get('gpu', 4))
        nodes = int(config.get('nodes') or recipe.get('resources', {}).get('nodes') or recipe.get('nodes', 1))
        base_port = int(config.get('base_port') or recipe.get('base_port', 8001))
        
        # Default: 1 GPU per replica (data-parallel, multiple replicas per node)
        # This is safer for small models that don't support tensor parallelism
        gpu_per_replica = int(config.get('gpu_per_replica') or recipe.get('gpu_per_replica', 1))
        
        # Calculate replicas per node
        replicas_per_node = total_gpus // gpu_per_replica
        total_replicas = nodes * replicas_per_node
        
        print(f"[DEBUG] Creating replica group: {nodes} nodes × {replicas_per_node} replicas/node = {total_replicas} total replicas (gpu_per_replica={gpu_per_replica})")
        self.logger.info(f"Creating replica group: {nodes} nodes × {replicas_per_node} replicas/node = {total_replicas} total replicas (gpu_per_replica={gpu_per_replica})")
        
        # Create replica service group
        group_id = self.service_manager.group_manager.create_replica_group(
            recipe_name=recipe_name,
            num_nodes=nodes,
            replicas_per_node=replicas_per_node,
            total_replicas=total_replicas,
            config=config
        )
        
        print(f"[DEBUG] Created group {group_id}, now submitting {nodes} node jobs...")
        
        # Submit one SLURM job per node
        for node_idx in range(nodes):
            print(f"[DEBUG] Submitting job for node {node_idx}...")
            # Create node-specific config
            node_config = config.copy()
            node_config['node_index'] = node_idx
            node_config['replicas_per_node'] = replicas_per_node
            node_config['base_port'] = base_port
            node_config['gpu_per_replica'] = gpu_per_replica
            
            # Remove fields that shouldn't be passed to deployer
            node_config.pop('replicas', None)
            
            try:
                # Submit SLURM job
                job_info = self.deployer.submit_job(recipe_name, node_config)
                job_id = job_info["id"]
                
                self.logger.info(f"Submitted node job {job_id} (node {node_idx}) for group {group_id}")
                
                # Register all replicas for this node
                for local_replica_idx in range(replicas_per_node):
                    global_replica_idx = node_idx * replicas_per_node + local_replica_idx
                    port = base_port + local_replica_idx
                    gpu_id = local_replica_idx * gpu_per_replica
                    
                    # Add replica to group
                    self.service_manager.group_manager.add_replica(
                        group_id=group_id,
                        job_id=job_id,
                        node_index=node_idx,
                        replica_index=global_replica_idx,
                        port=port,
                        gpu_id=gpu_id,
                        status=job_info["status"]
                    )
                    
                    # Also register as individual service for tracking
                    replica_id = f"{job_id}:{port}"
                    replica_data = {
                        "id": replica_id,
                        "name": f"{job_info['name']}-replica-{global_replica_idx}",
                        "recipe_name": recipe_name,
                        "status": job_info["status"],
                        "config": {
                            **node_config,
                            "port": port,
                            "gpu_id": gpu_id,
                            "replica_index": global_replica_idx
                        },
                        "created_at": job_info["created_at"],
                        "group_id": group_id,
                        "replica_index": global_replica_idx,
                        "job_id": job_id
                    }
                    self.service_manager.register_service(replica_data)
                
            except Exception as e:
                self.logger.exception(f"Failed to submit job for node {node_idx}: {e}")
                # Continue with other nodes
        
        # Get group info to return
        group_info = self.service_manager.group_manager.get_group(group_id)
        
        # Return group information
        return {
            "id": group_id,
            "name": f"{recipe_name}-group",
            "recipe_name": recipe_name,
            "status": group_info["status"],
            "type": "replica_group",
            "num_nodes": nodes,
            "replicas_per_node": replicas_per_node,
            "total_replicas": total_replicas,
            "node_jobs": group_info["node_jobs"],
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
            
            # Get group info to extract unique job IDs
            group_info = self.service_manager.group_manager.get_group(service_id)
            if not group_info:
                self.logger.error(f"Group {service_id} not found")
                return False
            
            # Extract unique job IDs from node_jobs
            job_ids = set()
            node_jobs = group_info.get("node_jobs", [])
            
            # Handle both list and dict formats
            if isinstance(node_jobs, list):
                for node_data in node_jobs:
                    job_id = node_data.get("job_id")
                    if job_id:
                        job_ids.add(job_id)
            elif isinstance(node_jobs, dict):
                for node_data in node_jobs.values():
                    job_id = node_data.get("job_id")
                    if job_id:
                        job_ids.add(job_id)
            
            # Cancel all jobs
            success = True
            for job_id in job_ids:
                self.logger.info(f"Cancelling job {job_id} for group {service_id}")
                if not self.deployer.cancel_job(job_id):
                    self.logger.warning(f"Failed to cancel job {job_id}")
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
                    is_ready, status, _ = self.vllm_service._check_ready_and_discover_model(service_id, stored_service)
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
            self.logger.info(f"Getting service group {service_id}")
            group_info = self.service_manager.get_group_info(service_id)
            if group_info:
                self.logger.info(f"Group info retrieved: {group_info.get('id')}, status: {group_info.get('status')}, node_jobs count: {len(group_info.get('node_jobs', []))}")
                # Update replica statuses - handle both group types
                all_replicas = self.service_manager.group_manager.get_all_replicas_flat(service_id)
                self.logger.info(f"Got {len(all_replicas)} replicas for group {service_id}")
                
                for replica in all_replicas:
                    replica_id = replica["id"]
                    status_dict = self.get_service_status(replica_id)
                    replica["status"] = status_dict.get("status", "unknown")
                    self.service_manager.update_replica_status(replica_id, replica["status"])
                
                # Ensure group_info has 'name' field for API compatibility
                if "name" not in group_info:
                    group_info["name"] = f"{group_info['recipe_name']}-group"
                
                # Group status is automatically updated by ServiceGroupManager
                return group_info
            self.logger.warning(f"Group {service_id} not found in group_manager")
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
        """Get current detailed status of a service or service group.
        
        Handles both regular service IDs, composite replica IDs (job_id:port), and group IDs.
        
        Returns:
            Dictionary with 'status' field containing the current service status
        """
        # Check if this is a service group
        if self.service_manager.is_group(service_id):
            group_info = self.service_manager.get_group_info(service_id)
            if not group_info:
                return {"status": "not_found"}
            # Return the group's overall status
            return {"status": group_info.get("status", "unknown")}
        
        # Handle composite replica IDs (e.g., "3712483:8001")
        if ":" in service_id:
            # For replicas, we need to check the actual service health, not SLURM job status
            # The SLURM job may complete while replicas continue running as background processes
            stored_service = self.service_manager.get_service(service_id)
            if not stored_service:
                return {"status": "not_found"}
            
            try:
                recipe_name = stored_service.get("recipe_name", "")
                # Check actual service readiness (health endpoint, etc.)
                if recipe_name.startswith("inference/vllm"):
                    is_ready, current_status, _ = self.vllm_service._check_ready_and_discover_model(service_id, stored_service)
                    return {"status": current_status}
                elif recipe_name.startswith("vector-db/"):
                    is_ready, current_status = self.vector_db_service._check_service_ready(service_id, stored_service)
                    return {"status": current_status}
                else:
                    # Fallback to SLURM status for unknown replica types
                    job_id = service_id.split(":")[0]
                    current_status = self.deployer.get_job_status(job_id)
                    return {"status": current_status}
            except Exception as e:
                self.logger.exception(f"Failed to get status for replica {service_id}: {e}")
                return {"status": "unknown"}
        
        # Get detailed status based on service type
        stored_service = self.service_manager.get_service(service_id)
        if not stored_service:
            return {"status": "not_found"}
        
        try:
            recipe_name = stored_service.get("recipe_name", "")
            if recipe_name.startswith("inference/vllm"):
                is_ready, current_status, _ = self.vllm_service._check_ready_and_discover_model(service_id, stored_service)
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
    
    # ========================================================================
    # Service Group Management Methods
    # ========================================================================
    
    def list_service_groups(self) -> List[Dict[str, Any]]:
        """List all service groups with summary information.
        
        Returns:
            List of service group summary objects
        """
        groups = self.service_manager.group_manager.list_groups()
        
        # Enrich each group with current status counts
        enriched_groups = []
        for group in groups:
            group_id = group["id"]
            
            # Get all replica service IDs for this group
            all_services = self.service_manager.list_services()
            replica_ids = [s["id"] for s in all_services if s.get("group_id") == group_id]
            
            # Get status for each replica in parallel using existing service functions
            status_counts = {
                "healthy": 0,
                "starting": 0,
                "pending": 0,
                "failed": 0
            }
            
            # Check all replicas in parallel
            replica_statuses = {}
            max_workers = min(len(replica_ids), 8)  # Cap at 8 concurrent checks
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all status check tasks
                future_to_id = {
                    executor.submit(self.get_service_status, replica_id): replica_id
                    for replica_id in replica_ids
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_id):
                    replica_id = future_to_id[future]
                    try:
                        status_dict = future.result()
                        status = status_dict.get("status", "unknown")
                        replica_statuses[replica_id] = status
                        
                        # Count by category
                        if status == "running":
                            status_counts["healthy"] += 1
                        elif status == "starting":
                            status_counts["starting"] += 1
                        elif status in ["pending", "building"]:
                            status_counts["pending"] += 1
                        elif status in ["failed", "cancelled"]:
                            status_counts["failed"] += 1
                    except Exception as e:
                        self.logger.error(f"Failed to get status for replica {replica_id}: {e}")
                        replica_statuses[replica_id] = "unknown"
            
            enriched_groups.append({
                "id": group_id,
                "type": group.get("type", "replica_group"),
                "recipe_name": group.get("recipe_name", "unknown"),
                "total_replicas": len(replica_ids),
                "healthy_replicas": status_counts["healthy"],
                "starting_replicas": status_counts["starting"],
                "pending_replicas": status_counts["pending"],
                "failed_replicas": status_counts["failed"],
                "created_at": group.get("created_at")
            })
        
        return enriched_groups
    
    def get_service_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a service group.
        
        Args:
            group_id: The service group ID
            
        Returns:
            Detailed group information or None if not found
        """
        # Get all services from service manager
        all_services = self.service_manager.list_services()
        
        # Filter services by group_id
        group_replicas = [s for s in all_services if s.get("group_id") == group_id]
        
        if not group_replicas:
            return None
        
        # Get full service info for each replica using existing get_service function
        enriched_replicas = []
        for replica in group_replicas:
            replica_id = replica["id"]
            # Use get_service to get full info including current status
            service_info = self.get_service(replica_id)
            if service_info:
                enriched_replicas.append(service_info)
            else:
                # Fallback to stored data if get_service fails
                enriched_replicas.append(replica)
        
        # Count replica statuses
        status_counts = {
            "healthy": sum(1 for r in enriched_replicas if r.get("status") == "running"),
            "starting": sum(1 for r in enriched_replicas if r.get("status") == "starting"),
            "pending": sum(1 for r in enriched_replicas if r.get("status") in ["pending", "building"]),
            "failed": sum(1 for r in enriched_replicas if r.get("status") in ["failed", "cancelled"])
        }
        
        # Extract common fields from first replica
        first_replica = enriched_replicas[0]
        recipe_name = first_replica.get("recipe_name", "unknown")
        base_port = first_replica.get("config", {}).get("base_port")
        
        # Group replicas by job_id to create node_jobs structure
        node_jobs = {}
        for replica in enriched_replicas:
            job_id = replica.get("id", "").split(":")[0]  # Extract job_id from composite ID
            node_index = replica.get("config", {}).get("node_index", 0)
            
            if job_id not in node_jobs:
                node_jobs[job_id] = {
                    "job_id": job_id,
                    "node_index": node_index,
                    "replicas": []
                }
            
            node_jobs[job_id]["replicas"].append({
                "id": replica.get("id"),
                "name": replica.get("name"),
                "status": replica.get("status"),
                "port": replica.get("config", {}).get("port"),
                "gpu_id": replica.get("config", {}).get("gpu_id"),
                "replica_index": replica.get("replica_index")
            })
        
        return {
            "id": group_id,
            "type": "replica_group",
            "replicas": [
                {
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "status": r.get("status"),
                    "port": r.get("config", {}).get("port"),
                    "gpu_id": r.get("config", {}).get("gpu_id"),
                    "replica_index": r.get("replica_index"),
                    "job_id": r.get("id", "").split(":")[0]
                }
                for r in enriched_replicas
            ],
            "total_replicas": len(enriched_replicas),
            "healthy_replicas": status_counts["healthy"],
            "starting_replicas": status_counts["starting"],
            "pending_replicas": status_counts["pending"],
            "failed_replicas": status_counts["failed"],
            "recipe_name": recipe_name,
            "base_port": base_port,
            "node_jobs": list(node_jobs.values())
        }
    
    def stop_service_group(self, group_id: str) -> Dict[str, Any]:
        """Stop all replicas in a service group.
        
        Args:
            group_id: The service group ID
            
        Returns:
            Result dictionary with success status and count of stopped replicas
        """
        # Get all replicas in the group
        all_replicas = self.service_manager.group_manager.get_all_replicas_flat(group_id)
        
        if not all_replicas:
            return {
                "success": False,
                "error": f"Service group '{group_id}' not found"
            }
        
        # Stop each replica
        stopped_count = 0
        failed_replicas = []
        
        for replica in all_replicas:
            replica_id = replica["id"]
            try:
                if self.stop_service(replica_id):
                    stopped_count += 1
                else:
                    failed_replicas.append(replica_id)
            except Exception as e:
                self.logger.error(f"Failed to stop replica {replica_id}: {e}")
                failed_replicas.append(replica_id)
        
        # Update group status to cancelled
        self.service_manager.group_manager.update_group_status(group_id, "cancelled")
        
        if failed_replicas:
            return {
                "success": True,
                "message": f"Service group {group_id} partially stopped",
                "group_id": group_id,
                "replicas_stopped": stopped_count,
                "replicas_failed": len(failed_replicas),
                "failed_replica_ids": failed_replicas
            }
        
        return {
            "success": True,
            "message": f"Service group {group_id} stopped successfully",
            "group_id": group_id,
            "replicas_stopped": stopped_count
        }
    
    def get_service_group_status(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get aggregated status of a service group with parallel status checks.
        
        Args:
            group_id: The service group ID
            
        Returns:
            Status summary or None if group not found
        """
        # Get all replicas in the group
        all_replicas = self.service_manager.group_manager.get_all_replicas_flat(group_id)
        
        if not all_replicas:
            return None
        
        # Count replica statuses
        status_counts = {
            "healthy": 0,
            "starting": 0,
            "pending": 0,
            "failed": 0
        }
        
        replica_statuses = []
        
        # Check all replicas in parallel
        max_workers = min(len(all_replicas), 8)  # Cap at 8 concurrent checks
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all status check tasks
            future_to_replica = {
                executor.submit(self.get_service_status, replica["id"]): replica
                for replica in all_replicas
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_replica):
                replica = future_to_replica[future]
                replica_id = replica["id"]
                
                try:
                    status_dict = future.result()
                    current_status = status_dict.get("status", "unknown")
                    
                    replica_statuses.append({
                        "id": replica_id,
                        "status": current_status
                    })
                    
                    # Count by category
                    if current_status == "running":
                        status_counts["healthy"] += 1
                    elif current_status == "starting":
                        status_counts["starting"] += 1
                    elif current_status in ["pending", "building"]:
                        status_counts["pending"] += 1
                    elif current_status in ["failed", "cancelled"]:
                        status_counts["failed"] += 1
                except Exception as e:
                    self.logger.error(f"Failed to get status for replica {replica_id}: {e}")
                    replica_statuses.append({
                        "id": replica_id,
                        "status": "unknown"
                    })
        
        # Determine overall status
        total = len(all_replicas)
        if status_counts["healthy"] == total:
            overall_status = "healthy"
        elif status_counts["failed"] == total:
            overall_status = "failed"
        elif status_counts["healthy"] > 0 and status_counts["failed"] > 0:
            overall_status = "degraded"
        elif status_counts["healthy"] > 0:
            overall_status = "partial"
        else:
            overall_status = "starting"
        
        return {
            "group_id": group_id,
            "overall_status": overall_status,
            "total_replicas": total,
            "healthy_replicas": status_counts["healthy"],
            "starting_replicas": status_counts["starting"],
            "pending_replicas": status_counts["pending"],
            "failed_replicas": status_counts["failed"],
            "replica_statuses": replica_statuses
        }

