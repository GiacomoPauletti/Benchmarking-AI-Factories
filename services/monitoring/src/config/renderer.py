# services/monitoring/config/renderer.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, List
from urllib import request, error
from urllib.parse import urlparse
import textwrap
import json

class ConfigRenderer:
    """
    Renders a Prometheus configuration (prometheus.yml) from in-memory targets
    and optionally hot-reloads Prometheus via /-/reload (requires --web.enable-lifecycle).
    """

    def __init__(self, workdir: str | Path) -> None:
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _yaml_targets(self, xs: List[str]) -> str:
        if not xs:
            return "[]"
        return "\n".join([f"      - {json.dumps(x)}" for x in xs])

    def _render_service_jobs(self, services: List[Dict]) -> str:
        """
        Render job entries for services (without the leading dash, for inclusion in scrape_configs list).
        Each service gets its own job with proper metrics_path.
        
        Args:
            services: List of dicts with 'name' and 'url' keys
                     where url is like "http://server:8001/api/v1/services/123/metrics"
        
        Returns:
            YAML string for service job configs (indented, without leading list marker)
        """
        if not services:
            return ""
        
        jobs = []
        for svc in services:
            url = svc["url"]
            name = svc["name"]
            
            # Parse the URL to extract components
            parsed = urlparse(url)
            scheme = parsed.scheme or "http"
            netloc = parsed.netloc
            path = parsed.path or "/metrics"
            
            # Create a job for this service (properly indented as part of scrape_configs list)
            job = f"""  - job_name: "{name}"
    scheme: {scheme}
    metrics_path: {json.dumps(path)}
    static_configs:
      - targets: [{json.dumps(netloc)}]"""
            jobs.append(job)
        
        return "\n".join(jobs)

    def render(self, targets: Dict, scrape_interval: str = "1s", output_path: Path = None) -> Path:
        """
        Render Prometheus configuration from targets.
        
        Args:
            targets: Dictionary with node/dcgm/services targets
            scrape_interval: How often Prometheus scrapes (e.g., "15s")
            output_path: Optional path to write config (defaults to workdir/prometheus.yml)
        
        Returns:
            Path to the rendered prometheus.yml file
            
        Note:
            This method only renders the YAML file. To hot-reload Prometheus,
            use PrometheusManager.reload_config() separately.
        """
        content = textwrap.dedent(f"""
        global:
          scrape_interval: {scrape_interval}

        scrape_configs:
          - job_name: "node"
            static_configs:
              - targets: {self._yaml_targets(targets.get("node", []))}
          - job_name: "dcgm"
            static_configs:
              - targets: {self._yaml_targets(targets.get("dcgm", []))}
        """).strip()
        
        # Add service jobs
        service_jobs = self._render_service_jobs(targets.get("services", []))
        if service_jobs:
            content += "\n" + service_jobs
        
        content += "\n"

        out = output_path if output_path else (self.workdir / "prometheus.yml")
        out.write_text(content, encoding="utf-8")
        return out

