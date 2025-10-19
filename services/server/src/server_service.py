"""
Core logic for the server service.
Orchestrates AI workloads using SLURM + Apptainer.
"""

from pathlib import Path
import yaml
import requests
from typing import Dict, List, Optional, Any
import logging

from slurm import SlurmDeployer
from service_manager import ServiceManager

DEFAULT_VLLM_PORT = 8001

class ServerService:
    """Main server service class with SLURM-based orchestration."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Initializing ServerService")
        self.deployer = SlurmDeployer()
        self.recipes_dir = Path(__file__).parent / "recipes"
        self.service_manager = ServiceManager()

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
        recipes = []
        
        if self.recipes_dir.exists():
            for category_dir in self.recipes_dir.iterdir():
                if category_dir.is_dir():
                    for yaml_file in category_dir.glob("*.yaml"):
                        try:
                            with open(yaml_file, 'r') as f:
                                recipe = yaml.safe_load(f)
                                recipes.append({
                                    "name": recipe["name"],
                                    "category": recipe["category"],
                                    "description": recipe["description"],
                                    "version": recipe["version"],
                                    "path": f"{category_dir.name}/{yaml_file.stem}"
                                })
                        except Exception:
                            continue
        
        return recipes
        
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
        services = self.list_running_services()
        vllm_services = []
        
        for service in services:
            # Check if this is a VLLM service based on name or recipe
            service_name = service.get("name", "").lower()
            recipe_name = service.get("recipe_name", "").lower()
            
            # Match both vllm services
            is_vllm_service = (
                "vllm" in service_name or 
                "vllm" in recipe_name or
                any("vllm" in str(val).lower() for val in service.values() if isinstance(val, str))
            )
            
            if is_vllm_service:
                job_id = service.get("id")
                # self.logger.debug("Resolving endpoint for vllm job %s", job_id)
                endpoint = self._get_vllm_endpoint(job_id)
                # self.logger.info("Resolved endpoint for job %s -> %s", job_id, endpoint)
                # Get status
                status = service.get("status", "unknown")
                vllm_services.append({
                    "id": job_id,
                    "name": service.get("name"),
                    "recipe_name": service.get("recipe_name", "unknown"),
                    "endpoint": endpoint,
                    "status": status  
                })
        
        return vllm_services
    
    def _get_vllm_endpoint(self, job_id: str) -> Optional[str]:
        """Get the endpoint for a VLLM service running on SLURM."""
        try:
            job_details = self.deployer.get_job_details(job_id)
            # self.logger.debug("job_details for %s: %s", job_id, job_details)
            if job_details and "nodes" in job_details and job_details["nodes"]:
                node = job_details["nodes"][0]
                port = None
                try:
                    # Look up registered service to find recipe name
                    service = self.service_manager.get_service(job_id)
                    recipe_name = service.get('recipe_name') if service else None
                    if recipe_name:
                        # recipes live next to this module (same layout as SlurmDeployer uses)
                        base = Path(__file__).parent / 'recipes'
                        # recipe_name can be 'category/name' or just 'name'
                        if '/' in recipe_name:
                            category, name = recipe_name.split('/', 1)
                            recipe_path = base / category / f"{name}.yaml"
                        else:
                            # search
                            found = list(base.rglob(f"{recipe_name}.yaml"))
                            recipe_path = found[0] if found else None

                        if recipe_path and recipe_path.exists():
                            with open(recipe_path, 'r') as f:
                                recipe = yaml.safe_load(f)
                                env = recipe.get('environment', {}) if isinstance(recipe, dict) else {}
                                port = str(env.get('VLLM_PORT') or (recipe.get('ports', [None])[0] if recipe.get('ports') else None))
                except Exception:
                    self.logger.debug("Could not read recipe to determine VLLM_PORT for job %s", job_id, exc_info=True)

                if not port:
                    port = DEFAULT_VLLM_PORT

                endpoint = f"http://{node}:{port}"
                self.logger.debug("_get_vllm_endpoint returning %s for job %s", endpoint, job_id)
                return endpoint
            return None
        except Exception as e:
            self.logger.exception("Error getting endpoint for %s: %s", job_id, e)
            return None

    def get_vllm_models(self, service_id: str, timeout: int = 5) -> List[str]:
        """Query a running VLLM service for available models.

        Returns a list of model ids (strings). If discovery fails an empty list
        is returned and the error is logged.
        """
        try:
            endpoint = self._get_vllm_endpoint(service_id)
            if not endpoint:
                self.logger.debug("No endpoint found for service %s when querying models", service_id)
                return []

            resp = requests.get(f"{endpoint}/v1/models", timeout=timeout)
            if not resp.ok:
                self.logger.warning("Model discovery for %s returned %s: %s", service_id, resp.status_code, resp.text)
                return []

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

            return models
        except Exception:
            self.logger.exception("Failed to discover models for service %s", service_id)
            return []
    
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

    def prompt_vllm_service(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a running VLLM service.
        
        Tries chat endpoint first (for instruction-tuned models).
        Falls back to completions endpoint if chat template error occurs (for base models).
        """
        # Find the VLLM service
        vllm_services = self.find_vllm_services()
        target_service = None
        
        for service in vllm_services:
            if service["id"] == service_id:
                target_service = service
                break
        
        if not target_service:
            raise RuntimeError(f"VLLM service {service_id} not found or not running")
        
        # Check if service is ready
        status = target_service.get("status", "").lower()
        if status in ["pending", "starting", "building", "configuring"]:
            return {
                "success": False,
                "error": f"Service is not ready yet (status: {status})",
                "message": "The vLLM service is still starting up. Please wait a moment and try again.",
                "service_id": service_id,
                "status": status,
                "endpoint": target_service.get("endpoint")
            }
        
        endpoint = target_service["endpoint"]
        
        # Get model name
        model = kwargs.get("model")
        if not model:
            models = self.get_vllm_models(service_id)
            model = models[0] if models else None

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
                current_status = self.get_service_status(service_id)
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
            self.logger.exception("Error in prompt_vllm_service")
            return {
                "success": False,
                "error": f"Error processing request: {str(e)}"
            }
