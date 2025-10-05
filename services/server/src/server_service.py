"""
Core logic for the server service.
Orchestrates AI workloads using SLURM + Apptainer.
"""

import subprocess
import sys
from pathlib import Path
import yaml
import requests
import json
from typing import Dict, List, Optional, Any

from deployment.slurm import SlurmDeployer


class ServerService:
    """Main server service class with SLURM-based orchestration."""

    def __init__(self):
        self.deployer = SlurmDeployer()
        # Fix the recipes directory path
        self.recipes_dir = Path(__file__).parent / "recipes"

    def start_service(self, recipe_name: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Start a service based on recipe using SLURM + Apptainer."""
        try:
            # Use config as-is, with default nodes=1 if not specified
            full_config = config or {}
            if "nodes" not in full_config:
                full_config["nodes"] = 1
            
            # Submit to SLURM
            job_info = self.deployer.submit_job(recipe_name, full_config)
            
            return {
                "id": job_info["id"],  # SLURM job ID is used directly as service ID
                "name": job_info["name"],
                "recipe_name": recipe_name,
                "status": job_info["status"],
                "nodes": full_config["nodes"],
                "config": full_config,
                "created_at": job_info["created_at"]
            }
            
        except Exception as e:
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
        """List currently running services."""
        return self.deployer.list_jobs()
    
    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific service."""
        jobs = self.deployer.list_jobs()
        for job in jobs:
            if job["id"] == service_id:
                return job
        return None
    
    def get_service_logs(self, service_id: str) -> str:
        """Get logs from a service."""
        return self.deployer.get_job_logs(service_id)
    
    def get_service_status(self, service_id: str) -> str:
        """Get current status of a service."""
        return self.deployer.get_job_status(service_id)

    def find_vllm_services(self) -> List[Dict[str, Any]]:
        """Find running VLLM services and their endpoints."""
        services = self.list_running_services()
        vllm_services = []
        
        for service in services:
            # Check if this is a VLLM service based on name or recipe
            service_name = service.get("name", "").lower()
            recipe_name = service.get("recipe_name", "").lower()
            
            # Match both vllm and vllm_dummy services
            is_vllm_service = (
                "vllm" in service_name or 
                "vllm" in recipe_name or
                any("vllm" in str(val).lower() for val in service.values() if isinstance(val, str))
            )
            
            if is_vllm_service and service.get("status") in ["running", "pending"]:
                # Try to determine the endpoint
                job_id = service.get("id")
                endpoint = self._get_vllm_endpoint(job_id)
                if endpoint or service.get("status") == "pending":
                    vllm_services.append({
                        "id": job_id,
                        "name": service.get("name"),
                        "recipe_name": service.get("recipe_name", "unknown"),
                        "endpoint": endpoint,
                        "status": service.get("status")
                    })
        
        return vllm_services
    
    def _get_vllm_endpoint(self, job_id: str) -> Optional[str]:
        """Get the endpoint for a VLLM service running on SLURM."""
        try:
            # Get job details from SLURM to find allocated nodes
            job_details = self.deployer.get_job_details(job_id)
            if job_details and "nodes" in job_details:
                # Assume VLLM runs on port 8000 (from the recipe)
                node = job_details["nodes"][0] if job_details["nodes"] else None
                if node:
                    return f"http://{node}:8000"
            return None
        except Exception:
            return None
    
    def prompt_vllm_service(self, service_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Send a prompt to a running VLLM service."""
        # Find the VLLM service
        vllm_services = self.find_vllm_services()
        target_service = None
        
        for service in vllm_services:
            if service["id"] == service_id:
                target_service = service
                break
        
        if not target_service:
            raise RuntimeError(f"VLLM service {service_id} not found or not running")
        
        endpoint = target_service["endpoint"]
        
        # Prepare the prompt request in OpenAI format (vLLM is compatible)
        request_data = {
            "model": kwargs.get("model", "microsoft/DialoGPT-medium"),  # Default from vllm.def
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": kwargs.get("max_tokens", 150),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False
        }
        
        try:
            # Send request to VLLM service
            response = requests.post(
                f"{endpoint}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json=request_data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Extract the response text
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                return {
                    "success": True,
                    "response": content,
                    "service_id": service_id,
                    "endpoint": endpoint,
                    "usage": result.get("usage", {})
                }
            else:
                return {
                    "success": False,
                    "error": "No response generated",
                    "raw_response": result
                }
                
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"Failed to connect to VLLM service: {str(e)}",
                "endpoint": endpoint
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error processing request: {str(e)}"
            }
