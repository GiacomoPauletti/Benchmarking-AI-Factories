"""
Core logic for the server service.
Orchestrates AI workloads using SLURM + Apptainer.
"""

import subprocess
import sys
from pathlib import Path
import yaml
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
