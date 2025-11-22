"""Qdrant-specific vector database service implementation."""

from typing import Dict, List, Optional, Any
from .vector_db_service import VectorDbService

DEFAULT_QDRANT_PORT = 6333

class QdrantService(VectorDbService):
    """Handles all Qdrant-specific vector database operations."""

    def find_services(self) -> List[Dict[str, Any]]:
        """Find running vector database services and their endpoints."""
        def is_vector_db(service):
            recipe_name = service.get("recipe_name", "").lower()
            # Match vector-db category
            return "vector-db" in recipe_name or recipe_name in ["qdrant", "chroma", "faiss"]
        
        services = self._filter_services(is_vector_db)
        self.logger.debug(f"Found {len(services)} vector DB services after filtering")
        vector_db_services = []
        
        for service in services:
            job_id = service.get("id")
            endpoint = self.endpoint_resolver.resolve(job_id, default_port=DEFAULT_QDRANT_PORT)
            if endpoint:
                self.logger.debug("Resolved endpoint for vector-db job %s -> %s", job_id, endpoint)
            else:
                self.logger.debug("No endpoint yet for vector-db job %s (status: %s)", job_id, service.get("status"))
            
            # Get detailed service-specific status instead of basic SLURM status
            try:
                is_ready, status = self._check_service_ready(job_id, service)
            except Exception as e:
                self.logger.warning(f"Failed to check readiness for service {job_id}: {e}")
                status = service.get("status", "unknown")
            
            vector_db_services.append({
                "id": job_id,
                "name": service.get("name"),
                "recipe_name": service.get("recipe_name", "unknown"),
                "endpoint": endpoint,
                "status": status
            })
        
        return vector_db_services

    def _check_service_ready(self, service_id: str, service_info: Dict[str, Any]) -> tuple[bool, str]:
        """Check if a vector DB service is ready to accept requests.
        
        Uses a hybrid approach:
        1. Check SLURM status first (fast filter for pending/building jobs)
        2. For RUNNING jobs, test HTTP connection to /collections endpoint
        
        Args:
            service_id: The service ID to check
            service_info: The service information dict
            
        Returns:
            Tuple of (is_ready: bool, status: str) where status is the current LIVE status
        """
        # Get the current LIVE status from SLURM
        try:
            basic_status = self.deployer.get_job_status(service_id).lower()
        except Exception as e:
            self.logger.warning(f"Failed to get status for service {service_id}: {e}")
            basic_status = service_info.get("status", "unknown").lower()
        
        # If not running yet, return basic status (no need to test connection)
        if basic_status != "running":
            is_ready = basic_status not in ["pending", "building", "starting"]
            return is_ready, basic_status
        
        # For RUNNING jobs, test actual HTTP connection to confirm Qdrant is ready
        # This replaces log parsing with a definitive connection test
        endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_QDRANT_PORT)
        if not endpoint:
            # Job is running but endpoint not available yet
            self.logger.debug(f"Service {service_id} is RUNNING but endpoint not resolved yet")
            return False, "starting"
        
        # Try lightweight HTTP GET to /collections with short timeout
        try:
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or DEFAULT_QDRANT_PORT
            path = "/collections"
            
            self.logger.debug(f"Testing readiness via connection to {remote_host}:{remote_port}{path}")
            
            # Use SSH to make the HTTP request with short timeout
            ssh_manager = self.deployer.ssh_manager
            success, status_code, body = ssh_manager.http_request_via_ssh(
                remote_host=remote_host,
                remote_port=remote_port,
                method="GET",
                path=path,
                timeout=8  # Short timeout for health checks
            )
            
            # Connection succeeded and got valid HTTP response
            if status_code >= 200 and status_code < 300:
                self.logger.debug(f"Service {service_id} is ready (HTTP {status_code})")
                return True, "running"
            else:
                # Connected but got error response - likely still initializing
                self.logger.debug(f"Service {service_id} connected but returned HTTP {status_code}")
                return False, "starting"
                
        except Exception as e:
            # Connection failed - service not ready yet
            self.logger.debug(f"Service {service_id} connection test failed: {e}")
            return False, "starting"

    def get_collections(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Get list of collections from a Qdrant service.
        
        Args:
            service_id: The service ID
            timeout: Request timeout in seconds
            
        Returns:
            Dict with either:
            - {"success": True, "collections": [list of collection names]}
            - {"success": False, "error": "...", "message": "...", "collections": []}
        """
        try:
            # Check if service exists and is ready
            service_info = self.service_manager.get_service(service_id)
            if not service_info:
                return {
                    "success": False,
                    "error": f"Service {service_id} not found",
                    "message": "The requested vector DB service could not be found.",
                    "collections": []
                }
            
            is_ready, status = self._check_service_ready(service_id, service_info)
            if not is_ready:
                return {
                    "success": False,
                    "error": f"Service is not ready yet (status: {status})",
                    "message": f"The vector DB service is still starting up (status: {status}). Please wait a moment and try again.",
                    "service_id": service_id,
                    "status": status,
                    "collections": []
                }
            
            endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_QDRANT_PORT)
            if not endpoint:
                return {
                    "success": False,
                    "error": "Service endpoint not available",
                    "message": "The vector DB service endpoint is not available yet.",
                    "service_id": service_id,
                    "status": status,
                    "collections": []
                }
            
            # Make HTTP request via SSH
            ssh_manager = self.deployer.ssh_manager
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or DEFAULT_QDRANT_PORT
            
            success, status_code, body = ssh_manager.http_request_via_ssh(
                remote_host=remote_host,
                remote_port=remote_port,
                method="GET",
                path="/collections",
                timeout=timeout
            )
            
            if not success or status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP {status_code} from collections endpoint",
                    "message": f"Failed to query collections from vector DB service (HTTP {status_code}).",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "collections": []
                }
            
            # Qdrant returns {"result": {"collections": [...]}}
            collections = []
            if "result" in body and "collections" in body["result"]:
                collections = [col["name"] for col in body["result"]["collections"]]
            
            return {
                "success": True,
                "collections": collections,
                "service_id": service_id,
                "endpoint": endpoint
            }
            
        except Exception as e:
            self.logger.exception("Failed to get collections for service %s", service_id)
            return {
                "success": False,
                "error": f"Exception during collection discovery: {str(e)}",
                "message": "An error occurred while querying the vector DB service for collections.",
                "service_id": service_id,
                "collections": []
            }

    def get_collection_info(self, service_id: str, collection_name: str, timeout: int = 5) -> Dict[str, Any]:
        """Get detailed information about a specific collection.
        
        Args:
            service_id: The service ID
            collection_name: Name of the collection
            timeout: Request timeout in seconds
            
        Returns:
            Dict with collection details or error
        """
        try:
            # Check if service exists and is ready
            service_info = self.service_manager.get_service(service_id)
            if not service_info:
                return {
                    "success": False,
                    "error": f"Service {service_id} not found",
                    "message": "The requested vector DB service could not be found."
                }
            
            is_ready, status = self._check_service_ready(service_id, service_info)
            if not is_ready:
                return {
                    "success": False,
                    "error": f"Service is not ready yet (status: {status})",
                    "message": f"The vector DB service is still starting up (status: {status}).",
                    "service_id": service_id,
                    "status": status
                }
            
            endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_QDRANT_PORT)
            if not endpoint:
                return {
                    "success": False,
                    "error": "Service endpoint not available",
                    "message": "The vector DB service endpoint is not available yet.",
                    "service_id": service_id
                }
            
            # Make HTTP request via SSH
            ssh_manager = self.deployer.ssh_manager
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or DEFAULT_QDRANT_PORT
            
            success, status_code, body = ssh_manager.http_request_via_ssh(
                remote_host=remote_host,
                remote_port=remote_port,
                method="GET",
                path=f"/collections/{collection_name}",
                timeout=timeout
            )
            
            if not success or status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP {status_code} from collection info endpoint",
                    "message": f"Failed to get collection info (HTTP {status_code}). Collection may not exist.",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "collection_name": collection_name
                }
            
            return {
                "success": True,
                "collection_info": body.get("result", {}),
                "service_id": service_id,
                "endpoint": endpoint,
                "collection_name": collection_name
            }
            
        except Exception as e:
            self.logger.exception("Failed to get collection info for %s in service %s", collection_name, service_id)
            return {
                "success": False,
                "error": f"Exception: {str(e)}",
                "message": "An error occurred while querying collection information.",
                "service_id": service_id,
                "collection_name": collection_name
            }

    def create_collection(self, service_id: str, collection_name: str, vector_size: int, 
                         distance: str = "Cosine", timeout: int = 10) -> Dict[str, Any]:
        """Create a new collection in Qdrant.
        
        Args:
            service_id: The service ID
            collection_name: Name for the new collection
            vector_size: Dimension of vectors
            distance: Distance metric ("Cosine", "Euclid", "Dot")
            timeout: Request timeout in seconds
            
        Returns:
            Dict with creation result
        """
        try:
            # Check if service exists and is ready
            service_info = self.service_manager.get_service(service_id)
            if not service_info:
                return {
                    "success": False,
                    "error": f"Service {service_id} not found",
                    "message": "The requested vector DB service could not be found."
                }
            
            is_ready, status = self._check_service_ready(service_id, service_info)
            if not is_ready:
                return {
                    "success": False,
                    "error": f"Service is not ready yet (status: {status})",
                    "message": f"The vector DB service is still starting up (status: {status}).",
                    "service_id": service_id,
                    "status": status
                }
            
            endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_QDRANT_PORT)
            if not endpoint:
                return {
                    "success": False,
                    "error": "Service endpoint not available",
                    "message": "The vector DB service endpoint is not available yet.",
                    "service_id": service_id
                }
            
            # Prepare request body
            request_body = {
                "vectors": {
                    "size": vector_size,
                    "distance": distance
                }
            }
            
            # Make HTTP request via SSH
            ssh_manager = self.deployer.ssh_manager
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or DEFAULT_QDRANT_PORT
            
            success, status_code, body = ssh_manager.http_request_via_ssh(
                remote_host=remote_host,
                remote_port=remote_port,
                method="PUT",
                path=f"/collections/{collection_name}",
                json_data=request_body,
                timeout=timeout
            )
            
            if not success or status_code not in [200, 201]:
                return {
                    "success": False,
                    "error": f"HTTP {status_code} from create collection endpoint",
                    "message": f"Failed to create collection (HTTP {status_code}).",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "collection_name": collection_name
                }
            
            return {
                "success": True,
                "message": f"Collection '{collection_name}' created successfully",
                "service_id": service_id,
                "endpoint": endpoint,
                "collection_name": collection_name,
                "vector_size": vector_size,
                "distance": distance
            }
            
        except Exception as e:
            self.logger.exception("Failed to create collection %s in service %s", collection_name, service_id)
            return {
                "success": False,
                "error": f"Exception: {str(e)}",
                "message": "An error occurred while creating the collection.",
                "service_id": service_id,
                "collection_name": collection_name
            }

    def delete_collection(self, service_id: str, collection_name: str, timeout: int = 10) -> Dict[str, Any]:
        """Delete a collection from Qdrant.
        
        Args:
            service_id: The service ID
            collection_name: Name of the collection to delete
            timeout: Request timeout in seconds
            
        Returns:
            Dict with deletion result
        """
        try:
            # Check if service exists and is ready
            service_info = self.service_manager.get_service(service_id)
            if not service_info:
                return {
                    "success": False,
                    "error": f"Service {service_id} not found",
                    "message": "The requested vector DB service could not be found."
                }
            
            is_ready, status = self._check_service_ready(service_id, service_info)
            if not is_ready:
                return {
                    "success": False,
                    "error": f"Service is not ready yet (status: {status})",
                    "message": f"The vector DB service is still starting up (status: {status}).",
                    "service_id": service_id,
                    "status": status
                }
            
            endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_QDRANT_PORT)
            if not endpoint:
                return {
                    "success": False,
                    "error": "Service endpoint not available",
                    "message": "The vector DB service endpoint is not available yet.",
                    "service_id": service_id
                }
            
            # Make HTTP request via SSH
            ssh_manager = self.deployer.ssh_manager
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or DEFAULT_QDRANT_PORT
            
            success, status_code, body = ssh_manager.http_request_via_ssh(
                remote_host=remote_host,
                remote_port=remote_port,
                method="DELETE",
                path=f"/collections/{collection_name}",
                timeout=timeout
            )
            
            if not success or status_code not in [200, 204]:
                return {
                    "success": False,
                    "error": f"HTTP {status_code} from delete collection endpoint",
                    "message": f"Failed to delete collection (HTTP {status_code}). Collection may not exist.",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "collection_name": collection_name
                }
            
            return {
                "success": True,
                "message": f"Collection '{collection_name}' deleted successfully",
                "service_id": service_id,
                "endpoint": endpoint,
                "collection_name": collection_name
            }
            
        except Exception as e:
            self.logger.exception("Failed to delete collection %s in service %s", collection_name, service_id)
            return {
                "success": False,
                "error": f"Exception: {str(e)}",
                "message": "An error occurred while deleting the collection.",
                "service_id": service_id,
                "collection_name": collection_name
            }

    def upsert_points(self, service_id: str, collection_name: str, points: List[Dict[str, Any]], 
                     timeout: int = 30) -> Dict[str, Any]:
        """Insert or update points (vectors with payloads) in a collection.
        
        Args:
            service_id: The service ID
            collection_name: Name of the collection
            points: List of points, each with 'id', 'vector', and optional 'payload'
                   Example: [{"id": 1, "vector": [0.1, 0.2, ...], "payload": {"text": "..."}}]
            timeout: Request timeout in seconds
            
        Returns:
            Dict with upsert result
        """
        try:
            # Check if service exists and is ready
            service_info = self.service_manager.get_service(service_id)
            if not service_info:
                return {
                    "success": False,
                    "error": f"Service {service_id} not found",
                    "message": "The requested vector DB service could not be found."
                }
            
            is_ready, status = self._check_service_ready(service_id, service_info)
            if not is_ready:
                return {
                    "success": False,
                    "error": f"Service is not ready yet (status: {status})",
                    "message": f"The vector DB service is still starting up (status: {status}).",
                    "service_id": service_id,
                    "status": status
                }
            
            endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_QDRANT_PORT)
            if not endpoint:
                return {
                    "success": False,
                    "error": "Service endpoint not available",
                    "message": "The vector DB service endpoint is not available yet.",
                    "service_id": service_id
                }
            
            # Prepare request body
            request_body = {
                "points": points
            }
            
            # Make HTTP request via SSH
            ssh_manager = self.deployer.ssh_manager
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or DEFAULT_QDRANT_PORT
            
            success, status_code, body = ssh_manager.http_request_via_ssh(
                remote_host=remote_host,
                remote_port=remote_port,
                method="PUT",
                path=f"/collections/{collection_name}/points",
                json_data=request_body,
                timeout=timeout
            )
            
            if not success or status_code not in [200, 201]:
                return {
                    "success": False,
                    "error": f"HTTP {status_code} from upsert points endpoint",
                    "message": f"Failed to upsert points (HTTP {status_code}).",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "collection_name": collection_name
                }
            
            return {
                "success": True,
                "message": f"Upserted {len(points)} points to collection '{collection_name}'",
                "service_id": service_id,
                "endpoint": endpoint,
                "collection_name": collection_name,
                "num_points": len(points)
            }
            
        except Exception as e:
            self.logger.exception("Failed to upsert points in collection %s, service %s", collection_name, service_id)
            return {
                "success": False,
                "error": f"Exception: {str(e)}",
                "message": "An error occurred while upserting points.",
                "service_id": service_id,
                "collection_name": collection_name
            }

    def search_points(self, service_id: str, collection_name: str, query_vector: List[float], 
                     limit: int = 10, timeout: int = 10) -> Dict[str, Any]:
        """Search for similar vectors in a collection.
        
        Args:
            service_id: The service ID
            collection_name: Name of the collection
            query_vector: The query vector
            limit: Maximum number of results to return
            timeout: Request timeout in seconds
            
        Returns:
            Dict with search results
        """
        try:
            # Check if service exists and is ready
            service_info = self.service_manager.get_service(service_id)
            if not service_info:
                return {
                    "success": False,
                    "error": f"Service {service_id} not found",
                    "message": "The requested vector DB service could not be found.",
                    "results": []
                }
            
            is_ready, status = self._check_service_ready(service_id, service_info)
            if not is_ready:
                return {
                    "success": False,
                    "error": f"Service is not ready yet (status: {status})",
                    "message": f"The vector DB service is still starting up (status: {status}).",
                    "service_id": service_id,
                    "status": status,
                    "results": []
                }
            
            endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_QDRANT_PORT)
            if not endpoint:
                return {
                    "success": False,
                    "error": "Service endpoint not available",
                    "message": "The vector DB service endpoint is not available yet.",
                    "service_id": service_id,
                    "results": []
                }
            
            # Prepare request body
            request_body = {
                "vector": query_vector,
                "limit": limit,
                "with_payload": True,
                "with_vector": False
            }
            
            # Make HTTP request via SSH
            ssh_manager = self.deployer.ssh_manager
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or DEFAULT_QDRANT_PORT
            
            success, status_code, body = ssh_manager.http_request_via_ssh(
                remote_host=remote_host,
                remote_port=remote_port,
                method="POST",
                path=f"/collections/{collection_name}/points/search",
                json_data=request_body,
                timeout=timeout
            )
            
            if not success or status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP {status_code} from search endpoint",
                    "message": f"Failed to search points (HTTP {status_code}).",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "collection_name": collection_name,
                    "results": []
                }
            
            results = body.get("result", [])
            
            return {
                "success": True,
                "results": results,
                "service_id": service_id,
                "endpoint": endpoint,
                "collection_name": collection_name,
                "num_results": len(results)
            }
            
        except Exception as e:
            self.logger.exception("Failed to search points in collection %s, service %s", collection_name, service_id)
            return {
                "success": False,
                "error": f"Exception: {str(e)}",
                "message": "An error occurred while searching points.",
                "service_id": service_id,
                "collection_name": collection_name,
                "results": []
            }

    def get_metrics(self, service_id: str, timeout: int = 10) -> Dict[str, Any]:
        """Get Prometheus metrics from a Qdrant service.
        
        Qdrant exposes Prometheus-compatible metrics at the /metrics endpoint.
        This method retrieves those metrics and returns them in Prometheus text format.
        
        Args:
            service_id: The service ID
            timeout: Request timeout in seconds
            
        Returns:
            Dict with either:
            - {"success": True, "metrics": "prometheus text format", "service_id": ..., "endpoint": ...}
            - {"success": False, "error": "...", "message": "...", "metrics": ""}
        """
        try:
            # Check if service exists and is ready
            service_info = self.service_manager.get_service(service_id)
            if not service_info:
                return {
                    "success": False,
                    "error": f"Service {service_id} not found",
                    "message": "The requested Qdrant service could not be found.",
                    "service_id": service_id,
                    "metrics": ""
                }
            
            is_ready, status = self._check_service_ready(service_id, service_info)
            if not is_ready:
                return {
                    "success": False,
                    "error": f"Service is not ready yet (status: {status})",
                    "message": f"The Qdrant service is still starting up (status: {status}). Please wait a moment and try again.",
                    "service_id": service_id,
                    "status": status,
                    "metrics": ""
                }
            
            endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_QDRANT_PORT)
            if not endpoint:
                self.logger.debug("No endpoint found for service %s when querying metrics", service_id)
                return {
                    "success": False,
                    "error": "Service endpoint not available",
                    "message": "The Qdrant service endpoint is not available yet.",
                    "service_id": service_id,
                    "status": status,
                    "metrics": ""
                }
            
            # Parse endpoint URL and use SSH tunneling to reach compute node
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or DEFAULT_QDRANT_PORT
            path = "/metrics"
            
            self.logger.debug("Querying metrics via SSH: %s:%s%s", remote_host, remote_port, path)
            
            # Use SSH to make the HTTP request (tunnels through login node to compute node)
            ssh_manager = self.deployer.ssh_manager
            success, status_code, body = ssh_manager.http_request_via_ssh(
                remote_host=remote_host,
                remote_port=remote_port,
                method="GET",
                path=path,
                timeout=timeout
            )
            
            if not success or not (200 <= status_code < 300):
                self.logger.warning("Metrics query for %s returned %s: %s", service_id, status_code, body[:200])
                return {
                    "success": False,
                    "error": f"HTTP {status_code} from metrics endpoint",
                    "message": f"Failed to query metrics from Qdrant service (HTTP {status_code}).",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "status": status_code,
                    "metrics": ""
                }
            
            self.logger.debug("Metrics retrieved successfully for service %s (%d bytes)", service_id, len(body))
            
            return {
                "success": True,
                "metrics": body,
                "service_id": service_id,
                "endpoint": endpoint
            }
            
        except Exception as e:
            self.logger.exception("Failed to get metrics for service %s", service_id)
            return {
                "success": False,
                "error": f"Exception during metrics retrieval: {str(e)}",
                "message": "An error occurred while querying the Qdrant service for metrics.",
                "service_id": service_id,
                "metrics": ""
            }
