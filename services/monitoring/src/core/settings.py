"""
Configuration settings for the Monitoring Service.
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Literal


class MonitoringSettings(BaseSettings):
    """Monitoring service configuration loaded from environment variables."""

    # Prometheus settings
    prometheus_url: str = "http://localhost:9090"
    
    # Server API (for metrics proxy and endpoint resolution)
    server_url: str = "http://localhost:8001"  # Alias for backward compatibility
    server_api_url: str = "http://localhost:8001"
    
    # Storage paths
    state_dir: Path = Path("/app/state")
    log_dir: Path = Path("/app/logs")
    
    class Config:
        env_file = ".env"
        env_prefix = "MONITORING_"
        case_sensitive = False


# Global settings instance
settings = MonitoringSettings()
