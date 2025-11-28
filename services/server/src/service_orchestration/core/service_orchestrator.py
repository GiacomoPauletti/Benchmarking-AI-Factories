"""
ServiceOrchestrator runs on Meluxina and handles:
1. Load balancing across vLLM instances
2. Receiving requests from clients (no SSH)
3. Health checking vLLM services
4. Collecting metrics
5. Managing SLURM jobs and services

This is a pure business logic class with no FastAPI dependencies.
The FastAPI application is created separately in main.py using the api module.
"""

import asyncio
import logging
import time
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
import httpx

from service_orchestration.core.slurm_client import SlurmClient
from service_orchestration.builders import JobBuilder, RecipeLoader
from service_orchestration.managers import ServiceManager
from service_orchestration.networking import EndpointResolver

logger = logging.getLogger().getChild("service_orchestrator")


@dataclass
class VLLMEndpoint:
    """Represents a vLLM service endpoint"""
    service_id: str
    host: str
    port: int
    model: str
    status: str = "unknown"  # unknown, healthy, unhealthy
    last_health_check: float = 0.0
    total_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    
    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
    
    @property
    def health_score(self) -> float:
        """Calculate health score (0-1) based on success rate and latency"""
        if self.total_requests == 0:
            return 1.0
        success_rate = 1 - (self.failed_requests / self.total_requests)
        # Penalize high latency (assuming 100ms is good, 1000ms is bad)
        latency_score = max(0, 1 - (self.avg_latency_ms / 1000.0))
        return (success_rate * 0.7) + (latency_score * 0.3)


class LoadBalancer:
    """Load balancer with multiple strategies"""
    
    def __init__(self, strategy: str = "round_robin"):
        self.strategy = strategy
        self._round_robin_index = 0
        self._lock = asyncio.Lock()
    
    async def select_endpoint(self, endpoints: List[VLLMEndpoint]) -> Optional[VLLMEndpoint]:
        """Select next endpoint based on strategy"""
        healthy_endpoints = [e for e in endpoints if e.status == "healthy"]
        
        if not healthy_endpoints:
            # Fallback to unknown status endpoints if no healthy ones
            healthy_endpoints = [e for e in endpoints if e.status == "unknown"]
            
        if not healthy_endpoints:
            logger.warning("No healthy endpoints available")
            return None
        
        if self.strategy == "round_robin":
            return await self._round_robin(healthy_endpoints)
        elif self.strategy == "least_loaded":
            return await self._least_loaded(healthy_endpoints)
        elif self.strategy == "best_health":
            return await self._best_health(healthy_endpoints)
        else:
            return healthy_endpoints[0]
    
    async def _round_robin(self, endpoints: List[VLLMEndpoint]) -> VLLMEndpoint:
        """Simple round-robin selection"""
        async with self._lock:
            endpoint = endpoints[self._round_robin_index % len(endpoints)]
            self._round_robin_index += 1
            return endpoint
    
    async def _least_loaded(self, endpoints: List[VLLMEndpoint]) -> VLLMEndpoint:
        """Select endpoint with fewest requests"""
        return min(endpoints, key=lambda e: e.total_requests)
    
    async def _best_health(self, endpoints: List[VLLMEndpoint]) -> VLLMEndpoint:
        """Select endpoint with best health score"""
        return max(endpoints, key=lambda e: e.health_score)


class ServiceOrchestrator:
    """
    Orchestrates vLLM services on Meluxina.
    Receives commands from local Server via SSH API.
    Handles client requests locally (no SSH).
    """
    
    def __init__(self):
        self.endpoints: Dict[str, VLLMEndpoint] = {}
        self.load_balancer = LoadBalancer(strategy="round_robin")
        
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
        
        # Initialize service handlers (for data plane operations)
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
            # Load recipe to check if it's a replica group
            recipe_name, recipe = self.recipe_loader.load(recipe_name)
            if not recipe:
                raise ValueError(f"Recipe '{recipe_name}' not found")
            
            # Build job payload
            account = config.get("account") or self.default_account
            build_result = self.job_builder.build_job(recipe_name, config, account)
            
            # Submit job - pass the complete payload with script and job
            job_payload = {
                "script": build_result["script"],
                "job": build_result["job"]
            }
            job_id = self.slurm_client.submit_job(job_payload)
            
            # Check if this is a replica group recipe
            gpu_per_replica = recipe.get("gpu_per_replica") or config.get("gpu_per_replica")
            
            if gpu_per_replica:
                # This is a replica group - create group and pre-register replicas
                return self._start_replica_group(job_id, recipe_name, recipe, config)
            else:
                # Regular single-service job
                service_data = {
                    "id": job_id,
                    "name": f"{recipe_name}-{job_id}",
                    "recipe_name": recipe_name,
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
                           recipe: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Start a replica group and pre-register replicas.
        
        Args:
            job_id: The SLURM job ID
            recipe_name: Name of the recipe
            recipe: Recipe configuration
            config: User-provided config overrides
            
        Returns:
            Service group data with pre-registered replicas
        """
        # Extract configuration
        resources = recipe.get("resources", {})
        num_nodes = int(config.get("nodes") or resources.get("nodes", 1))
        total_gpus = int(config.get("gpu") or resources.get("gpu", 4))
        gpu_per_replica = int(config.get("gpu_per_replica") or recipe.get("gpu_per_replica", 1))
        base_port = int(config.get("base_port") or recipe.get("base_port", 8001))
        
        # Calculate replicas
        replicas_per_node = total_gpus // gpu_per_replica
        total_replicas = num_nodes * replicas_per_node
        
        # Create service group using job_id in group_id
        group_id = self.service_manager.group_manager.create_replica_group(
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
                self.service_manager.group_manager.add_replica(
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
                # Also remove from endpoints if present
                if service_id in self.endpoints:
                    self.endpoints.pop(service_id)
            return {"status": "cancelled" if success else "failed", "service_id": service_id}
        except Exception as e:
            logger.error(f"Failed to stop service {service_id}: {e}")
            return {"status": "error", "message": str(e)}

    def register_service(self, service_id: str, host: str, port: int, model: str) -> Dict[str, Any]:
        """Register a new vLLM service endpoint (called when service is ready)"""
        endpoint = VLLMEndpoint(
            service_id=service_id,
            host=host,
            port=port,
            model=model,
            status="unknown"
        )
        self.endpoints[service_id] = endpoint
        logger.info(f"Registered service {service_id} at {endpoint.url}")
        
        # Update status in ServiceManager
        self.service_manager.update_service_status(service_id, "running")
        
        # Trigger immediate health check
        asyncio.create_task(self._check_endpoint(endpoint))
        
        return {"status": "registered", "service_id": service_id, "url": endpoint.url}
    
    def unregister_service(self, service_id: str) -> Dict[str, Any]:
        """Unregister a vLLM service"""
        if service_id in self.endpoints:
            endpoint = self.endpoints.pop(service_id)
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
        """Get aggregated metrics"""
        # Convert defaultdict to regular dict for JSON serialization
        metrics_copy = {k: v for k, v in self.metrics.items() if k != "requests_per_service"}
        metrics_copy["requests_per_service"] = dict(self.metrics["requests_per_service"])
        
        return {
            "global": metrics_copy,
            "services": {
                service_id: {
                    "total_requests": ep.total_requests,
                    "failed_requests": ep.failed_requests,
                    "avg_latency_ms": ep.avg_latency_ms,
                    "health_score": ep.health_score,
                    "status": ep.status
                }
                for service_id, ep in self.endpoints.items()
            }
        }
    
    def configure_load_balancer(self, strategy: str) -> Dict[str, Any]:
        """Configure load balancing strategy"""
        valid_strategies = ["round_robin", "least_loaded", "best_health"]
        if strategy not in valid_strategies:
            return {"status": "error", "message": f"Invalid strategy. Valid: {valid_strategies}"}
        
        self.load_balancer = LoadBalancer(strategy=strategy)
        logger.info(f"Load balancer strategy set to: {strategy}")
        return {"status": "configured", "strategy": strategy}
    
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
        """List all available service recipes"""
        return self.recipe_loader.list_all()
    
    def list_service_groups(self) -> List[Dict[str, Any]]:
        """List all service groups"""
        return self.service_manager.group_manager.list_groups()
    
    def get_service_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a service group"""
        return self.service_manager.get_group_info(group_id)
    
    def get_service_group_status(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get aggregated status of a service group"""
        group_info = self.service_manager.get_group_info(group_id)
        if not group_info:
            return None
        
        # Count replicas by status
        all_replicas = self.service_manager.group_manager.get_all_replicas_flat(group_id)
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
        group_info = self.service_manager.group_manager.get_group(group_id)
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
        self.service_manager.group_manager.update_group_status(group_id, "cancelled")
        
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
        group_info = self.service_manager.group_manager.get_group(group_id)
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
        self.service_manager.group_manager.update_group_status(group_id, "cancelled")
        
        # Update all replica statuses
        replica_ids = self.service_manager.group_manager.get_all_replica_ids(group_id)
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
    
    # ===== Client-facing API (local network, no SSH) =====
    
    async def forward_completion(self, request_data: dict) -> Dict[str, Any]:
        """
        Forward completion request to a vLLM service.
        This is called by clients on Meluxina - no SSH overhead.
        """
        # Select endpoint
        endpoint = await self.load_balancer.select_endpoint(list(self.endpoints.values()))
        if endpoint is None:
            raise RuntimeError("No healthy vLLM services available")
        
        # Track timing
        start_time = time.perf_counter()
        
        try:
            # Forward to vLLM
            response = await self._http_client.post(
                f"{endpoint.url}/v1/completions",
                json=request_data
            )
            response.raise_for_status()
            result = response.json()
            
            # Calculate latency
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            # Update endpoint metrics
            endpoint.total_requests += 1
            # Update running average
            if endpoint.avg_latency_ms == 0:
                endpoint.avg_latency_ms = latency_ms
            else:
                endpoint.avg_latency_ms = (
                    (endpoint.avg_latency_ms * (endpoint.total_requests - 1) + latency_ms) 
                    / endpoint.total_requests
                )
            
            # Update global metrics
            self.metrics["total_requests"] += 1
            self.metrics["total_latency_ms"] += latency_ms
            self.metrics["requests_per_service"][endpoint.service_id] += 1
            
            # Add metadata
            result["_orchestrator_meta"] = {
                "service_id": endpoint.service_id,
                "latency_ms": latency_ms,
                "endpoint": endpoint.url
            }
            
            logger.debug(f"Request forwarded to {endpoint.service_id}, latency: {latency_ms:.2f}ms")
            return result
            
        except Exception as e:
            endpoint.failed_requests += 1
            self.metrics["failed_requests"] += 1
            logger.error(f"Request to {endpoint.service_id} failed: {e}")
            raise RuntimeError(f"vLLM service error: {str(e)}")
    
    # ===== Health checking =====
    
    async def _health_check_loop(self):
        """Periodically health check all endpoints and replica groups"""
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                await self._check_all_endpoints()
                await self._check_all_replica_groups()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _check_all_endpoints(self):
        """Check health of all registered endpoints"""
        if not self.endpoints:
            return
            
        tasks = [self._check_endpoint(ep) for ep in self.endpoints.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_all_replica_groups(self):
        """Check health of all replicas in all groups"""
        groups = self.service_manager.group_manager.list_groups()
        if not groups:
            return
        
        logger.info(f"Checking replica groups: {len(groups)} groups found")
        
        tasks = []
        for group in groups:
            group_id = group["id"]
            replicas = self.service_manager.group_manager.get_all_replicas_flat(group_id)
            for replica in replicas:
                # Only check replicas that aren't already "ready"
                if replica.get("status") != "ready":
                    logger.info(f"Will check replica {replica['id']} in group {group_id}")
                    tasks.append(self._check_replica(group_id, replica))
        
        if tasks:
            logger.info(f"Checking {len(tasks)} replicas...")
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_replica(self, group_id: str, replica: Dict[str, Any]):
        """Check if a single replica is ready"""
        replica_id = replica["id"]
        job_id = replica["job_id"]
        logger.info(f"Checking replica {replica_id} for job {job_id}...")
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
            
            # Try to reach the replica's /v1/models endpoint
            url = f"http://{node}:{port}/v1/models"
            response = await self._http_client.get(url, timeout=5.0)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("object") == "list" and "data" in data:
                    # Replica is ready!
                    self.service_manager.group_manager.update_replica_status(replica_id, "ready")
                    
                    # Update node info in the group if not set
                    self.service_manager.group_manager.update_node_info(group_id, job_id, node)
                    
                    # Register replica as an endpoint so it can be used for data plane operations
                    # Use the composite replica_id (e.g., "3751387:8001") as service_id
                    group_info = self.service_manager.group_manager.get_group(group_id)
                    if group_info:
                        recipe_name = group_info.get("recipe_name", "inference/vllm-replicas")
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
    
    async def _check_endpoint(self, endpoint: VLLMEndpoint):
        """Check if a single endpoint is healthy"""
        try:
            response = await self._http_client.get(
                f"{endpoint.url}/health",
                timeout=5.0
            )
            if response.status_code == 200:
                if endpoint.status != "healthy":
                    logger.info(f"Service {endpoint.service_id} is now healthy")
                endpoint.status = "healthy"
            else:
                if endpoint.status != "unhealthy":
                    logger.warning(f"Service {endpoint.service_id} is unhealthy (status {response.status_code})")
                endpoint.status = "unhealthy"
        except Exception as e:
            if endpoint.status != "unhealthy":
                logger.warning(f"Health check failed for {endpoint.service_id}: {e}")
            endpoint.status = "unhealthy"
        
        endpoint.last_health_check = time.time()
