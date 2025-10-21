"""VLLM service-specific operations."""

from typing import Dict, List, Optional, Any
import requests
from .base_service import BaseService

DEFAULT_VLLM_PORT = 8001


class VllmService(BaseService):
    """Handles all VLLM-specific operations."""

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
            
            is_ready, status = self._check_service_ready(service_id, service_info)
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

            resp = requests.get(f"{endpoint}/v1/models", timeout=timeout)
            if not resp.ok:
                self.logger.warning("Model discovery for %s returned %s: %s", service_id, resp.status_code, resp.text)
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code} from models endpoint",
                    "message": f"Failed to query models from vLLM service (HTTP {resp.status_code}).",
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "models": []
                }

            self.logger.debug("Model discovery response for %s: %s", service_id, resp.text)

            data = resp.json()
            models = []
            
            # vLLM returns {"object": "list", "data": [...]}
            if isinstance(data, dict):
                # Try standard OpenAI format (data field)
                candidates = data.get('data', [])
                # Fallback to other possible formats
                if not candidates:
                    candidates = data.get('models') or data.get('served_models') or []
                
                if isinstance(candidates, list):
                    for item in candidates:
                        if isinstance(item, str):
                            models.append(item)
                        elif isinstance(item, dict):
                            model_id = item.get('id') or item.get('model')
                            if model_id:
                                models.append(model_id)
            elif isinstance(data, list):
                # Direct list format
                for item in data:
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

    def _check_service_ready(self, service_id: str, service_info: Dict[str, Any]) -> tuple[bool, str]:
        """Check if a service is ready to accept requests.
        
        Args:
            service_id: The service ID to check
            service_info: The service information dict
            
        Returns:
            Tuple of (is_ready: bool, status: str) where status is the current LIVE status from SLURM
        """
        # Get the current LIVE status from SLURM (don't trust cached status)
        try:
            status = self.deployer.get_job_status(service_id).lower()
        except Exception as e:
            self.logger.warning(f"Failed to get status for service {service_id}: {e}")
            status = service_info.get("status", "unknown").lower()
        
        # Check if service is ready
        is_ready = status not in ["pending", "starting", "building", "configuring"]
        
        return is_ready, status

    def prompt(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a running VLLM service.
        
        Tries chat endpoint first (for instruction-tuned models).
        Falls back to completions endpoint if chat template error occurs (for base models).
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
        
        # Check if service is ready
        is_ready, status = self._check_service_ready(service_id, service_info)
        if not is_ready:
            return {
                "success": False,
                "error": f"Service is not ready yet (status: {status})",
                "message": "The vLLM service is still starting up. Please wait a moment and try again.",
                "service_id": service_id,
                "status": status
            }
        
        # Try to get the endpoint
        endpoint = self.endpoint_resolver.resolve(service_id, default_port=DEFAULT_VLLM_PORT)
        if not endpoint:
            # Service exists but endpoint not available yet
            return {
                "success": False,
                "error": "Service endpoint not available",
                "message": "The vLLM service endpoint is not available yet. The service may still be initializing.",
                "service_id": service_id,
                "status": status
            }
        
        # Get model name and remove it from kwargs to avoid duplicate argument
        model = kwargs.pop("model", None)
        if not model:
            models_result = self.get_models(service_id)
            if models_result.get("success") and models_result.get("models"):
                model = models_result["models"][0]
            else:
                model = None

        self.logger.debug("Preparing prompt for service %s at %s with model %s", service_id, endpoint, model)
        
        try:
            # Try chat endpoint first (works for instruction-tuned models)
            response = self._try_chat_endpoint(endpoint, model, prompt, **kwargs)
            
            # Check if we got a chat template error
            if self._is_chat_template_error(response):
                self.logger.info("Chat template error detected, retrying with completions endpoint")
                
                # Retry with completions endpoint (works for base models)
                response = self._try_completions_endpoint(endpoint, model, prompt, **kwargs)
                return self._parse_completions_response(response, endpoint, service_id)
            
            # No chat template error - parse as chat response
            return self._parse_chat_response(response, endpoint, service_id)
                
        except requests.exceptions.RequestException as e:
            error_str = str(e)
            
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
            self.logger.exception("Error in prompt")
            return {
                "success": False,
                "error": f"Error processing request: {str(e)}"
            }

    def _try_chat_endpoint(self, endpoint: str, model: str, prompt: str, **kwargs) -> Dict[str, Any]:
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
        
        self.logger.debug("Trying chat endpoint via SSH: %s:%s%s", remote_host, remote_port, path)
        
        # Use SSH to make the HTTP request
        ssh_manager = self.deployer.ssh_manager
        success, status_code, body = ssh_manager.http_request_via_ssh(
            remote_host=remote_host,
            remote_port=remote_port,
            method="POST",
            path=path,
            json_data=request_data,
            timeout=30
        )
        
        # Create a mock response object that matches requests.Response interface
        class MockResponse:
            def __init__(self, status_code, text, ok):
                self.status_code = status_code
                self.text = text
                self.ok = ok
            
            def json(self):
                import json
                return json.loads(self.text)
        
        return MockResponse(status_code, body, status_code >= 200 and status_code < 300)

    def _try_completions_endpoint(self, endpoint: str, model: str, prompt: str, **kwargs) -> Dict[str, Any]:
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
        
        self.logger.debug("Trying completions endpoint via SSH: %s:%s%s", remote_host, remote_port, path)
        
        # Use SSH to make the HTTP request
        ssh_manager = self.deployer.ssh_manager
        success, status_code, body = ssh_manager.http_request_via_ssh(
            remote_host=remote_host,
            remote_port=remote_port,
            method="POST",
            path=path,
            json_data=request_data,
            timeout=30
        )
        
        # Create a mock response object that matches requests.Response interface
        class MockResponse:
            def __init__(self, status_code, text, ok):
                self.status_code = status_code
                self.text = text
                self.ok = ok
            
            def json(self):
                import json
                return json.loads(self.text)
        
        return MockResponse(status_code, body, status_code >= 200 and status_code < 300)

    def _is_chat_template_error(self, response: requests.Response) -> bool:
        """Check if response indicates a chat template error."""
        if response.status_code != 400:
            return False
        
        try:
            body = response.json()
            if not isinstance(body, dict):
                return False
            
            # Check both direct detail field and nested error.message field
            error_text = str(body.get("detail", ""))
            if "error" in body and isinstance(body["error"], dict):
                error_text += " " + str(body["error"].get("message", ""))
            
            return "chat template" in error_text.lower()
        except Exception:
            return False

    def _parse_chat_response(self, response: requests.Response, endpoint: str, service_id: str) -> Dict[str, Any]:
        """Parse response from chat completions endpoint."""
        if not response.ok:
            body = None
            try:
                body = response.json()
            except Exception:
                body = response.text
            
            return {
                "success": False,
                "error": f"vLLM returned {response.status_code}",
                "endpoint": endpoint,
                "status_code": response.status_code,
                "body": body
            }
        
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            return {
                "success": True,
                "response": content,
                "service_id": service_id,
                "endpoint": endpoint,
                "endpoint_used": "chat",
                "usage": result.get("usage", {})
            }
        
        return {
            "success": False,
            "error": "No response generated",
            "raw_response": result,
            "endpoint": endpoint
        }

    def _parse_completions_response(self, response: requests.Response, endpoint: str, service_id: str) -> Dict[str, Any]:
        """Parse response from completions endpoint."""
        if not response.ok:
            body = None
            try:
                body = response.json()
            except Exception:
                body = response.text
            
            return {
                "success": False,
                "error": f"vLLM completions returned {response.status_code}",
                "endpoint": endpoint,
                "status_code": response.status_code,
                "body": body
            }
        
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["text"]
            return {
                "success": True,
                "response": content,
                "service_id": service_id,
                "endpoint": endpoint,
                "endpoint_used": "completions",
                "usage": result.get("usage", {})
            }
        
        return {
            "success": False,
            "error": "No response generated from completions endpoint",
            "raw_response": result,
            "endpoint": endpoint
        }
