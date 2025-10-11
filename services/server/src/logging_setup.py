"""Centralized logging setup for the server.

Provides a function to configure application and Uvicorn loggers and ensure
log files are truncated on startup.
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Tuple


def setup_logging(log_dir: str = "/app/logs") -> str:
    """Configure root and uvicorn loggers.

    Creates `server.log` and `server_fastapi.log` inside `log_dir` and
    truncates them on startup. Returns tuple (server_log_path, uvicorn_log_path).
    """
    os.makedirs(log_dir, exist_ok=True)

    server_log = os.path.join(log_dir, "server.log")

    # Create formatter
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Helper to create a rotating handler that truncates the file on creation.
    def make_truncating_rotating_handler(path: str) -> RotatingFileHandler:
        # Ensure the file exists and is truncated
        open(path, "w").close()
        handler = RotatingFileHandler(path, maxBytes=10*1024*1024, backupCount=5)
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        return handler

    # Application-level handler (server.log)
    server_handler = make_truncating_rotating_handler(server_log)
    # Avoid adding duplicate handlers
    if not any(isinstance(h, RotatingFileHandler) and getattr(h, 'baseFilename', '') == server_handler.baseFilename for h in root_logger.handlers):
        root_logger.addHandler(server_handler)

    # Console handler (stdout) for immediate visibility
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(logging.DEBUG)
        root_logger.addHandler(console)

    # Attach the same server file handler to Uvicorn loggers so everything goes to one file
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        ulogger = logging.getLogger(logger_name)
        if not any(isinstance(h, RotatingFileHandler) and getattr(h, 'baseFilename', '') == server_handler.baseFilename for h in ulogger.handlers):
            ulogger.addHandler(server_handler)

    return server_log
