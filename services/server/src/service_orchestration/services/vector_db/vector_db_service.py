"""Abstract base class for vector database services (Qdrant, Chroma, Weaviate, etc.)."""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from service_orchestration.services.base_service import BaseService


class VectorDbService(BaseService, ABC):
    """Abstract base class for all vector database service implementations.
    
    This class defines the common interface that all vector database services
    (Qdrant, Chroma, Weaviate, FAISS, etc.) must implement.
    """

    @abstractmethod
    def get_collections(self, service_id: str) -> Dict[str, Any]:
        """Get all collections from a vector database service.
        
        Args:
            service_id: The service ID to query
            
        Returns:
            Dict with either:
            - {"success": True, "collections": [...]}
            - {"success": False, "error": "..."}
        """
        pass

    @abstractmethod
    def create_collection(self, service_id: str, collection_name: str, 
                         vector_size: int, distance: str) -> Dict[str, Any]:
        """Create a new collection in the vector database.
        
        Args:
            service_id: The service ID
            collection_name: Name of the collection to create
            vector_size: Dimensionality of vectors
            distance: Distance metric (e.g., "Cosine", "Euclid", "Dot")
            
        Returns:
            Dict with either:
            - {"success": True, ...}
            - {"success": False, "error": "..."}
        """
        pass

    @abstractmethod
    def delete_collection(self, service_id: str, collection_name: str) -> Dict[str, Any]:
        """Delete a collection from the vector database.
        
        Args:
            service_id: The service ID
            collection_name: Name of the collection to delete
            
        Returns:
            Dict with either:
            - {"success": True, ...}
            - {"success": False, "error": "..."}
        """
        pass

    @abstractmethod
    def get_collection_info(self, service_id: str, collection_name: str) -> Dict[str, Any]:
        """Get detailed information about a collection.
        
        Args:
            service_id: The service ID
            collection_name: Name of the collection
            
        Returns:
            Dict with collection metadata or error
        """
        pass

    @abstractmethod
    def upsert_points(self, service_id: str, collection_name: str, 
                     points: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Insert or update points (vectors) in a collection.
        
        Args:
            service_id: The service ID
            collection_name: Name of the collection
            points: List of point dicts with id, vector, and optional payload
            
        Returns:
            Dict with either:
            - {"success": True, ...}
            - {"success": False, "error": "..."}
        """
        pass

    @abstractmethod
    def search_points(self, service_id: str, collection_name: str, 
                     query_vector: List[float], limit: int = 10) -> Dict[str, Any]:
        """Search for similar vectors in a collection.
        
        Args:
            service_id: The service ID
            collection_name: Name of the collection
            query_vector: Query vector for similarity search
            limit: Maximum number of results to return
            
        Returns:
            Dict with either:
            - {"success": True, "results": [...]}
            - {"success": False, "error": "..."}
        """
        pass

    @abstractmethod
    def _check_service_ready(self, service_id: str, service_info: Dict[str, Any]) -> tuple[bool, str]:
        """Check if a vector database service is ready to accept requests.
        
        This method should implement service-specific readiness checks by examining
        logs for startup indicators.
        
        Args:
            service_id: The service ID to check
            service_info: The service information dict
            
        Returns:
            Tuple of (is_ready: bool, status: str)
        """
        pass
