"""
SLURM Job Management API routes
Direct job control (lower-level than services)
"""

from fastapi import APIRouter


def create_router(orchestrator):
    """Create job management routes"""
    router = APIRouter()
    
    @router.delete("/{job_id}")
    async def cancel_job(job_id: str):
        """Cancel a SLURM job"""
        return orchestrator.cancel_job(job_id)
    
    @router.get("/{job_id}")
    async def get_job_status(job_id: str):
        """Get SLURM job status"""
        return orchestrator.get_job_status(job_id)
    
    @router.get("/")
    async def get_job_logs(path: str, lines: int = 200):
        """Get job logs from a file path"""
        return orchestrator.get_job_logs(path, lines)
    
    return router
