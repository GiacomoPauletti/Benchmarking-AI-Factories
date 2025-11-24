"""
Logging configuration for the Logs Service.
"""

import logging
import sys
import os


def setup_logging(log_level: str = None):
    """Configure logging for the logs service.
    
    Args:
        log_level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO")
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.INFO)
