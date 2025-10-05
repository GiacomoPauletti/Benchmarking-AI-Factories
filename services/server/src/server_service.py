"""
Core logic for the server service.
"""

import subprocess
import uuid
import yaml
from pathlib import Path
from datetime import datetime


class ServerService:
    """Main server service class with core logic."""

    def __init__(self):
        self.running_services = {}

    def start_service(self, recipe_name, nodes=1, config={}):
        """Start a service based on recipe"""
        try:
            # Load recipe
            recipe_path = Path(f"src/recipes/simple/{recipe_name}.yaml")
            if not recipe_path.exists():
                raise FileNotFoundError(f"Recipe '{recipe_name}' not found")
            
            with open(recipe_path, 'r') as f:
                recipe = yaml.safe_load(f)
            
            # Generate service ID
            service_id = str(uuid.uuid4())[:8]
            
            # Build Apptainer image if it doesn't exist
            def_path = Path(f"src/recipes/simple/{recipe['container_def']}")
            sif_path = Path(f"src/recipes/simple/{recipe['image']}")
            
            if not sif_path.exists():
                print(f"Building Apptainer image from {def_path}")
                result = subprocess.run([
                    "apptainer", "build", str(sif_path), str(def_path)
                ], capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise RuntimeError(f"Failed to build image: {result.stderr}")
            
            # Run the container
            print(f"Running Apptainer container: {sif_path}")
            result = subprocess.run([
                "apptainer", "run", str(sif_path)
            ], capture_output=True, text=True)
            
            # Create service info
            service_info = {
                "id": service_id,
                "name": f"{recipe_name}-{service_id}",
                "recipe_name": recipe_name,
                "status": "completed" if result.returncode == 0 else "failed",
                "nodes": nodes,
                "config": config,
                "output": result.stdout,
                "error": result.stderr if result.stderr else None,
                "return_code": result.returncode,
                "created_at": datetime.now().isoformat()
            }
            
            self.running_services[service_id] = service_info
            return service_info
            
        except Exception as e:
            raise RuntimeError(f"Failed to start service: {str(e)}")
        
    def stop_service(self, service_id):
        """Stop running service"""
        if service_id in self.running_services:
            # For simple containers that just run and complete, we just remove from tracking
            del self.running_services[service_id]
            return True
        return False
        
    def list_available_recipes(self):
        """List all available service recipes"""
        recipes = []
        recipes_dir = Path("src/recipes/simple")
        
        if recipes_dir.exists():
            for yaml_file in recipes_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, 'r') as f:
                        recipe = yaml.safe_load(f)
                        recipes.append({
                            "name": recipe["name"],
                            "description": recipe["description"],
                            "category": recipe["category"],
                            "version": recipe["version"]
                        })
                except Exception:
                    continue
        
        return recipes
        
    def list_running_services(self):
        """List currently running services"""
        return list(self.running_services.values())
    
    def get_service(self, service_id):
        """Get details of a specific service"""
        return self.running_services.get(service_id)