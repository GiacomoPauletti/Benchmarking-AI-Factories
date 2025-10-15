# services/monitoring/config/renderer.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, List
from urllib import request, error
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

    def _yaml_services(self, services: List[Dict]) -> str:
        lst = [s["url"] for s in services] if services else []
        return self._yaml_targets(lst)

    def render(self, targets: Dict, scrape_interval: str = "1s") -> Path:
        """
        targets = {"node":[host:port,...], "dcgm":[host:port,...], "services":[{"name","url"},...]}
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
          - job_name: "services"
            static_configs:
              - targets: {self._yaml_services(targets.get("services", []))}
        """).strip() + "\n"

        out = self.workdir / "prometheus.yml"
        out.write_text(content, encoding="utf-8")
        return out

    def reload(self, prometheus_url: str, timeout: int = 5) -> bool:
        """POST to /-/reload. Prometheus must be started with --web.enable-lifecycle."""
        url = prometheus_url.rstrip("/") + "/-/reload"
        req = request.Request(url, method="POST")
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                return 200 <= resp.status < 300
        except error.URLError:
            return False
