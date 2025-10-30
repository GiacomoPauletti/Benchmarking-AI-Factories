"""
Main FastAPI application entry point for the Server Service.
SLURM + Apptainer orchestration for AI workloads.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Clean package imports
from api.routes import router

# Create FastAPI application
app = FastAPI(
    title="AI Factory Server Service",
    description="SLURM + Apptainer orchestration for AI workloads",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "AI Factory Server Service",
        "version": "1.0.0",
        "status": "running",
        "node": os.environ.get("SLURMD_NODENAME", "unknown"),
        "job_id": os.environ.get("SLURM_JOB_ID", "unknown"),
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

# Include API routes
app.include_router(router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting AI Factory Server Service...")
    print(f"📍 Node: {os.environ.get('SLURMD_NODENAME', 'unknown')}")
    print(f"🆔 Job ID: {os.environ.get('SLURM_JOB_ID', 'unknown')}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )

