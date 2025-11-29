"""vLLM-specific inference service implementation."""

from typing import Dict, List, Optional, Any, Tuple
import requests
import time
from .inference_service import InferenceService
from service_orchestration.networking import LoadBalancer

DEFAULT_VLLM_PORT = 8001
BASE_TIMEOUT = 30  # Base timeout for single-node setups
TIMEOUT_PER_EXTRA_NODE = 30  # Additional timeout per extra node beyond first


class VllmService(InferenceService):
    """Handles all vLLM-specific inference operations.
    
    Features:
    - Model name caching to avoid redundant /v1/models calls
    - Load balancing for service groups (replica groups)
    - Chat/completions endpoint fallback for base models
    - RAG-augmented prompting support
    
    Uses BaseService helpers for HTTP requests and response formatting.
    """
    
    def __init__(self, deployer, service_manager, endpoint_resolver, logger):
        """Initialize VllmService with load balancer support and model caching."""
        super().__init__(deployer, service_manager, endpoint_resolver, logger)
        self.load_balancer = LoadBalancer()
        
        # Model name cache: {service_id: {"model": str, "endpoint": str, "timestamp": float}}
        self._model_cache: Dict[str, Dict[str, Any]] = {}
        self._model_cache_ttl = 3600  # Cache for 1 hour

    # ========== BaseService Abstract Properties ==========
    
    @property
    def default_port(self) -> int:
        return DEFAULT_VLLM_PORT
    
    @property
    def service_type_name(self) -> str:
        return "vLLM"

    # ========== Model Caching ==========

    def _get_cached_model(self, service_id: str, endpoint: str) -> Optional[str]:
        """Get cached model name if available and fresh."""
        if service_id in self._model_cache:
            cache_entry = self._model_cache[service_id]
            age = time.time() - cache_entry["timestamp"]
            if age < self._model_cache_ttl and cache_entry["endpoint"] == endpoint:
                self.logger.debug(f"Model cache HIT for {service_id}: {cache_entry['model']} (age: {age:.1f}s)")
                return cache_entry["model"]
            else:
                self.logger.debug(f"Model cache STALE for {service_id}")
        return None
    
    def _cache_model(self, service_id: str, endpoint: str, model: str):
        """Cache the model name for a service."""
        self._model_cache[service_id] = {
            "model": model,
            "endpoint": endpoint,
            "timestamp": time.time()
        }
        self.logger.debug(f"Model cached for {service_id}: {model}")

    # ========== Service Discovery ==========

    def find_services(self) -> List[Dict[str, Any]]:
        """Find running vLLM services and their endpoints."""
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
            endpoint_parts = self._resolve_endpoint_parts(job_id)
            endpoint = f"http://{endpoint_parts[0]}:{endpoint_parts[1]}" if endpoint_parts else None
            
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

    # ========== Readiness Check with Model Discovery ==========

    def _check_service_ready(self, service_id: str, service_info: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if service is ready (simplified, without model discovery)."""
        is_ready, status, _ = self._check_ready_and_discover_model(service_id, service_info)
        return is_ready, status

    def _check_ready_and_discover_model(self, service_id: str, service_info: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """Check if vLLM service is ready AND discover model in ONE HTTP call.
        
        This optimized method combines readiness checking with model discovery
        to eliminate redundant HTTP requests, reducing latency by ~2 seconds.
        """
        # For composite replica IDs, skip SLURM check
        if ":" in service_id:
            self.logger.debug(f"Checking replica {service_id} via direct HTTP test")
            basic_status = "running"
        else:
            try:
                basic_status = self.deployer.get_job_status(service_id).lower()
            except Exception as e:
                self.logger.warning(f"Failed to get status for service {service_id}: {e}")
                basic_status = service_info.get("status", "unknown").lower()
        
        if basic_status != "running":
            is_ready = basic_status not in ["pending", "building", "starting"]
            return is_ready, basic_status, None
        
        # Test HTTP connection to /v1/models
        endpoint_parts = self._resolve_endpoint_parts(service_id)
        if not endpoint_parts:
            self.logger.info(f"Service {service_id} is RUNNING but endpoint not resolved yet")
            return False, "starting", None
        
        hostname, port = endpoint_parts
        endpoint = f"http://{hostname}:{port}"
        
        try:
            self.logger.info(f"Testing readiness + discovering model via {hostname}:{port}/v1/models")
            response = requests.get(f"http://{hostname}:{port}/v1/models", timeout=8)
            
            if 200 <= response.status_code < 300:
                self.logger.info(f"Service {service_id} is ready (HTTP {response.status_code})")
                
                # Parse model from response
                model = None
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        candidates = data.get('data', [])
                        if isinstance(candidates, list) and candidates:
                            first_item = candidates[0]
                            model = first_item.get('id') if isinstance(first_item, dict) else first_item
                    
                    if model:
                        self._cache_model(service_id, endpoint, model)
                except Exception as e:
                    self.logger.debug(f"Failed to parse models from response: {e}")
                
                return True, "running", model
            else:
                self.logger.debug(f"Service {service_id} returned HTTP {response.status_code}")
                return False, "starting", None
                
        except Exception as e:
            self.logger.debug(f"Service {service_id} connection test failed: {e}")
            return False, "starting", None

    # ========== InferenceService Abstract Methods ==========

    def get_models(self, service_id: str, timeout: int = 5) -> Dict[str, Any]:
        """Query a running vLLM service for available models."""
        exists, service_info, error = self._validate_service_exists(service_id)
        if not exists:
            error["models"] = []
            return error
        
        is_ready, status, discovered_model = self._check_ready_and_discover_model(service_id, service_info)
        if not is_ready:
            return self._error_response(
                error=f"Service is not ready yet (status: {status})",
                message=f"The vLLM service is still starting up (status: {status}). Please wait.",
                service_id=service_id, status=status, models=[]
            )
        
        result = self._make_request(service_id, "/v1/models", timeout=timeout)
        if not result["success"]:
            result["models"] = []
            return result
        
        # Parse vLLM response format: {"object": "list", "data": [...]}
        data = result.get("data", {})
        models = []
        candidates = data.get('data', []) or data.get('models', []) or data.get('served_models', [])
        
        for item in candidates:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict):
                model_id = item.get('id') or item.get('model')
                if model_id:
                    models.append(model_id)
        
        return self._success_response(
            models=models,
            service_id=service_id,
            endpoint=result.get("endpoint")
        )

    def prompt(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a running vLLM service or service group.
        
        For service groups: Uses round-robin load balancing to route to healthy replicas.
        For single services: Routes directly.
        
        Tries chat endpoint first, falls back to completions for base models.
        """
        if self.service_manager.is_group(service_id):
            return self._prompt_service_group(service_id, prompt, **kwargs)
        return self._prompt_single_service(service_id, prompt, **kwargs)

    def rag_prompt(self, service_id: str, prompt: str, qdrant_service, 
                   qdrant_service_id: str, collection_name: str, 
                   top_k: int = 3, **kwargs) -> Dict[str, Any]:
        """Send a RAG-augmented prompt to a vLLM service.
        
        This method:
        1. Searches the Qdrant collection for relevant context using text similarity
        2. Augments the original prompt with retrieved context
        3. Sends the augmented prompt to the vLLM service
        
        Args:
            service_id: The vLLM service ID to send the prompt to
            prompt: The original user prompt/question
            qdrant_service: The QdrantService instance to use for retrieval
            qdrant_service_id: The Qdrant service ID to search
            collection_name: The collection name to search in
            top_k: Number of context chunks to retrieve (default: 3)
            **kwargs: Additional parameters for vLLM (max_tokens, temperature, etc.)
            
        Returns:
            Dict with:
            - On success: {"success": True, "response": "...", "rag_context": [...], ...}
            - On failure: {"success": False, "error": "...", ...}
        """
        self.logger.info(f"RAG prompt for service {service_id}, collection {collection_name}, top_k={top_k}")
        
        # Step 1: Retrieve relevant context from Qdrant
        try:
            search_result = qdrant_service.search_with_text(
                service_id=qdrant_service_id,
                collection_name=collection_name,
                query_text=prompt,
                limit=top_k
            )
            
            if not search_result.get("success"):
                # Qdrant search failed - decide whether to proceed without context or fail
                self.logger.warning(f"RAG context retrieval failed: {search_result.get('error')}")
                # Proceed without RAG context (graceful degradation)
                return self._prompt_without_rag(service_id, prompt, search_result, **kwargs)
            
            # Extract context from search results
            retrieved_contexts = []
            for result in search_result.get("results", []):
                payload = result.get("payload", {})
                # Common payload fields: 'text', 'content', 'chunk', 'document'
                text = payload.get("text") or payload.get("content") or payload.get("chunk") or payload.get("document")
                if text:
                    retrieved_contexts.append({
                        "text": text,
                        "score": result.get("score", 0),
                        "id": result.get("id")
                    })
            
            self.logger.debug(f"Retrieved {len(retrieved_contexts)} context chunks")
            
        except Exception as e:
            self.logger.exception(f"Error during RAG context retrieval: {e}")
            # Proceed without RAG context (graceful degradation)
            return self._prompt_without_rag(service_id, prompt, {"error": str(e)}, **kwargs)
        
        # Step 2: Format augmented prompt
        augmented_prompt = self._format_rag_prompt(prompt, retrieved_contexts)
        self.logger.debug(f"Augmented prompt length: {len(augmented_prompt)} chars")
        
        # Step 3: Send augmented prompt to vLLM
        result = self.prompt(service_id, augmented_prompt, **kwargs)
        
        # Add RAG metadata to result
        result["rag_enabled"] = True
        result["rag_context"] = retrieved_contexts
        result["rag_collection"] = collection_name
        result["original_prompt"] = prompt
        
        return result

    def _format_rag_prompt(self, question: str, contexts: List[Dict[str, Any]]) -> str:
        """Format the RAG-augmented prompt with retrieved context.
        
        Uses a simple but effective template that works well with most LLMs.
        
        Args:
            question: The original user question
            contexts: List of context dicts with 'text' and 'score' fields
            
        Returns:
            Formatted prompt string with context prepended
        """
        if not contexts:
            return question
        
        # Build context section
        context_parts = []
        for i, ctx in enumerate(contexts, 1):
            text = ctx.get("text", "").strip()
            if text:
                context_parts.append(f"[{i}] {text}")
        
        if not context_parts:
            return question
        
        context_section = "\n\n".join(context_parts)
        
        # Format the augmented prompt
        augmented_prompt = f"""Use the following context to answer the question. If the context doesn't contain relevant information, say so and answer based on your knowledge.

Context:
{context_section}

Question: {question}

Answer:"""
        
        return augmented_prompt

    def _prompt_without_rag(self, service_id: str, prompt: str, 
                            retrieval_error: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Send prompt without RAG augmentation when retrieval fails.
        
        This provides graceful degradation - the prompt still works,
        just without the context augmentation.
        """
        self.logger.info(f"Proceeding without RAG context due to retrieval failure")
        
        result = self.prompt(service_id, prompt, **kwargs)
        
        # Add metadata about the failed RAG attempt
        result["rag_enabled"] = False
        result["rag_context"] = []
        result["rag_error"] = retrieval_error.get("error", "Unknown retrieval error")
        result["original_prompt"] = prompt
        
        return result
    
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
        all_replicas = self.service_manager.get_all_replicas_flat(group_id)
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

    def _try_chat_endpoint(self, endpoint: str, model: str, prompt: str, service_id: str = None, **kwargs) -> tuple:
        """Try to send prompt using chat completions endpoint.
        
        Returns:
            Tuple of (ok: bool, status_code: int, body: dict/str)
        """
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
        
        # Return tuple of (ok, status_code, body)
        ok = response.ok
        status_code = response.status_code
        try:
            body = response.json()
        except Exception:
            body = response.text
        
        return ok, status_code, body

    def _try_completions_endpoint(self, endpoint: str, model: str, prompt: str, service_id: str = None, **kwargs) -> tuple:
        """Try to send prompt using completions endpoint (for base models).
        
        Returns:
            Tuple of (ok: bool, status_code: int, body: dict/str)
        """
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
        
        # Return tuple of (ok, status_code, body)
        ok = response.ok
        status_code = response.status_code
        try:
            body = response.json()
        except Exception:
            body = response.text
        
        return ok, status_code, body

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

