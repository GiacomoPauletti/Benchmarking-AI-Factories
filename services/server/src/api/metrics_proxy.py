"""
Metrics proxy endpoints for Server Service.

These endpoints proxy /metrics from services running in SLURM jobs
so Prometheus can scrape them without direct network access.
"""
from fastapi import APIRouter, HTTPException, Response
from typing import Dict, Any
import httpx
import logging

from server_service import ServerService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metrics", tags=["metrics"])


async def get_service_endpoint(server_service: ServerService, job_id: str) -> Dict[str, Any]:
    """
    Get service endpoint information from job ID.
    
    Args:
        server_service: ServerService instance
        job_id: SLURM job ID
    
    Returns:
        Dict with service endpoint info
    
    Raises:
        HTTPException: If service not found
    """
    # Get all running services
    services = server_service.list_running_services()
    
    # Find service by job ID
    service = next((s for s in services if s.get("id") == job_id), None)
    
    if not service:
        raise HTTPException(status_code=404, detail=f"Service with job ID {job_id} not found")
    
    return service


@router.get("/vllm/{job_id}")
async def proxy_vllm_metrics(job_id: str):
    """
    Proxy /metrics endpoint from vLLM service running in SLURM.
    
    This allows Prometheus to scrape vLLM metrics without direct access
    to the compute node.
    
    **Path Parameters:**
    - `job_id`: SLURM job ID of the vLLM service
    
    **Returns:**
    - Prometheus-formatted metrics from vLLM (200 OK)
    - 503 Service Unavailable if service exists but isn't running yet
    - 404 Not Found if service doesn't exist
    
    **Example:**
    ```
    GET /metrics/vllm/3691724
    ```
    """
    from server_service import ServerService
    
    try:
        server_service = ServerService()
        
        # Get service info (will raise 404 if service doesn't exist)
        service = server_service.get_service(job_id)
        if not service:
            raise HTTPException(status_code=404, detail=f"Service with job ID {job_id} not found")

        # Check if service is running
        status = service.get("status", "").lower()
        if status not in ["running"]:
            # Service exists but isn't ready yet - return 503 with empty metrics
            # so Prometheus can parse the response (Prometheus expects text/plain, not JSON)
            logger.info(f"vLLM service {job_id} not ready (status: {status}), returning 503 with empty metrics")
            return Response(
                content=f"# Service {job_id} not ready (status: {status})\n",
                status_code=503,
                media_type="text/plain; version=0.0.4"
            )
        
        # Get endpoint from service info
        endpoint = service.get("endpoint")
        if not endpoint:
            raise HTTPException(status_code=500, detail="Service endpoint not available")
        
        # Construct metrics URL
        if not endpoint.startswith("http"):
            endpoint = f"http://{endpoint}"
        
        metrics_url = f"{endpoint}/metrics"
        
        logger.info(f"Proxying vLLM metrics from {metrics_url}")
        
        # Fetch metrics from vLLM service
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(metrics_url)
            response.raise_for_status()
            
            # Return raw metrics in Prometheus format
            return Response(
                content=response.text,
                media_type="text/plain; version=0.0.4"
            )
    
    except HTTPException:
        # Re-raise HTTPExceptions (404, 503, etc.)
        raise
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch vLLM metrics for job {job_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch metrics from vLLM service: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error proxying vLLM metrics for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/qdrant/{job_id}")
async def proxy_qdrant_metrics(job_id: str):
    """
    Proxy /metrics endpoint from Qdrant service running in SLURM.
    
    This allows Prometheus to scrape Qdrant metrics without direct access
    to the compute node.
    
    **Path Parameters:**
    - `job_id`: SLURM job ID of the Qdrant service
    
    **Returns:**
    - Prometheus-formatted metrics from Qdrant (200 OK)
    - 503 Service Unavailable if service exists but isn't running yet
    - 404 Not Found if service doesn't exist
    
    **Example:**
    ```
    GET /metrics/qdrant/3691725
    ```
    """
    from server_service import ServerService
    
    try:
        server_service = ServerService()
        
        # Get service info (will raise 404 if service doesn't exist)
        service = server_service.get_service(job_id)
        
        # Check if service is running
        status = service.get("status", "").lower()
        if status not in ["running"]:
            # Service exists but isn't ready yet - return 503 with empty metrics
            # so Prometheus can parse the response (Prometheus expects text/plain, not JSON)
            logger.info(f"Qdrant service {job_id} not ready (status: {status}), returning 503 with empty metrics")
            return Response(
                content=f"# Service {job_id} not ready (status: {status})\n",
                status_code=503,
                media_type="text/plain; version=0.0.4"
            )
        
        # Get endpoint from service info
        endpoint = service.get("endpoint")
        if not endpoint:
            raise HTTPException(status_code=500, detail="Service endpoint not available")
        
        # Construct metrics URL
        if not endpoint.startswith("http"):
            endpoint = f"http://{endpoint}"
        
        metrics_url = f"{endpoint}/metrics"
        
        logger.info(f"Proxying Qdrant metrics from {metrics_url}")
        
        # Fetch metrics from Qdrant service
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(metrics_url)
            response.raise_for_status()
            
            # Return raw metrics in Prometheus format
            return Response(
                content=response.text,
                media_type="text/plain; version=0.0.4"
            )
    
    except HTTPException:
        # Re-raise HTTPExceptions (404, 503, etc.)
        raise
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch Qdrant metrics for job {job_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch metrics from Qdrant service: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error proxying Qdrant metrics for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service/{job_id}")
async def proxy_service_metrics(job_id: str):
    """
    Generic metrics proxy for any service running in SLURM.
    
    Automatically detects the service type and proxies its /metrics endpoint.
    
    **Path Parameters:**
    - `job_id`: SLURM job ID of the service
    
    **Returns:**
    - Prometheus-formatted metrics from the service (200 OK)
    - 503 Service Unavailable if service exists but isn't running yet
    - 404 Not Found if service doesn't exist
    
    **Example:**
    ```
    GET /metrics/service/3691724
    ```
    """
    from server_service import ServerService
    
    try:
        server_service = ServerService()
        
        # Get service info (will raise 404 if service doesn't exist)
        service = server_service.get_service(job_id)
        
        # Check if service is running
        status = service.get("status", "").lower()
        if status not in ["running"]:
            # Service exists but isn't ready yet - return 503 with empty metrics
            # so Prometheus can parse the response (Prometheus expects text/plain, not JSON)
            logger.info(f"Service {job_id} not ready (status: {status}), returning 503 with empty metrics")
            return Response(
                content=f"# Service {job_id} not ready (status: {status})\n",
                status_code=503,
                media_type="text/plain; version=0.0.4"
            )
        
        # Get endpoint from service info
        endpoint = service.get("endpoint")
        if not endpoint:
            raise HTTPException(status_code=500, detail="Service endpoint not available")
        
        # Construct metrics URL
        if not endpoint.startswith("http"):
            endpoint = f"http://{endpoint}"
        
        metrics_url = f"{endpoint}/metrics"
        
        service_name = service.get("name", "unknown")
        logger.info(f"Proxying {service_name} metrics from {metrics_url}")
        
        # Fetch metrics from service
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(metrics_url)
            response.raise_for_status()
            
            # Return raw metrics in Prometheus format
            return Response(
                content=response.text,
                media_type="text/plain; version=0.0.4"
            )
    
    except HTTPException:
        # Re-raise HTTPExceptions (404, 503, etc.)
        raise
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch metrics for job {job_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch metrics from service: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error proxying metrics for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all")
async def get_all_services_metrics():
    """
    Get a list of all running services with their metrics endpoints.
    
    This is useful for Prometheus service discovery.
    
    **Returns:**
    - List of services with their metrics proxy URLs
    
    **Example Response:**
    ```json
    {
      "services": [
        {
          "job_id": "3691724",
          "name": "vllm-service",
          "metrics_url": "http://server:8001/metrics/vllm/3691724"
        },
        {
          "job_id": "3691725",
          "name": "qdrant-service",
          "metrics_url": "http://server:8001/metrics/qdrant/3691725"
        }
      ]
    }
    ```
    """
    from server_service import ServerService
    
    try:
        server_service = ServerService()
        services = server_service.list_running_services()
        
        # Build list of metrics endpoints
        metrics_services = []
        for service in services:
            job_id = service.get("id")
            name = service.get("name", "unknown")
            recipe_name = service.get("recipe_name", "")
            
            # Determine proxy path based on recipe
            if "vllm" in recipe_name.lower():
                proxy_path = f"/metrics/vllm/{job_id}"
            elif "qdrant" in recipe_name.lower():
                proxy_path = f"/metrics/qdrant/{job_id}"
            else:
                proxy_path = f"/metrics/service/{job_id}"
            
            metrics_services.append({
                "job_id": job_id,
                "name": name,
                "recipe": recipe_name,
                "metrics_url": f"http://server:8001{proxy_path}",
                "status": service.get("status")
            })
        
        return {"services": metrics_services, "count": len(metrics_services)}
    
    except Exception as e:
        logger.error(f"Error listing services metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
