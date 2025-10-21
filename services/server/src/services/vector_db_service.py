"""Vector database service-specific operations."""

from typing import Dict, List, Optional, Any
from .base_service import BaseService

DEFAULT_QDRANT_PORT = 6333


class VectorDbService(BaseService):
    """Handles all vector database-specific operations."""

    def find_services(self) -> List[Dict[str, Any]]:
        """Find running vector database services and their endpoints."""
        def is_vector_db(service):
            recipe_name = service.get("recipe_name", "").lower()
            # Match vector-db category
            return "vector-db" in recipe_name or recipe_name in ["qdrant", "chroma", "faiss"]
        
        services = self._filter_services(is_vector_db)
        vector_db_services = []
        
        for service in services:
            job_id = service.get("id")
            endpoint = self.endpoint_resolver.resolve(job_id, default_port=DEFAULT_QDRANT_PORT)
            status = service.get("status", "unknown")
            vector_db_services.append({
                "id": job_id,
                "name": service.get("name"),
                "recipe_name": service.get("recipe_name", "unknown"),
                "endpoint": endpoint,
                "status": status
            })
        
        return vector_db_services
