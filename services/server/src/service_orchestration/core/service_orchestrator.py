"""
ServiceOrchestrator runs on Meluxina and handles:
1. Managing SLURM jobs and services (start, stop, status)
2. Service registration and discovery
3. Health checking services (generic)
4. Collecting metrics
5. Routing requests to service-specific handlers (vLLM, Qdrant, etc.)

This is a pure business logic class with no FastAPI dependencies.
The FastAPI application is created separately in main.py using the api module.

Service-specific logic (prompting, model discovery, etc.) is delegated to:
- VllmService for inference operations
- QdrantService for vector database operations
"""

import asyncio
import logging
import time
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict
import httpx

from service_orchestration.core.slurm_client import SlurmClient
from service_orchestration.builders import JobBuilder
from service_orchestration.recipes import RecipeLoader, Recipe, InferenceRecipe
from service_orchestration.managers import ServiceManager
from service_orchestration.networking import EndpointResolver

logger = logging.getLogger().getChild("service_orchestrator")


class ServiceOrchestrator:
    """
    Orchestrates AI services (vLLM, Qdrant, etc.) on Meluxina.
    Receives commands from local Server via SSH API.
    Delegates service-specific operations to specialized handlers.
    """
    
    def __init__(self):
        # Service registry for tracking endpoints
        self.registered_endpoints: Dict[str, Dict[str, Any]] = {}
        
        # Initialize managers
        self.slurm_client = SlurmClient()
        self.service_manager = ServiceManager()
        
        # Initialize job builder
        base_path = os.getenv("REMOTE_BASE_PATH", os.getcwd())
        self.job_builder = JobBuilder(base_path)
        self.default_account = os.getenv("ORCHESTRATOR_ACCOUNT", "p200776")
        
        # Initialize helper utilities for service handlers
        recipes_dir = Path(base_path) / "src" / "recipes"
        self.recipe_loader = RecipeLoader(recipes_dir)
        self.endpoint_resolver = EndpointResolver(self.slurm_client, self.service_manager, self.recipe_loader)
        
        # Initialize service handlers (lazy-loaded for data plane operations)
        self._vllm_service = None
        self._qdrant_service = None
        
        self.metrics: Dict[str, Any] = {
            "total_requests": 0,
            "failed_requests": 0,
            "total_latency_ms": 0.0,
            "requests_per_service": defaultdict(int)
        }
        self._health_check_task: Optional[asyncio.Task] = None
        self._http_client = httpx.AsyncClient(timeout=300.0)
    
    @property
    def vllm_service(self):
        """Lazy-load vLLM service handler."""
        if self._vllm_service is None:
            from service_orchestration.services.inference.vllm_service import VllmService
            self._vllm_service = VllmService(
                self.slurm_client, 
                self.service_manager, 
                self.endpoint_resolver, 
                logger
            )
        return self._vllm_service
    
    @property
    def qdrant_service(self):
        """Lazy-load Qdrant service handler."""
        if self._qdrant_service is None:
            from service_orchestration.services.vector_db.qdrant_service import QdrantService
            self._qdrant_service = QdrantService(
                self.slurm_client,
                self.service_manager,
                self.endpoint_resolver,
                logger
            )
        return self._qdrant_service
    
    async def start(self):
        """Start background tasks"""
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("ServiceOrchestrator started")
    
    async def stop(self):
        """Stop background tasks"""
        if self._health_check_task:
            self._health_check_task.cancel()
        await self._http_client.aclose()
        logger.info("ServiceOrchestrator stopped")
    
    # ===== Management API (called by Server via SSH) =====
    
    def start_service(self, recipe_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start a new service (job) or service group (replica group)"""
        try:
            config = config or {}
            # Load validated recipe
            recipe = self.recipe_loader.load(recipe_name)
            if not recipe:
                raise ValueError(f"Recipe '{recipe_name}' not found")
            
            # Build job payload using Recipe object
            account = config.get("account") or self.default_account
            build_result = self.job_builder.build_job(recipe, config, account)
            
            # Submit job - pass the complete payload with script and job
            job_payload = {
                "script": build_result["script"],
                "job": build_result["job"]
            }
            job_id = self.slurm_client.submit_job(job_payload)
            
            # Use canonical recipe path for consistent storage (e.g., "inference/vllm-single-node")
            canonical_recipe_name = recipe.path or recipe_name
            
            # Check if this is a replica group recipe
            if recipe.is_replica_group:
                # This is a replica group - create group and pre-register replicas
                return self._start_replica_group(job_id, canonical_recipe_name, recipe, config)
            else:
                # Regular single-service job
                service_data = {
                    "id": job_id,
                    "name": f"{canonical_recipe_name}-{job_id}",
                    "recipe_name": canonical_recipe_name,
                    "status": "pending",
                    "config": config,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
                }
                self.service_manager.register_service(service_data)
                
                return {"status": "submitted", "job_id": job_id, "service_data": service_data}
            
        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            return {"status": "error", "message": str(e)}
    
    def _start_replica_group(self, job_id: str, recipe_name: str, 
                           recipe: Recipe, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start a replica group and pre-register replicas.
        
        Args:
            job_id: The SLURM job ID
            recipe_name: Name of the recipe
            recipe: Validated Recipe object
            config: User-provided config overrides
            
        Returns:
            Service group data with pre-registered replicas
        """
        # Get merged recipe with config
        merged_recipe = recipe.merge_config(config)
        resources = merged_recipe.resources
        
        # Extract configuration from merged recipe
        num_nodes = resources.nodes
        total_gpus = resources.gpu or 4
        
        # Get replica-specific settings (only available on InferenceRecipe)
        if isinstance(merged_recipe, InferenceRecipe):
            gpu_per_replica = merged_recipe.gpu_per_replica or 1
            base_port = merged_recipe.base_port
        else:
            gpu_per_replica = 1
            base_port = 8001
        
        # Calculate replicas
        replicas_per_node = total_gpus // gpu_per_replica
        total_replicas = num_nodes * replicas_per_node
        
        # Create service group using job_id in group_id
        group_id = self.service_manager.create_replica_group(
            recipe_name=recipe_name,
            num_nodes=num_nodes,
            replicas_per_node=replicas_per_node,
            total_replicas=total_replicas,
            config=config,
            job_id=job_id
        )
        
        # Pre-register replicas (they'll update to "ready" when health checks pass)
        replica_idx = 0
        for node_idx in range(num_nodes):
            # For single-node groups, we only have one job
            node_job_id = job_id  # In future, multi-node would have different job IDs
            
            for gpu_idx in range(replicas_per_node):
                port = base_port + replica_idx
                self.service_manager.add_replica(
                    group_id=group_id,
                    job_id=node_job_id,
                    node_index=node_idx,
                    replica_index=replica_idx,
                    port=port,
                    gpu_id=gpu_idx,
                    status="starting"  # Will become "ready" when health check succeeds
                )
                replica_idx += 1
        
        # Get complete group info to return
        group_info = self.service_manager.get_group_info(group_id)
        
        logger.info(f"Created replica group {group_id} with {total_replicas} replicas for job {job_id}")
        
        return {
            "status": "submitted",
            "job_id": job_id,
            "group_id": group_id,
            "service_data": group_info
        }

    def stop_service(self, service_id: str) -> Dict[str, Any]:
        """Stop a service (cancel job) or service group"""
        try:
            # Check if this is a service group ID
            if service_id.startswith("sg-"):
                return self.stop_service_group(service_id)
            
            # Regular service - cancel the job
            success = self.slurm_client.cancel_job(service_id)
            if success:
                self.service_manager.update_service_status(service_id, "cancelled")
                # Also remove from registered endpoints if present
                if service_id in self.registered_endpoints:
                    self.registered_endpoints.pop(service_id)
            return {"status": "cancelled" if success else "failed", "service_id": service_id}
        except Exception as e:
            logger.error(f"Failed to stop service {service_id}: {e}")
            return {"status": "error", "message": str(e)}

    def register_endpoint(self, service_id: str, host: str, port: int, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Register a service endpoint (called when service is ready).
        
        This is a generic registration method used by all service types.
        Service-specific metadata (e.g., model name for vLLM) can be passed via metadata dict.
        """
        url = f"http://{host}:{port}"
        endpoint_info = {
            "service_id": service_id,
            "host": host,
            "port": port,
            "url": url,
            "status": "unknown",
            "registered_at": time.time(),
            **(metadata or {})
        }
        self.registered_endpoints[service_id] = endpoint_info
        logger.info(f"Registered service {service_id} at {url}")
        
        # Update status in ServiceManager
        self.service_manager.update_service_status(service_id, "running")
        
        # Register with endpoint resolver for discovery
        self.endpoint_resolver.register(service_id, host, port)
        
        return {"status": "registered", "service_id": service_id, "url": url}
    
    def unregister_endpoint(self, service_id: str) -> Dict[str, Any]:
        """Unregister a service endpoint"""
        if service_id in self.registered_endpoints:
            self.registered_endpoints.pop(service_id)
            logger.info(f"Unregistered service {service_id}")
            return {"status": "unregistered", "service_id": service_id}
        return {"status": "not_found", "service_id": service_id}
    
    def list_services(self) -> Dict[str, Any]:
        """List all services (jobs)"""
        # Get all services from ServiceManager
        services = self.service_manager.list_services()
        
        # Update statuses from SLURM for non-terminal states
        for service in services:
            if service["status"] not in ["completed", "failed", "cancelled"]:
                current_status = self.slurm_client.get_job_status(service["id"])
                if current_status != service["status"]:
                    self.service_manager.update_service_status(service["id"], current_status)
                    service["status"] = current_status
        
        return {
            "services": services,
            "total": len(services)
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics across all services"""
        # Convert defaultdict to regular dict for JSON serialization
        metrics_copy = {k: v for k, v in self.metrics.items() if k != "requests_per_service"}
        metrics_copy["requests_per_service"] = dict(self.metrics["requests_per_service"])
        
        # Build per-service metrics from registered endpoints
        service_metrics = {}
        for service_id, endpoint_info in self.registered_endpoints.items():
            service_metrics[service_id] = {
                "status": endpoint_info.get("status", "unknown"),
                "url": endpoint_info.get("url"),
                "registered_at": endpoint_info.get("registered_at")
            }
        
        return {
            "global": metrics_copy,
            "services": service_metrics
        }
    
    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific service or service group"""
        # Check if it's a group
        if self.service_manager.is_group(service_id):
            return self.service_manager.get_group_info(service_id)
        
        # Regular service
        service = self.service_manager.get_service(service_id)
        if service:
            # Update status from SLURM if non-terminal
            if service["status"] not in ["completed", "failed", "cancelled"]:
                current_status = self.slurm_client.get_job_status(service_id)
                if current_status != service["status"]:
                    self.service_manager.update_service_status(service_id, current_status)
                    service["status"] = current_status
            
            # Resolve endpoint if running
            if service["status"] in ["running", "RUNNING"]:
                endpoint = self.endpoint_resolver.resolve(service_id)
                if endpoint:
                    service["endpoint"] = endpoint
                    
        return service
    
    def get_service_status(self, service_id: str) -> Dict[str, str]:
        """Get current status of a service or service group"""
        # Check if it's a group
        if self.service_manager.is_group(service_id):
            group_info = self.service_manager.get_group_info(service_id)
            if not group_info:
                return {"status": "not_found"}
            return {"status": group_info.get("status", "unknown")}
        
        # Regular service
        service = self.service_manager.get_service(service_id)
        if not service:
            return {"status": "not_found"}
        
        # Get live status from SLURM
        if service["status"] not in ["completed", "failed", "cancelled"]:
            current_status = self.slurm_client.get_job_status(service_id)
            return {"status": current_status}
        
        return {"status": service["status"]}
    
    def get_service_logs(self, service_id: str) -> Dict[str, str]:
        """Get SLURM logs from a service"""
        try:
            # Get job details to find log path
            job_details = self.slurm_client.get_job_details(service_id)
            if not job_details:
                return {"logs": f"Job {service_id} not found"}
            
            # Construct log path (typically in standard output file)
            # SLURM usually writes to slurm-{job_id}.out
            log_path = Path(os.getcwd()) / f"slurm-{service_id}.out"
            
            if not log_path.exists():
                # Try alternative locations
                base_path = os.getenv("REMOTE_BASE_PATH", os.getcwd())
                log_path = Path(base_path) / "logs" / f"{service_id}.out"
            
            if log_path.exists():
                # Read last 200 lines
                import subprocess
                result = subprocess.run(
                    ["tail", "-n", "200", str(log_path)],
                    capture_output=True,
                    text=True
                )
                return {"logs": result.stdout}
            else:
                return {"logs": f"Log file not found for job {service_id}"}
                
        except Exception as e:
            logger.error(f"Failed to get logs for {service_id}: {e}")
            return {"logs": f"Error fetching logs: {str(e)}"}
    
    def get_service_metrics(self, service_id: str, timeout: int = 10) -> Dict[str, Any]:
        """Get Prometheus metrics for a service by auto-detecting service type"""
        import requests
        from urllib.parse import urlparse
        from datetime import datetime
        
        logger.info(f"Getting metrics for service: {service_id}")
        
        # Check if it's a service group
        if self.service_manager.is_group(service_id):
            return {
                "success": False,
                "error": "Metrics endpoint does not support service groups. Query individual services instead."
            }
        
        # Get service info
        service = self.service_manager.get_service(service_id)
        if not service:
            logger.error(f"Service {service_id} not found")
            return {
                "success": False,
                "error": f"Service {service_id} not found"
            }
        
        # Extract recipe name to determine service type and default port
        recipe_name = service.get("recipe_name", "").lower()
        status = service.get("status", "unknown")
        
        # Determine default port based on service type
        if "vllm" in recipe_name:
            default_port = 8001  # DEFAULT_VLLM_PORT
        elif "qdrant" in recipe_name:
            default_port = 6333  # DEFAULT_QDRANT_PORT
        else:
            logger.warning(f"Metrics not available for service type: {recipe_name}")
            return {
                "success": False,
                "error": f"Metrics not available for service type: {recipe_name}",
                "status": status
            }
        
        # Check if service is ready
        if status not in ["running", "RUNNING", "ready"]:
            # Generate synthetic metrics for pending/starting services
            if status.lower() in ["pending", "starting"]:
                # Try to get creation time
                created_at_str = service.get("created_at")
                start_timestamp = time.time() # Default to now if not found
                if created_at_str:
                    try:
                        # Parse "2025-12-11T10:00:00" format
                        dt = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%S")
                        start_timestamp = dt.timestamp()
                    except Exception:
                        pass
                
                metric_name = "process_start_time_seconds"
                metric_value = start_timestamp
                
                metrics = [
                    f'# HELP {metric_name} Start time of the process since unix epoch in seconds.',
                    f'# TYPE {metric_name} gauge',
                    f'{metric_name} {metric_value}'
                ]
                
                return {
                    "success": True,
                    "metrics": "\n".join(metrics),
                    "service_id": service_id,
                    "endpoint": "synthetic",
                    "metrics_format": "prometheus_text_format"
                }

            return {
                "success": False,
                "error": f"Service is not ready yet (status: {status})",
                "message": f"The service is still starting up (status: {status}). Please wait a moment and try again.",
                "service_id": service_id,
                "status": status,
                "metrics": ""
            }
        
        try:
            # Resolve endpoint using endpoint_resolver
            endpoint = self.endpoint_resolver.resolve(service_id, default_port=default_port)
            if not endpoint:
                logger.debug(f"No endpoint found for service {service_id} when querying metrics")
                return {
                    "success": False,
                    "error": "Service endpoint not available",
                    "message": "The service endpoint is not available yet.",
                    "service_id": service_id,
                    "status": status,
                    "metrics": ""
                }
            
            # Parse endpoint URL and make direct HTTP request to compute node
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or default_port
            path = "/metrics"
            
            logger.debug(f"Querying metrics: http://{remote_host}:{remote_port}{path}")
            
            # Direct HTTP request to compute node
            try:
                response = requests.get(
                    f"http://{remote_host}:{remote_port}{path}",
                    timeout=timeout
                )
            except Exception as e:
                logger.warning(f"Metrics retrieval for {service_id} failed: {e}")
                return {
                    "success": False,
                    "error": f"Connection failed: {str(e)}",
                    "message": "Failed to connect to service for metrics.",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "metrics": ""
                }
            
            if response.status_code < 200 or response.status_code >= 300:
                logger.warning(f"Metrics endpoint for {service_id} returned {response.status_code}: {response.text[:200]}")
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code} from metrics endpoint",
                    "message": f"Failed to query metrics from service (HTTP {response.status_code}).",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "metrics": ""
                }
            
            logger.debug(f"Metrics retrieved for {service_id} (size: {len(response.text)} bytes)")
            
            return {
                "success": True,
                "metrics": response.text,  # Return raw Prometheus text format
                "service_id": service_id,
                "endpoint": endpoint,
                "metrics_format": "prometheus_text_format"
            }
            
        except Exception as e:
            logger.error(f"Failed to get metrics for {service_id}: {e}")
            return {
                "success": False,
                "error": f"Error fetching metrics: {str(e)}",
                "status": status,
                "metrics": ""
            }
    
    def list_recipes(self) -> List[Dict[str, Any]]:
        """List all available service recipes with simplified API format"""
        recipes = self.recipe_loader.list_all()
        return [recipe.to_api_response() for recipe in recipes]
    
    def list_service_groups(self) -> List[Dict[str, Any]]:
        """List all service groups"""
        return self.service_manager.list_groups()
    
    def get_service_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a service group"""
        return self.service_manager.get_group_info(group_id)
    
    def get_service_group_status(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get aggregated status of a service group"""
        group_info = self.service_manager.get_group_info(group_id)
        if not group_info:
            return None
        
        # Count replicas by status
        all_replicas = self.service_manager.get_all_replicas_flat(group_id)
        status_counts = {
            "healthy": 0,
            "starting": 0,
            "pending": 0,
            "failed": 0
        }
        
        for replica in all_replicas:
            status = replica.get("status", "unknown")
            if status == "running":
                status_counts["healthy"] += 1
            elif status == "starting":
                status_counts["starting"] += 1
            elif status in ["pending", "building"]:
                status_counts["pending"] += 1
            elif status in ["failed", "cancelled"]:
                status_counts["failed"] += 1
        
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
            "failed_replicas": status_counts["failed"]
        }
    
    def stop_service_group(self, group_id: str) -> Dict[str, Any]:
        """Stop all replicas in a service group"""
        group_info = self.service_manager.get_group_info(group_id)
        if not group_info:
            return {"status": "error", "message": f"Group {group_id} not found"}
        
        # Extract unique job IDs
        job_ids = set()
        node_jobs = group_info.get("node_jobs", [])
        
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
        stopped_count = 0
        failed_jobs = []
        
        for job_id in job_ids:
            success = self.slurm_client.cancel_job(job_id)
            if success:
                stopped_count += 1
            else:
                failed_jobs.append(job_id)
        
        # Update group status
        self.service_manager.update_group_status(group_id, "cancelled")
        
        if failed_jobs:
            return {
                "status": "partial",
                "message": f"Stopped {stopped_count} jobs, {len(failed_jobs)} failed",
                "group_id": group_id,
                "stopped": stopped_count,
                "failed": failed_jobs
            }
        
        return {
            "status": "success",
            "message": f"Stopped all {stopped_count} jobs",
            "group_id": group_id,
            "stopped": stopped_count
        }
    
    def update_service_group_status(self, group_id: str, new_status: str) -> Dict[str, Any]:
        """Update service group status (e.g., to 'cancelled').
        
        This is the recommended way to stop service groups as it preserves
        metadata for analysis while gracefully shutting down all replicas.
        
        Args:
            group_id: The service group ID
            new_status: The new status (currently only 'cancelled' is supported)
            
        Returns:
            Dict with status and operation details
        """
        group_info = self.service_manager.get_group_info(group_id)
        if not group_info:
            return {"status": "error", "message": f"Group {group_id} not found"}
        
        if new_status != "cancelled":
            return {
                "status": "error",
                "message": f"Unsupported status: {new_status}. Only 'cancelled' is currently supported."
            }
        
        # Extract unique job IDs
        job_ids = set()
        node_jobs = group_info.get("node_jobs", [])
        
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
        cancelled_count = 0
        failed_jobs = []
        
        for job_id in job_ids:
            success = self.slurm_client.cancel_job(job_id)
            if success:
                cancelled_count += 1
                # Update individual service status if it exists
                self.service_manager.update_service_status(job_id, "cancelled")
            else:
                failed_jobs.append(job_id)
        
        # Update group status
        self.service_manager.update_group_status(group_id, "cancelled")
        
        # Update all replica statuses
        replica_ids = self.service_manager.get_all_replica_ids(group_id)
        replicas_updated = 0
        for replica_id in replica_ids:
            self.service_manager.update_service_status(replica_id, "cancelled")
            replicas_updated += 1
        
        if failed_jobs:
            return {
                "status": "partial",
                "message": f"Service group {group_id} status updated to {new_status}. {cancelled_count} jobs cancelled, {len(failed_jobs)} failed",
                "group_id": group_id,
                "replicas_updated": replicas_updated,
                "jobs_cancelled": cancelled_count,
                "jobs_failed": failed_jobs
            }
        
        return {
            "status": "success",
            "message": f"Service group {group_id} status updated to {new_status}",
            "group_id": group_id,
            "replicas_updated": replicas_updated,
            "jobs_cancelled": cancelled_count
        }
    
    # ===== Job Management API (called by Server via SSH) =====

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel a SLURM job"""
        return self.stop_service(job_id)

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get SLURM job status"""
        status = self.slurm_client.get_job_status(job_id)
        return {"status": status, "job_id": job_id}

    def get_job_logs(self, log_path: str, lines: int = 200) -> Dict[str, Any]:
        """Get job logs"""
        try:
            path = Path(log_path)
            if not path.exists():
                return {"status": "error", "message": "Log file not found"}
                
            # Use tail to get last N lines
            result = subprocess.run(
                ["tail", "-n", str(lines), str(path)],
                capture_output=True,
                text=True
            )
            return {"status": "success", "logs": result.stdout}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    # ===== Health checking =====
    
    async def _health_check_loop(self):
        """Periodically health check all replica groups.
        
        Service-specific health checks are delegated to the respective service handlers.
        """
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                await self._check_all_replica_groups()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _check_all_replica_groups(self):
        """Check health of all replicas in all groups.
        
        Determines service type from recipe and delegates to appropriate handler.
        """
        groups = self.service_manager.list_groups()
        if not groups:
            return
        
        logger.debug(f"Checking replica groups: {len(groups)} groups found")
        
        tasks = []
        for group in groups:
            group_id = group["id"]
            recipe_name = group.get("recipe_name", "")
            replicas = self.service_manager.get_all_replicas_flat(group_id)
            
            for replica in replicas:
                # Only check replicas that aren't already "ready"
                if replica.get("status") != "ready":
                    logger.debug(f"Will check replica {replica['id']} in group {group_id}")
                    tasks.append(self._check_replica(group_id, replica, recipe_name))
        
        if tasks:
            logger.debug(f"Checking {len(tasks)} replicas...")
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_replica(self, group_id: str, replica: Dict[str, Any], recipe_name: str):
        """Check if a single replica is ready.
        
        Uses service-type-specific health check endpoints:
        - vLLM: /v1/models
        - Qdrant: /collections
        """
        replica_id = replica["id"]
        job_id = replica["job_id"]
        port = replica["port"]
        
        try:
            # First check if the SLURM job is running
            job_status = self.slurm_client.get_job_status(job_id)
            if job_status not in ["running", "RUNNING"]:
                # Job not running yet, keep status as "starting"
                return
            
            # Get the node where the job is running
            job_details = self.slurm_client.get_job_details(job_id)
            if not job_details or "nodes" not in job_details:
                return
            
            nodes = job_details["nodes"]
            if isinstance(nodes, list) and nodes:
                node = str(nodes[0]).strip()
            else:
                node = str(nodes).strip()
            
            if not node:
                return
            
            # Determine health check endpoint based on service type
            if "vllm" in recipe_name.lower() or "inference" in recipe_name.lower():
                health_url = f"http://{node}:{port}/v1/models"
                is_ready = await self._check_vllm_health(health_url)
            elif "qdrant" in recipe_name.lower() or "vector-db" in recipe_name.lower():
                health_url = f"http://{node}:{port}/collections"
                is_ready = await self._check_qdrant_health(health_url)
            else:
                # Generic health check - try /health endpoint
                health_url = f"http://{node}:{port}/health"
                is_ready = await self._check_generic_health(health_url)
            
            if is_ready:
                # Replica is ready!
                self.service_manager.update_replica_status(replica_id, "ready")
                
                # Update node info in the group if not set
                self.service_manager.update_node_info(group_id, job_id, node)
                
                # Register replica as an endpoint so it can be used for data plane operations
                group_info = self.service_manager.get_group_info(group_id)
                if group_info:
                    self.service_manager.register_service({
                        "id": replica_id,
                        "job_id": job_id,
                        "recipe_name": recipe_name,
                        "config": {},
                        "status": "running",
                        "created_at": replica.get("added_at", "")
                    })
                    # Register the endpoint
                    self.endpoint_resolver.register(replica_id, node, port)
                    logger.debug(f"Registered endpoint for replica {replica_id}: http://{node}:{port}")
                
                logger.info(f"Replica {replica_id} in group {group_id} is now ready on {node}:{port}")
                    
        except Exception as e:
            # Replica not ready yet - this is normal during startup
            logger.debug(f"Replica {replica_id} not ready yet: {e}")
    
    async def _check_vllm_health(self, url: str) -> bool:
        """Check if a vLLM endpoint is healthy via /v1/models."""
        try:
            response = await self._http_client.get(url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return data.get("object") == "list" and "data" in data
        except Exception:
            pass
        return False
    
    async def _check_qdrant_health(self, url: str) -> bool:
        """Check if a Qdrant endpoint is healthy via /collections."""
        try:
            response = await self._http_client.get(url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                # Qdrant returns {"result": {"collections": [...]}} or similar
                return "result" in data or "collections" in data
        except Exception:
            pass
        return False
    
    async def _check_generic_health(self, url: str) -> bool:
        """Check if a generic endpoint is healthy via /health."""
        try:
            response = await self._http_client.get(url, timeout=5.0)
            return response.status_code == 200
        except Exception:
            pass
        return False
