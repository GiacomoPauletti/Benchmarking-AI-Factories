"""
Client Service for AI Factory - Communicates with Server Service
"""

from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any
import sys
from pathlib import Path

# Add shared modules to path
sys.path.append(str(Path(__file__).parent.parent / "shared"))
from service_discovery import service_client, service_registry

app = FastAPI(
    title="AI Factory Client Service",
    description="Client interface for managing AI workloads",
    version="1.0.0"
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AI Factory Client Service",
        "status": "running",
        "endpoints": ["/jobs", "/jobs/{job_id}", "/recipes", "/status"]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "client"}


@app.post("/jobs")
async def submit_job(recipe_name: str, nodes: int = 1, config: Dict[str, Any] = None):
    """Submit a job to the server service."""
    try:
        # Call server service to start a service
        response = await service_client.call_service(
            service_name="server",
            endpoint="/services",
            method="POST",
            json={
                "recipe_name": recipe_name,
                "nodes": nodes,
                "config": config or {}
            }
        )
        
        # Transform server response to client job format
        job = {
            "job_id": response["id"],
            "name": response["name"],
            "recipe": response["recipe_name"],
            "status": response["status"],
            "nodes": response["nodes"],
            "submitted_at": response["created_at"],
            "server_service_id": response["id"]
        }
        
        return job
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {str(e)}")


@app.get("/jobs")
async def list_jobs():
    """List all jobs by querying server service."""
    try:
        # Get running services from server
        response = await service_client.call_service(
            service_name="server",
            endpoint="/services",
            method="GET"
        )
        
        # Transform to client job format
        jobs = []
        for service in response.get("services", []):
            jobs.append({
                "job_id": service["id"],
                "name": service["name"],
                "recipe": service["recipe_name"],
                "status": service["status"],
                "nodes": service["nodes"],
                "submitted_at": service["created_at"]
            })
            
        return {"jobs": jobs}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {str(e)}")


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job details by querying server service."""
    try:
        response = await service_client.call_service(
            service_name="server",
            endpoint=f"/services/{job_id}",
            method="GET"
        )
        
        # Transform to client job format
        job = {
            "job_id": response["id"],
            "name": response["name"],
            "recipe": response["recipe_name"],
            "status": response["status"],
            "nodes": response["nodes"],
            "output": response.get("output"),
            "error": response.get("error"),
            "return_code": response.get("return_code"),
            "submitted_at": response["created_at"]
        }
        
        return job
        
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Job not found: {str(e)}")


@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a job by calling server service."""
    try:
        response = await service_client.call_service(
            service_name="server",
            endpoint=f"/services/{job_id}",
            method="DELETE"
        )
        
        return {"message": f"Job {job_id} cancelled successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


@app.get("/recipes")
async def list_recipes():
    """List available recipes from server service."""
    try:
        response = await service_client.call_service(
            service_name="server",
            endpoint="/recipes",
            method="GET"
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list recipes: {str(e)}")


@app.get("/status")
async def get_system_status():
    """Get overall system status by checking all services."""
    status = {
        "client": "healthy",
        "services": {}
    }
    
    # Check each service health
    for service_name in ["server", "monitoring", "logs"]:
        try:
            is_healthy = await service_registry.health_check(service_name)
            status["services"][service_name] = "healthy" if is_healthy else "unhealthy"
        except Exception:
            status["services"][service_name] = "unreachable"
    
    return status


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)