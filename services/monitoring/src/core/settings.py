"""
Configuration settings for the Monitoring Service.
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Literal


class MonitoringSettings(BaseSettings):
    """Monitoring service configuration loaded from environment variables."""
    
    # Deployment mode
    deployment_mode: Literal["local", "slurm"] = "local"
    
    # Prometheus settings
    prometheus_url: str = "http://localhost:9090"
    prometheus_config_path: Path = Path("/app/config/prometheus.yml")
    
    # Server API (for metrics proxy and endpoint resolution)
    server_url: str = "http://localhost:8001"  # Alias for backward compatibility
    server_api_url: str = "http://localhost:8001"
    
    # Storage paths
    state_dir: Path = Path("/app/state")
    log_dir: Path = Path("/app/logs")
    config_dir: Path = Path("/app/config")
    
    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8002
    
    # Scrape defaults
    default_scrape_interval: str = "15s"
    default_scrape_timeout: str = "10s"
    default_evaluation_interval: str = "15s"
    
    # Retention
    default_retention_time: str = "15d"
    
    class Config:
        env_file = ".env"
        env_prefix = "MONITORING_"
        case_sensitive = False


# Global settings instance
settings = MonitoringSettings()
