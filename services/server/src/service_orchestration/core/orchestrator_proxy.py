"""
Manages the ServiceOrchestrator running on Meluxina.
Server communicates with it via SSH API calls.
"""

import logging
from typing import Dict, Any, Optional, List
from ssh_manager import SSHManager

logger = logging.getLogger(__name__)


class OrchestratorProxy:
    """
    Manages communication with ServiceOrchestrator on Meluxina.
    Server stays local, orchestrator runs on Meluxina.
    """
    
    def __init__(self, ssh_manager: SSHManager, orchestrator_url: str, orchestrator_job_id: Optional[str] = None):
        """
        Args:
            ssh_manager: SSHManager instance for SSH tunneling
            orchestrator_url: URL of orchestrator on Meluxina (e.g., http://mel1234:8003)
            orchestrator_job_id: SLURM job ID of the orchestrator (for cleanup)
        """
        self.ssh_manager = ssh_manager
        self.orchestrator_url = orchestrator_url
        self.orchestrator_job_id = orchestrator_job_id
        logger.info(f"OrchestratorProxy initialized for {orchestrator_url}, job_id={orchestrator_job_id}")
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to orchestrator via SSH tunnel"""
        # Parse orchestrator URL
        from urllib.parse import urlparse, urlencode
        parsed = urlparse(self.orchestrator_url)
        host = parsed.hostname
        port = parsed.port or 80
        
        # Build the full path with query parameters for GET requests
        full_path = endpoint
        if method == "GET" and kwargs.get("params"):
            query_string = urlencode(kwargs["params"])
            full_path = f"{endpoint}?{query_string}"
        
        try:
            # Use SSH manager to execute curl on the remote machine (login node)
            # targeting the orchestrator (compute node)
            logger.debug(f"Making request to orchestrator: {method} {full_path} via {host}:{port}")
            
            # Only send json_data for non-GET methods
            json_data = None
            if method != "GET":
                json_data = kwargs.get("json") or kwargs.get("params")
            
            success, status, body = self.ssh_manager.http_request_via_ssh(
                remote_host=host,
                remote_port=port,
                method=method,
                path=full_path,
                headers=kwargs.get("headers"),
                json_data=json_data,
                timeout=kwargs.get("timeout", 30)
            )
            
            if not success:
                logger.error(f"SSH HTTP request failed - success={success}, status={status}, body='{body}'")
                logger.error(f"Request details: {method} {host}:{port}{full_path}")
                raise RuntimeError(f"SSH HTTP request failed: {body if body else 'No error details'}")
            
            if status >= 400:
                logger.error(f"HTTP error {status} from orchestrator: {body}")
                raise RuntimeError(f"HTTP error {status}: {body}")
            
            import json
            return json.loads(body)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse orchestrator response as JSON: {e}")
            logger.error(f"Raw body: {body}")
            raise RuntimeError(f"Invalid JSON response from orchestrator: {str(e)}")
        except Exception as e:
            logger.error(f"Request to orchestrator failed: {e}")
            raise
    
    def register_service(self, service_id: str, host: str, port: int, model: str) -> Dict[str, Any]:
        """Register a vLLM service with the orchestrator"""
        return self._make_request(
            "POST",
            "/api/register",
            params={"service_id": service_id, "host": host, "port": port, "model": model}
        )
    
    def unregister_service(self, service_id: str) -> Dict[str, Any]:
        """Unregister a service"""
        return self._make_request("DELETE", f"/api/services/{service_id}")
    
    def list_services(self) -> Dict[str, Any]:
        """List all services managed by orchestrator"""
        return self._make_request("GET", "/api/services")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get orchestrator metrics"""
        return self._make_request("GET", "/api/metrics")
    
    def configure_load_balancer(self, strategy: str) -> Dict[str, Any]:
        """Configure load balancing strategy"""
        return self._make_request("POST", "/api/configure", params={"strategy": strategy})
    
    def get_orchestrator_url_for_clients(self) -> str:
        """
        Get the URL that clients should use to reach orchestrator.
        This is the local Meluxina URL (no SSH needed for clients).
        """
        return self.orchestrator_url

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a SLURM job via orchestrator"""
        try:
            response = self._make_request("DELETE", f"/api/jobs/{job_id}")
            return response.get("status") == "cancelled"
        except:
            return False

    def get_job_status(self, job_id: str) -> str:
        """Get job status via orchestrator"""
        try:
            response = self._make_request("GET", f"/api/jobs/{job_id}")
            return response.get("status", "unknown")
        except:
            return "unknown"

    def get_job_logs(self, log_path: str, lines: int = 200) -> str:
        """Get job logs via orchestrator"""
        try:
            # Manually construct query string
            endpoint = f"/api/logs?path={log_path}&lines={lines}"
            response = self._make_request("GET", endpoint)
            return response.get("logs", "")
        except:
            return "Failed to fetch logs"

    def start_service(self, recipe_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Start a service via orchestrator (orchestrator builds the job)"""
        return self._make_request(
            "POST",
            "/api/services/start",
            json={"recipe_name": recipe_name, "config": config}
        )

    def stop_service(self, service_id: str) -> Dict[str, Any]:
        """Stop a service via orchestrator"""
        return self._make_request("POST", f"/api/services/stop/{service_id}")

    def list_recipes(self) -> List[Dict[str, Any]]:
        """List available recipes via orchestrator"""
        response = self._make_request("GET", "/api/recipes")
        return response.get("recipes", [])

    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get service details via orchestrator"""
        try:
            return self._make_request("GET", f"/api/services/{service_id}")
        except:
            return None

    def get_service_logs(self, service_id: str) -> Dict[str, str]:
        """Get service logs via orchestrator"""
        return self._make_request("GET", f"/api/services/{service_id}/logs")

    def get_service_status(self, service_id: str) -> Dict[str, str]:
        """Get service status via orchestrator"""
        return self._make_request("GET", f"/api/services/{service_id}/status")
    
    def list_service_groups(self) -> List[Dict[str, Any]]:
        """List all service groups via orchestrator"""
        response = self._make_request("GET", "/api/service-groups")
        return response.get("service_groups", [])
    
    def get_service_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get service group details via orchestrator"""
        try:
            return self._make_request("GET", f"/api/service-groups/{group_id}")
        except:
            return None
    
    def get_service_group_status(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get service group status via orchestrator"""
        try:
            return self._make_request("GET", f"/api/service-groups/{group_id}/status")
        except:
            return None
    
    def stop_service_group(self, group_id: str) -> Dict[str, Any]:
        """Stop all replicas in a service group via orchestrator"""
        return self._make_request("POST", f"/api/service-groups/{group_id}/stop")

    # ===== Data Plane Operations (vLLM) =====

    def find_vllm_services(self) -> List[Dict[str, Any]]:
        """Find running vLLM services"""
        return self._make_request("GET", "/api/services/vllm")

    def get_vllm_models(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Get models from a vLLM service"""
        return self._make_request("GET", f"/api/services/vllm/{service_id}/models", params={"timeout": timeout})

    def prompt_vllm_service(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a vLLM service"""
        data = {"prompt": prompt, **kwargs}
        return self._make_request("POST", f"/api/services/vllm/{service_id}/prompt", json=data)

    # ===== Data Plane Operations (Vector DB) =====

    def find_vector_db_services(self) -> List[Dict[str, Any]]:
        """Find running vector DB services"""
        return self._make_request("GET", "/api/services/vector-db")

    def get_collections(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Get collections from a vector DB service"""
        return self._make_request("GET", f"/api/services/vector-db/{service_id}/collections", params={"timeout": timeout})

    def get_collection_info(self, service_id: str, collection_name: str, timeout: int = 5) -> Dict[str, Any]:
        """Get collection info"""
        return self._make_request("GET", f"/api/services/vector-db/{service_id}/collections/{collection_name}", params={"timeout": timeout})

    def create_collection(self, service_id: str, collection_name: str, vector_size: int, distance: str = "Cosine", timeout: int = 10) -> Dict[str, Any]:
        """Create a collection"""
        data = {"vector_size": vector_size, "distance": distance, "timeout": timeout}
        return self._make_request("PUT", f"/api/services/vector-db/{service_id}/collections/{collection_name}", json=data)

    def delete_collection(self, service_id: str, collection_name: str, timeout: int = 10) -> Dict[str, Any]:
        """Delete a collection"""
        return self._make_request("DELETE", f"/api/services/vector-db/{service_id}/collections/{collection_name}", params={"timeout": timeout})

    def upsert_points(self, service_id: str, collection_name: str, points: List[Dict[str, Any]], timeout: int = 30) -> Dict[str, Any]:
        """Upsert points to a collection"""
        data = {"points": points, "timeout": timeout}
        return self._make_request("PUT", f"/api/services/vector-db/{service_id}/collections/{collection_name}/points", json=data)

    def search_points(self, service_id: str, collection_name: str, query_vector: List[float], limit: int = 10, timeout: int = 10) -> Dict[str, Any]:
        """Search for similar points"""
        data = {"query_vector": query_vector, "limit": limit, "timeout": timeout}
        return self._make_request("POST", f"/api/services/vector-db/{service_id}/collections/{collection_name}/search", json=data)

    def get_service_metrics(self, service_id: str, timeout: int = 10) -> Dict[str, Any]:
        """Get metrics from any service (auto-detects service type).
        
        This is a generic metrics endpoint that delegates to the orchestrator
        to determine the service type and fetch appropriate metrics.
        
        Args:
            service_id: Service or service group ID
            timeout: Request timeout in seconds
            
        Returns:
            Dict with success status and metrics or error information
        """
        return self._make_request("GET", f"/api/services/{service_id}/metrics", params={"timeout": timeout})

    def stop_orchestrator(self) -> bool:
        """Stop the orchestrator job via SLURM."""
        if not self.orchestrator_job_id:
            logger.warning("No orchestrator job ID stored, cannot stop orchestrator")
            return False
        
        try:
            logger.info(f"Cancelling orchestrator job {self.orchestrator_job_id}...")
            # Use scancel via SSH
            success, stdout, stderr = self.ssh_manager.execute_remote_command(
                f"scancel {self.orchestrator_job_id}",
                timeout=10
            )
            
            if success:
                logger.info(f"Successfully cancelled orchestrator job {self.orchestrator_job_id}")
                return True
            else:
                logger.error(f"Failed to cancel orchestrator job: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error cancelling orchestrator job: {e}")
            return False

    def get_orchestrator_url(self) -> Optional[str]:
        """Get the internal orchestrator URL."""
        return self.orchestrator_url
