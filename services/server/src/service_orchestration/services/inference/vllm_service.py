"""vLLM-specific inference service implementation."""

from typing import Dict, List, Optional, Any, Tuple
import requests
import time
import json
from .inference_service import InferenceService
from service_orchestration.networking import LoadBalancer

DEFAULT_VLLM_PORT = 8001
BASE_TIMEOUT = 30  # Base timeout for single-node setups
TIMEOUT_PER_EXTRA_NODE = 30  # Additional timeout per extra node beyond first


class VllmService(InferenceService):
    """Handles all vLLM-specific inference operations."""
    
    def __init__(self, deployer, service_manager, endpoint_resolver, logger):
        """Initialize VllmService with load balancer support and model caching."""
        super().__init__(deployer, service_manager, endpoint_resolver, logger)
        self.load_balancer = LoadBalancer()
        
        # Model name cache: {service_id: {"model": str, "endpoint": str, "timestamp": float}}
        self._model_cache: Dict[str, Dict[str, Any]] = {}
        self._model_cache_ttl = 3600  # Cache for 1 hour (models don't change during service lifetime)
    
    def _get_cached_model(self, service_id: str, endpoint: str) -> Optional[str]:
        """Get cached model name if available and fresh.
        
        Args:
            service_id: The service ID
            endpoint: The current endpoint (must match cached endpoint)
            
        Returns:
            Cached model name or None
        """
        if service_id in self._model_cache:
            cache_entry = self._model_cache[service_id]
            age = time.time() - cache_entry["timestamp"]
            
            # Verify cache is fresh and endpoint matches
            if age < self._model_cache_ttl and cache_entry["endpoint"] == endpoint:
                self.logger.debug(f"Model cache HIT for {service_id}: {cache_entry['model']} (age: {age:.1f}s)")
                return cache_entry["model"]
            else:
                self.logger.debug(f"Model cache STALE for {service_id} (age: {age:.1f}s or endpoint mismatch)")
        
        return None
    
    def _cache_model(self, service_id: str, endpoint: str, model: str):
        """Cache the model name for a service.
        
        Args:
            service_id: The service ID
            endpoint: The endpoint URL
            model: The model name to cache
        """
        self._model_cache[service_id] = {
            "model": model,
            "endpoint": endpoint,
            "timestamp": time.time()
        }
        self.logger.debug(f"Model cached for {service_id}: {model}")

    def find_services(self) -> List[Dict[str, Any]]:
        """Find running VLLM services and their endpoints."""
        def is_vllm(service):
            service_name = service.get("name", "").lower()
            recipe_name = service.get("recipe_name", "").lower()
            return (
                "vllm" in service_name or 
                "vllm" in recipe_name or
                any("vllm" in str(val).lower() for val in service.values() if isinstance(val, str))
            )
        
        services = self._filter_services(is_vllm)
        self.logger.debug(f"Found {len(services)} vLLM services after filtering")
        vllm_services = []
        
        for service in services:
            job_id = service.get("id")
            endpoint = self.endpoint_resolver.resolve(job_id, default_port=DEFAULT_VLLM_PORT)
            if endpoint:
                self.logger.debug("Resolved endpoint for vllm job %s -> %s", job_id, endpoint)
            else:
                self.logger.debug("No endpoint yet for vllm job %s (status: %s)", job_id, service.get("status"))
            
            # Get detailed service-specific status instead of basic SLURM status
            try:
                is_ready, status, _ = self._check_ready_and_discover_model(job_id, service)
            except Exception as e:
                self.logger.warning(f"Failed to check readiness for service {job_id}: {e}")
                status = service.get("status", "unknown")
            
            vllm_services.append({
                "id": job_id,
                "name": service.get("name"),
                "recipe_name": service.get("recipe_name", "unknown"),
                "endpoint": endpoint,
                "status": status  
            })
        
        return vllm_services


    def get_models(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Query a running VLLM service for available models.

        Returns a dict with either:
        - {"success": True, "models": [list of model ids]}
        - {"success": False, "error": "...", "message": "...", ...}
        """
        try:
            # Check if service exists and is ready
            service_info = self.service_manager.get_service(service_id)
            if not service_info:
                return {
                    "success": False,
                    "error": f"Service {service_id} not found",
                    "message": "The requested vLLM service could not be found.",
                    "models": []
                }
            
            is_ready, status, _ = self._check_ready_and_discover_model(service_id, service_info)
            if not is_ready:
                return {
                    "success": False,
                    "error": f"Service is not ready yet (status: {status})",
                    "message": f"The vLLM service is still starting up (status: {status}). Please wait a moment and try again.",
                    "service_id": service_id,
                    "status": status,
                    "models": []
                }
            
            endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_VLLM_PORT)
            if not endpoint:
                self.logger.debug("No endpoint found for service %s when querying models", service_id)
                return {
                    "success": False,
                    "error": "Service endpoint not available",
                    "message": "The vLLM service endpoint is not available yet.",
                    "service_id": service_id,
                    "status": status,
                    "models": []
                }

            # Parse endpoint URL and make direct HTTP request to compute node
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or 8001
            path = "/v1/models"
            
            self.logger.debug("Querying models: %s:%s%s", remote_host, remote_port, path)
            
            # Direct HTTP request to compute node
            try:
                response = requests.get(
                    f"http://{remote_host}:{remote_port}{path}",
                    timeout=timeout
                )
            except Exception as e:
                self.logger.warning("Model discovery for %s failed: %s", service_id, str(e))
                return {
                    "success": False,
                    "error": f"Connection failed: {str(e)}",
                    "message": "Failed to connect to vLLM service for model discovery.",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "models": []
                }
            
            if not response.ok:
                self.logger.warning("Model discovery for %s returned %s: %s", service_id, response.status_code, response.text)
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code} from models endpoint",
                    "message": f"Failed to query models from vLLM service (HTTP {response.status_code}).",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "models": []
                }

            self.logger.debug("Model discovery response for %s: %s", service_id, response.text)

            data = response.json()
            models = []
            
            # vLLM returns {"object": "list", "data": [...]}
            if isinstance(body, dict):
                # Try standard OpenAI format (data field)
                candidates = body.get('data', [])
                # Fallback to other possible formats
                if not candidates:
                    candidates = body.get('models') or body.get('served_models') or []
                
                if isinstance(candidates, list):
                    for item in candidates:
                        if isinstance(item, str):
                            models.append(item)
                        elif isinstance(item, dict):
                            model_id = item.get('id') or item.get('model')
                            if model_id:
                                models.append(model_id)
            elif isinstance(body, list):
                # Direct list format
                for item in body:
                    if isinstance(item, str):
                        models.append(item)
                    elif isinstance(item, dict):
                        model_id = item.get('id') or item.get('model')
                        if model_id:
                            models.append(model_id)

            return {
                "success": True,
                "models": models,
                "service_id": service_id,
                "endpoint": endpoint
            }
        except Exception as e:
            self.logger.exception("Failed to discover models for service %s", service_id)
            return {
                "success": False,
                "error": f"Exception during model discovery: {str(e)}",
                "message": "An error occurred while querying the vLLM service for models.",
                "service_id": service_id,
                "models": []
            }

    
    def _check_ready_and_discover_model(self, service_id: str, service_info: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """Check if a vLLM service is ready AND discover its model name in ONE HTTP call.
        
        This combines readiness checking with model discovery to eliminate duplicate
        HTTP requests to the /v1/models endpoint, reducing latency by ~2 seconds.
        
        Uses a hybrid approach:
        1. For replicas (composite IDs), skip SLURM check and test HTTP directly
        2. For regular services, check SLURM status first (fast, eliminates pending/building jobs)
        3. For RUNNING jobs, test HTTP connection to /v1/models endpoint AND parse model list
        
        Args:
            service_id: The service ID to check (may be composite like "job_id:port")
            service_info: The service information dict
            
        Returns:
            Tuple of (is_ready: bool, status: str, model: Optional[str])
            - is_ready: True if service is ready for prompts
            - status: Current service status ("running", "starting", etc.)
            - model: First model name from /v1/models, or None if not available
        """
        # For composite replica IDs (e.g., "3713478:8001"), skip SLURM check
        # The SLURM job may be "completed" while replicas continue running as background processes
        if ":" in service_id:
            # Replicas: test HTTP connection directly without checking SLURM status
            self.logger.debug(f"Checking replica {service_id} via direct HTTP test (skipping SLURM status)")
            basic_status = "running"  # Assume running and let HTTP test determine actual state
        else:
            # Regular services: Get the current LIVE status from SLURM
            try:
                basic_status = self.deployer.get_job_status(service_id).lower()
            except Exception as e:
                self.logger.warning(f"Failed to get status for service {service_id}: {e}")
                basic_status = service_info.get("status", "unknown").lower()
        
        # If not running yet, return basic status (no need to test connection)
        if basic_status != "running":
            is_ready = basic_status not in ["pending", "building", "starting"]
            return is_ready, basic_status, None
        
        # For RUNNING jobs, test actual HTTP connection to confirm vLLM is ready
        # This replaces log parsing with a definitive connection test
        endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_VLLM_PORT)
        if not endpoint:
            # Job is running but endpoint not available yet
            self.logger.info(f"Service {service_id} is RUNNING but endpoint not resolved yet")
            return False, "starting", None
        
        # Try lightweight HTTP GET to /v1/models with short timeout
        # This SINGLE call both checks readiness AND discovers the model
        try:
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            remote_host = parsed.hostname
            remote_port = parsed.port or 8001
            path = "/v1/models"
            
            self.logger.info(f"Testing readiness + discovering model via {remote_host}:{remote_port}{path}")
            
            # Direct HTTP request to compute node (orchestrator runs on MeluXina)
            try:
                response = requests.get(
                    f"http://{remote_host}:{remote_port}{path}",
                    timeout=8
                )
                status_code = response.status_code
                body = response.text
            except Exception as e:
                self.logger.info(f"Direct HTTP request to {remote_host}:{remote_port} failed: {e}")
                return False, "starting", None
            
            # Connection succeeded and got valid HTTP response
            if status_code >= 200 and status_code < 300:
                self.logger.info(f"Service {service_id} is ready (HTTP {status_code})")
                
                # Parse model list from response
                model = None
                try:
                    # vLLM returns {"object": "list", "data": [...]}
                    if isinstance(data, dict):
                        candidates = data.get('data', [])
                        if isinstance(candidates, list) and candidates:
                            # Extract first model ID
                            first_item = candidates[0]
                            if isinstance(first_item, dict):
                                model = first_item.get('id')
                            elif isinstance(first_item, str):
                                model = first_item
                    
                    if model:
                        self.logger.debug(f"Discovered model for {service_id}: {model}")
                        # Cache the model for future use
                        self._cache_model(service_id, endpoint, model)
                    else:
                        self.logger.debug(f"Could not extract model from /v1/models response for {service_id}")
                        
                except Exception as e:
                    self.logger.debug(f"Failed to parse models from response for {service_id}: {e}")
                
                return True, "running", model
            else:
                # Connected but got error response - likely still initializing
                self.logger.debug(f"Service {service_id} on {remote_host}:{remote_port} returned HTTP {status_code}")
                return False, "starting", None
                
        except Exception as e:
            # Connection failed - service not ready yet
            self.logger.debug(f"Service {service_id} connection test to {remote_host}:{remote_port} failed: {e}")
            return False, "starting", None

    def prompt(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a running VLLM service or service group.
        
        For service groups: Uses round-robin load balancing to route to healthy replicas.
        For single services: Routes directly.
        
        Tries chat endpoint first (for instruction-tuned models).
        Falls back to completions endpoint if chat template error occurs (for base models).
        
        Optimized: Skips expensive status checks for services that were recently used successfully.
        """
        # Check if this is a service group
        if self.service_manager.is_group(service_id):
            return self._prompt_service_group(service_id, prompt, **kwargs)
        
        # Single service flow (existing logic)
        return self._prompt_single_service(service_id, prompt, **kwargs)
    
    def _prompt_service_group(self, group_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a service group using load balancing with automatic failover.
        
        Strategy: Try replicas in round-robin order. Mark replica unhealthy only if it fails.
        This allows replicas to be used as soon as they're allocated (regardless of status tracking).
        """
        # Get group info
        group_info = self.service_manager.get_group_info(group_id)
        if not group_info:
            return {
                "success": False,
                "error": f"Service group {group_id} not found",
                "message": "The requested service group could not be found.",
                "service_id": group_id
            }
        
        # Get all replicas (regardless of status) - must use flattened list
        all_replicas = self.service_manager.group_manager.get_all_replicas_flat(group_id)
        if not all_replicas:
            return {
                "success": False,
                "error": "Service group has no replicas",
                "message": "The service group exists but has no replicas.",
                "service_id": group_id
            }
        
        # Try replicas in round-robin order
        # The load balancer will cycle through regardless of health status
        attempted_replicas = []
        
        for attempt in range(len(all_replicas)):
            # Get next replica based on round-robin
            selected_replica = self.load_balancer.select_replica(group_id, all_replicas)
            if not selected_replica:
                return {
                    "success": False,
                    "error": "Load balancer failed to select replica",
                    "message": "Internal error: load balancer could not select a replica.",
                    "service_id": group_id
                }
            
            replica_id = selected_replica["id"]
            self.logger.info(f"Routing prompt for group {group_id} to replica {replica_id} (attempt {attempt + 1}/{len(all_replicas)})")
            attempted_replicas.append(replica_id)
            
            # Try to send prompt to this replica
            result = self._prompt_single_service(replica_id, prompt, **kwargs)
            
            if result.get("success"):
                # Success! Mark replica as healthy and return
                self.service_manager.update_replica_status(replica_id, "running")
                result["routed_to"] = replica_id
                result["group_id"] = group_id
                self.logger.info(f"Successfully routed to replica {replica_id}")
                return result
            else:
                # This replica failed - mark it unhealthy and try next one
                self.logger.warning(f"Replica {replica_id} failed: {result.get('error')}. Trying next replica...")
                self.service_manager.update_replica_status(replica_id, "failed")
                
                # If this is not the last attempt, continue to next replica
                if attempt < len(all_replicas) - 1:
                    continue
        
        # All replicas failed
        return {
            "success": False,
            "error": "All replicas failed",
            "message": f"Could not route prompt to any of the {len(all_replicas)} replicas.",
            "service_id": group_id,
            "num_replicas": len(all_replicas),
            "attempted_replicas": attempted_replicas,
            "replica_statuses": {r["id"]: r["status"] for r in all_replicas}
        }
    
    def _prompt_single_service(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a single VLLM service (not a group).
        
        Tries chat endpoint first (for instruction-tuned models).
        Falls back to completions endpoint if chat template error occurs (for base models).
        
        Optimized with model caching and combined readiness+discovery check.
        """
        # Try to get service info directly (works for just-created services too)
        service_info = self.service_manager.get_service(service_id)
        if not service_info:
            # Service doesn't exist at all
            return {
                "success": False,
                "error": f"VLLM service {service_id} not found",
                "message": "The requested vLLM service could not be found. It may not exist or may have been stopped.",
                "service_id": service_id
            }
        
        # Check if it's a VLLM service
        if "inference/vllm" not in service_info.get("recipe_name", ""):
            return {
                "success": False,
                "error": f"Service {service_id} is not a vLLM service",
                "message": f"The requested service is a {service_info.get('recipe_name')} service, not a vLLM service.",
                "service_id": service_id
            }
        
        # Try to get the endpoint early
        endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_VLLM_PORT)
        if not endpoint:
            return {
                "success": False,
                "error": "Service endpoint not available",
                "message": "The vLLM service endpoint is not available yet. The service may still be initializing.",
                "service_id": service_id,
                "status": "starting"
            }
        
        # FAST PATH: Skip expensive checks if service was recently used successfully (within 5 minutes)
        skip_readiness_check = self.service_manager.is_service_recently_healthy(service_id, max_age_seconds=300)
        discovered_model = None
        
        if skip_readiness_check:
            self.logger.debug(f"Fast path: Skipping readiness check for recently-used service {service_id}")
            status = "running"  # Assume it's still running
            # Try to get cached model (saves ~2s!)
            discovered_model = self._get_cached_model(service_id, endpoint)
        else:
            # SLOW PATH: Do combined readiness check + model discovery (saves ~2s vs separate calls!)
            is_ready, status, discovered_model = self._check_ready_and_discover_model(service_id, service_info)
            if not is_ready:
                return {
                    "success": False,
                    "error": f"Service is not ready yet (status: {status})",
                    "message": "The vLLM service is still starting up. Please wait a moment and try again.",
                    "service_id": service_id,
                    "status": status
                }
        
        # Get model name and remove it from kwargs to avoid duplicate argument
        model = kwargs.pop("model", None)
        
        # Use discovered/cached model if no explicit model provided
        if not model:
            if discovered_model:
                # Use the model we discovered during readiness check or from cache
                model = discovered_model
                self.logger.debug(f"Using discovered/cached model for {service_id}: {model}")
            else:
                # Fallback: query models endpoint (only if we don't have a cached model)
                self.logger.debug(f"No cached model for {service_id}, querying /v1/models")
                models_result = self.get_models(service_id)
                if models_result.get("success") and models_result.get("models"):
                    model = models_result["models"][0]
                    # Cache it for next time
                    self._cache_model(service_id, endpoint, model)
                else:
                    model = None

        self.logger.debug("Preparing prompt for service %s at %s with model %s", service_id, endpoint, model)
        
        try:
            # Try chat endpoint first (works for instruction-tuned models)
            ok, status_code, body = self._try_chat_endpoint(endpoint, model, prompt, service_id=service_id, **kwargs)
            
            # Check if we got a chat template error
            if self._is_chat_template_error(ok, status_code, body):
                self.logger.info("Chat template error detected, retrying with completions endpoint")
                
                # Retry with completions endpoint (works for base models)
                ok, status_code, body = self._try_completions_endpoint(endpoint, model, prompt, service_id=service_id, **kwargs)
                result = self._parse_completions_response(ok, status_code, body, endpoint, service_id)
            else:
                # No chat template error - parse as chat response
                result = self._parse_chat_response(ok, status_code, body, endpoint, service_id)
            
            # Mark service as healthy on successful response
            if result.get("success"):
                self.service_manager.mark_service_healthy(service_id)
            else:
                # Invalidate health on error response
                self.service_manager.invalidate_service_health(service_id)
            
            return result
                
        except requests.exceptions.RequestException as e:
            error_str = str(e)
            
            # Invalidate health status on any request exception
            self.service_manager.invalidate_service_health(service_id)
            
            # Check if it's a connection error (service not ready)
            if "Connection refused" in error_str or "NewConnectionError" in error_str:
                # Double-check current status
                current_status = self.deployer.get_job_status(service_id)
                return {
                    "success": False,
                    "error": "Service not available",
                    "message": f"Cannot connect to vLLM service. The service may still be starting up (status: {current_status}). Please wait and try again.",
                    "service_id": service_id,
                    "status": current_status,
                    "endpoint": endpoint,
                    "technical_details": error_str
                }
            
            # Other network errors
            return {
                "success": False,
                "error": f"Failed to connect to VLLM service: {error_str}",
                "endpoint": endpoint
            }
        except Exception as e:
            # Invalidate health status on any exception
            self.service_manager.invalidate_service_health(service_id)
            
            self.logger.exception("Error in prompt")
            return {
                "success": False,
                "error": f"Error processing request: {str(e)}"
            }

    def _calculate_timeout(self, service_id: str) -> int:
        """Calculate appropriate timeout based on number of nodes in service.
        
        Multi-node tensor parallelism requires more time for NCCL communication
        and coordination. Formula: BASE_TIMEOUT + (num_nodes - 1) * TIMEOUT_PER_EXTRA_NODE
        
        Args:
            service_id: The service ID to check node count for
            
        Returns:
            Timeout in seconds
        """
        try:
            service_info = self.service_manager.get_service(service_id)
            if service_info:
                node_count = service_info.get("node_count", 1)
                if node_count > 1:
                    timeout = BASE_TIMEOUT + (node_count - 1) * TIMEOUT_PER_EXTRA_NODE
                    self.logger.debug(f"Using extended timeout {timeout}s for {node_count}-node service {service_id}")
                    return timeout
        except Exception as e:
            self.logger.warning(f"Failed to get node count for service {service_id}: {e}")
        
        # Default to base timeout
        return BASE_TIMEOUT

    def _try_chat_endpoint(self, endpoint: str, model: str, prompt: str, service_id: str = None, **kwargs) -> requests.Response:
        """Try to send prompt using chat completions endpoint."""
        # Parse endpoint URL (e.g., "http://mel2079:8001")
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        remote_host = parsed.hostname
        remote_port = parsed.port or 8001
        path = "/v1/chat/completions"
        
        request_data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", 500),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False
        }
        
        # Calculate timeout based on node count
        timeout = self._calculate_timeout(service_id) if service_id else BASE_TIMEOUT
        
        self.logger.debug("Trying chat endpoint: http://%s:%s%s (timeout=%ds)", remote_host, remote_port, path, timeout)
        
        # Direct HTTP request to compute node
        response = requests.post(
            f"http://{remote_host}:{remote_port}{path}",
            json=request_data,
            timeout=timeout
        )
        
        return response

    def _try_completions_endpoint(self, endpoint: str, model: str, prompt: str, service_id: str = None, **kwargs) -> requests.Response:
        """Try to send prompt using completions endpoint (for base models)."""
        # Parse endpoint URL (e.g., "http://mel2079:8001")
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        remote_host = parsed.hostname
        remote_port = parsed.port or 8001
        path = "/v1/completions"
        
        request_data = {
            "model": model,
            "prompt": prompt,
            "max_tokens": kwargs.get("max_tokens", 500),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False
        }
        
        # Calculate timeout based on node count
        timeout = self._calculate_timeout(service_id) if service_id else BASE_TIMEOUT
        
        self.logger.debug("Trying completions endpoint: http://%s:%s%s (timeout=%ds)", remote_host, remote_port, path, timeout)
        
        # Direct HTTP request to compute node
        response = requests.post(
            f"http://{remote_host}:{remote_port}{path}",
            json=request_data,
            timeout=timeout
        )
        
        return response

    def _is_chat_template_error(self, ok: bool, status_code: int, body: Any) -> bool:
        """Check if response indicates a chat template error."""
        if ok or status_code != 400:
            return False
        
        try:
            if not isinstance(body, dict):
                return False
            
            # Check both direct detail field and nested error.message field
            error_text = str(body.get("detail", ""))
            if "error" in body and isinstance(body["error"], dict):
                error_text += " " + str(body["error"].get("message", ""))
            
            return "chat template" in error_text.lower()
        except Exception:
            return False

    def _parse_chat_response(self, ok: bool, status_code: int, body: Any, endpoint: str, service_id: str) -> Dict[str, Any]:
        """Parse response from chat completions endpoint."""
        if not ok:
            return {
                "success": False,
                "error": f"vLLM returned {status_code}",
                "endpoint": endpoint,
                "status_code": status_code,
                "body": body
            }
        
        if "choices" in body and len(body["choices"]) > 0:
            content = body["choices"][0]["message"]["content"]
            return {
                "success": True,
                "response": content,
                "service_id": service_id,
                "endpoint": endpoint,
                "endpoint_used": "chat",
                "usage": body.get("usage", {})
            }
        
        return {
            "success": False,
            "error": "No response generated",
            "raw_response": body,
            "endpoint": endpoint
        }

    def _parse_completions_response(self, ok: bool, status_code: int, body: Any, endpoint: str, service_id: str) -> Dict[str, Any]:
        """Parse response from completions endpoint."""
        if not ok:
            return {
                "success": False,
                "error": f"vLLM completions returned {status_code}",
                "endpoint": endpoint,
                "status_code": status_code,
                "body": body
            }
        
        if "choices" in body and len(body["choices"]) > 0:
            content = body["choices"][0]["text"]
            return {
                "success": True,
                "response": content,
                "service_id": service_id,
                "endpoint": endpoint,
                "endpoint_used": "completions",
                "usage": body.get("usage", {})
            }
        
        return {
            "success": False,
            "error": "No response generated from completions endpoint",
            "raw_response": body,
            "endpoint": endpoint
        }

