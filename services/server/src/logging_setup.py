"""Centralized logging setup for the server.

Configures application and Uvicorn loggers to write to stdout/stderr only.
Docker captures these streams automatically.
"""
import logging


def setup_logging(log_dir: str = "/app/logs") -> str:
    """Configure root and uvicorn loggers to use console output only.
    
    Args:
        log_dir: Ignored, kept for backwards compatibility
        
    Returns:
        Empty string (kept for backwards compatibility)
    """
    # Create formatter
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler (stdout) - Docker captures this
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(logging.DEBUG)
        root_logger.addHandler(console)

    return ""
