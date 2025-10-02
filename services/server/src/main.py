"""
Main FastAPI application entry point for the Server Service.
"""

from fastapi import FastAPI
from api.routes import router

# Create FastAPI application
app = FastAPI(
    title="AI Factory Server Service",
    description="Service orchestrator using proper architecture",
    version="1.0.0"
)

# Include the API routes
app.include_router(router)

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AI Factory Server Service",
        "status": "running",
        "endpoints": ["/services", "/services/{service_id}", "/recipes"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)