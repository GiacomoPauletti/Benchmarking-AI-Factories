"""
Main entry point for ServiceOrchestrator FastAPI application.
This is what should be run by the Apptainer container on MeluXina.
"""

import uvicorn
import logging
import os
from pathlib import Path

from service_orchestration.core import ServiceOrchestrator
from api import create_app

# Configure logging to both file and console
def setup_logging():
    """Configure logging to write to both file and stdout"""  
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()  # Also log to console
        ]
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()


def main():
    """Main entry point"""
    logger.info("Starting ServiceOrchestrator application")
    
    # Create orchestrator instance (business logic)
    orchestrator = ServiceOrchestrator()
    
    # Create FastAPI app with routes
    app = create_app(orchestrator)
    
    orchestrator_port = int(os.getenv("ORCHESTRATOR_PORT", "8003"))
    # Run server with logging configuration
    logger.info(f"Starting uvicorn server on 0.0.0.0:{orchestrator_port}")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=orchestrator_port,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "INFO"},
                "uvicorn.error": {"level": "INFO"},
                "uvicorn.access": {"handlers": ["default"], "level": "INFO"},
            },
        }
    )


if __name__ == "__main__":
    main()
