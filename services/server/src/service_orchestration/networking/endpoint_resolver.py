"""
Endpoint resolver utility for determining service endpoints.

Unifies the logic for resolving HTTP endpoints of services running on SLURM.
"""

from typing import Optional
import logging

from service_orchestration.recipes import RecipeLoader


class EndpointResolver:
    """Resolves HTTP endpoints for services running on SLURM compute nodes."""
    
    def __init__(self, deployer, service_manager, recipe_loader: RecipeLoader):
        """
        Initialize the endpoint resolver.
        
        Args:
            deployer: SlurmDeployer instance for getting job details
            service_manager: ServiceManager instance for looking up service info
            recipe_loader: RecipeLoader instance for getting recipe metadata
        """
        self.deployer = deployer
        self.service_manager = service_manager
        self.recipe_loader = recipe_loader
        self.logger = logging.getLogger(__name__)
    
    def resolve(self, replica_id: str, default_port: Optional[int] = None) -> Optional[str]:
        """
        Resolve the HTTP endpoint for a service or replica.
        
        Supports two ID formats:
        1. Simple job ID: "3712345" - resolves using recipe port
        2. Composite replica ID: "3712345:8002" - uses specified port
        
        This method:
        1. Parses the replica_id to extract job_id and optional port
        2. Gets the SLURM job details to find which node it's running on
        3. Uses specified port if provided, otherwise looks up recipe port
        4. Falls back to default_port if no port found
        5. Returns the full HTTP endpoint URL
        
        Args:
            replica_id: SLURM job ID or composite "job_id:port"
            default_port: Fallback port if not specified
        
        Returns:
            HTTP endpoint string (e.g., "http://mel0343:8002"), or None if resolution fails
        """
        try:
            # Parse replica_id to extract job_id and optional port
            if ":" in replica_id:
                # Composite format: "job_id:port"
                job_id, port_str = replica_id.split(":", 1)
                specified_port = int(port_str)
                self.logger.debug(f"Parsed composite replica_id {replica_id}: job={job_id}, port={specified_port}")
            else:
                # Simple format: just job_id
                job_id = replica_id
                specified_port = None
                self.logger.debug(f"Simple job ID: {job_id}")
            
            # Get job details from SLURM
            job_details = self.deployer.get_job_details(job_id)
            
            if not job_details or "nodes" not in job_details or not job_details["nodes"]:
                self.logger.debug("No node information for job %s", job_id)
                return None
            
            # Extract the first node (master node for distributed jobs)
            # The nodes field should already be parsed as a list by slurm.py
            nodes = job_details["nodes"]
            if isinstance(nodes, list) and nodes:
                node = str(nodes[0]).strip()
            else:
                # Fallback: treat as string
                node = str(nodes).strip()
            
            # Basic validation: node name should not be empty
            if not node:
                self.logger.warning("Empty node name for job %s", job_id)
                return None
            
            # Determine the port
            if specified_port is not None:
                # Use port from composite replica_id
                port = specified_port
            else:
                # Look up port from recipe
                port = self._get_port_for_job(job_id)
                
                # Fallback to default port if needed
                if port is None:
                    port = default_port
            
            if port is None:
                self.logger.warning("No port found for replica %s (job %s)", replica_id, job_id)
                return None
            
            endpoint = f"http://{node}:{port}"
            self.logger.debug("Resolved endpoint for replica %s: %s (from nodes: %s)", replica_id, endpoint, nodes)
            return endpoint
            
        except Exception as e:
            self.logger.exception("Error resolving endpoint for replica %s: %s", replica_id, e)
            return None
    
    def _get_port_for_job(self, job_id: str) -> Optional[int]:
        """
        Get the port number for a job by looking up its recipe.
        
        Args:
            job_id: SLURM job ID
        
        Returns:
            Port number, or None if not found
        """
        try:
            # Look up the service to get recipe name
            service = self.service_manager.get_service(job_id)
            if not service:
                self.logger.debug("Service %s not found in service manager", job_id)
                return None
            
            recipe_name = service.get('recipe_name')
            if not recipe_name:
                self.logger.debug("No recipe_name for service %s", job_id)
                return None
            
            # Get port from recipe
            port = self.recipe_loader.get_recipe_port(recipe_name)
            
            if port:
                self.logger.debug("Found port %s for job %s (recipe: %s)", port, job_id, recipe_name)
            
            return port
            
        except Exception as e:
            self.logger.exception("Error getting port for job %s: %s", job_id, e)
            return None
