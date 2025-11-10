"""
Prometheus manager - controls a local Prometheus instance via HTTP API.

This file replaces the older `local_prometheus.py` module. Prometheus runs as a
persistent Docker service; this manager interacts with it over HTTP for health
checks, config reloads, and queries.
"""
import logging
import requests
from pathlib import Path
from typing import Optional, Dict, Any
import time

logger = logging.getLogger(__name__)


class PrometheusManager:
    """
    Manages a Prometheus instance reachable over HTTP.

    Responsibilities:
    - Check Prometheus health/readiness
    - Hot-reload configuration
    - Query metrics via HTTP API
    - Get scrape target status

    Does NOT:
    - Start/stop Prometheus (Docker Compose handles this)
    - Generate config (ConfigRenderer does this)
    - Manage SLURM jobs
    """

    def __init__(self, prometheus_url: str, config_path: Path):
        """
        Args:
            prometheus_url: Base URL of Prometheus (e.g., http://prometheus:9090)
            config_path: Path to prometheus.yml config file
        """
        self.url = prometheus_url.rstrip('/')
        self.config_path = Path(config_path)
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

        logger.info(f"Initialized PrometheusManager for {self.url}")

    def is_healthy(self) -> bool:
        """Check if Prometheus is healthy"""
        try:
            response = self.session.get(f"{self.url}/-/healthy", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Prometheus health check failed: {e}")
            return False

    def is_ready(self, timeout_s: int = 30) -> bool:
        """
        Check if Prometheus is ready to serve queries.

        Args:
            timeout_s: How long to wait for Prometheus to become ready

        Returns:
            True if Prometheus is ready within timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout_s:
            try:
                response = self.session.get(f"{self.url}/-/ready", timeout=5)
                if response.status_code == 200:
                    logger.info("Prometheus is ready")
                    return True
            except Exception as e:
                logger.debug(f"Prometheus not ready yet: {e}")

            time.sleep(2)

        logger.warning(f"Prometheus did not become ready within {timeout_s}s")
        return False

    def reload_config(self) -> bool:
        """
        Hot-reload Prometheus configuration.

        Prometheus must be started with --web.enable-lifecycle flag.

        Returns:
            True if reload successful, False otherwise
        """
        try:
            response = self.session.post(f"{self.url}/-/reload", timeout=10)
            response.raise_for_status()
            logger.info("Prometheus configuration reloaded successfully")
            return True
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.error(
                    "Reload failed: Prometheus not started with --web.enable-lifecycle. "
                    "Check docker-compose.yml command section."
                )
            else:
                logger.error(f"Failed to reload Prometheus: {e}")
            return False
        except Exception as e:
            logger.error(f"Error reloading Prometheus: {e}")
            return False

    def query_range(
        self,
        query: str,
        start: str,
        end: str,
        step: str = "15s"
    ) -> Optional[Dict[str, Any]]:
        """
        Query Prometheus for time range data.

        Args:
            query: PromQL query string
            start: Start time (RFC3339 or Unix timestamp)
            end: End time (RFC3339 or Unix timestamp)
            step: Query resolution step (e.g., "15s", "1m")

        Returns:
            Query result dict or None if failed
        """
        try:
            params = {
                "query": query,
                "start": start,
                "end": end,
                "step": step
            }
            response = self.session.get(
                f"{self.url}/api/v1/query_range",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Query range failed for '{query}': {e}")
            return None

    def query_instant(self, query: str, time: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Execute instant PromQL query.

        Args:
            query: PromQL query string
            time: Evaluation timestamp (optional, defaults to now)

        Returns:
            Query result dict or None if failed
        """
        try:
            params = {"query": query}
            if time:
                params["time"] = time

            response = self.session.get(
                f"{self.url}/api/v1/query",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Instant query failed for '{query}': {e}")
            return None

    def get_targets(self) -> Optional[Dict[str, Any]]:
        """
        Get current scrape targets and their status.

        Returns:
            Dict with active and dropped targets, or None if failed
        """
        try:
            response = self.session.get(f"{self.url}/api/v1/targets", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get targets: {e}")
            return None

    def get_config(self) -> Optional[str]:
        """
        Get current Prometheus configuration as YAML string.

        Returns:
            YAML config string or None if failed
        """
        try:
            response = self.session.get(f"{self.url}/api/v1/status/config", timeout=10)
            response.raise_for_status()
            result = response.json()
            return result.get("data", {}).get("yaml")
        except Exception as e:
            logger.error(f"Failed to get config: {e}")
            return None

    def get_metadata(self, metric: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get metadata about metrics.

        Args:
            metric: Specific metric name (optional, returns all if not provided)

        Returns:
            Metadata dict or None if failed
        """
        try:
            params = {}
            if metric:
                params["metric"] = metric

            response = self.session.get(
                f"{self.url}/api/v1/metadata",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get metadata: {e}")
            return None

    def check_target_health(self, job_name: str) -> Dict[str, Any]:
        """
        Check health of specific scrape target.

        Args:
            job_name: Name of the scrape job

        Returns:
            Dict with health info: {"healthy": bool, "targets": [...]} 
        """
        targets_data = self.get_targets()
        if not targets_data:
            return {"healthy": False, "targets": [], "error": "Failed to fetch targets"}

        active_targets = targets_data.get("data", {}).get("activeTargets", [])
        job_targets = [t for t in active_targets if t.get("labels", {}).get("job") == job_name]

        if not job_targets:
            return {"healthy": False, "targets": [], "error": f"No targets found for job '{job_name}'"}

        all_healthy = all(t.get("health") == "up" for t in job_targets)

        return {
            "healthy": all_healthy,
            "targets": job_targets,
            "count": len(job_targets),
            "up_count": sum(1 for t in job_targets if t.get("health") == "up")
        }
