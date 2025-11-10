"""
Core logic for the monitoring service.
Coordinates Prometheus-based metrics collection (local deployment).
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from datetime import datetime
import uuid
import logging

from .core.state_store import StateStore
from .core.settings import settings
from .config.renderer import ConfigRenderer
from .managers.prometheus_manager import PrometheusManager
from .registry.registry import Registry
from .metrics.collector_agg import CollectorAgg


class MonitoringService:
    """
    Main monitoring service class that coordinates Prometheus configuration,
    target registry, and metrics collection.

    Architecture (Local Deployment):
    - Prometheus runs as a Docker service (managed by docker-compose)
    - MonitoringService manages Prometheus configuration and hot-reloads it
    - Metrics are scraped from local services and proxied SLURM services
    - No SLURM dependency for Prometheus itself
    """

    def __init__(
        self,
        prometheus_url: Optional[str] = None,
        config_path: Optional[Path] = None,
        state_dir: Optional[Path] = None
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing MonitoringService (local deployment mode)")
        
        # Use settings or override
        self.prometheus_url = prometheus_url or settings.prometheus_url
        self.config_path = config_path or settings.prometheus_config_path
        self.state_dir = state_dir or settings.state_dir
        
        # Initialize components
        self.state = StateStore(self.state_dir)
        self.registry = Registry(self.state_dir)
        self.prom = PrometheusManager(self.prometheus_url, self.config_path)
        
        # Ensure directories exist
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Prometheus URL: {self.prometheus_url}")
        self.logger.info(f"Config path: {self.config_path}")

    # -------------------- Helper methods --------------------

    def _get_active_session(self) -> Optional[Dict[str, Any]]:
        """
        Find the currently active (RUNNING) session.
        
        In single-session mode, only one session can be RUNNING at a time.
        
        Returns:
            Active session dict or None if no active session
        """
        all_sessions = self.state.list_all()
        for session in all_sessions:
            if session.get("status") == "RUNNING":
                return session
        return None

    # -------------------- Session lifecycle --------------------

    def create_session(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new monitoring session and activate it immediately.
        
        SINGLE-SESSION MODE: Only one session can be RUNNING at a time.
        If there's already an active session, this will raise an error.
        
        In local deployment, this:
        1. Checks for existing RUNNING session (raises error if found)
        2. Creates session metadata and workspace
        3. Renders Prometheus config with any pre-registered targets
        4. Hot-reloads Prometheus to activate the session
        5. Verifies Prometheus is ready
        
        Args:
            cfg: Configuration dictionary with:
                - run_id (str, optional): Session identifier (auto-generated if not provided)
                - scrape_interval (str, optional): Prometheus scrape interval (default: "15s")
                - labels (dict, optional): Additional labels for this session
        
        Returns:
            Dictionary with session_id, prometheus_url, status, workdir, and targets_count
            
        Raises:
            RuntimeError: If another session is already RUNNING
        """
        # Enforce single-session mode
        active_session = self._get_active_session()
        if active_session:
            raise RuntimeError(
                f"Cannot create new session: session '{active_session['session_id']}' is already RUNNING. "
                f"Stop it first with stop('{active_session['session_id']}') before creating a new session."
            )
        
        sid = cfg.get("run_id") or f"mon-{uuid.uuid4().hex[:8]}"
        workdir = Path(self.state_dir) / sid
        workdir.mkdir(parents=True, exist_ok=True)

        scrape_interval = cfg.get("scrape_interval", settings.default_scrape_interval)
        
        # Get any pre-registered targets for this session
        targets = self.registry.list_targets(sid)
        
        # Render config directly to the shared Prometheus config location
        renderer = ConfigRenderer(workdir)
        cfg_path = renderer.render(
            targets, 
            scrape_interval,
            output_path=self.config_path
        )

        # Hot-reload Prometheus to pick up new config
        if not self.prom.reload_config():
            raise RuntimeError("Failed to reload Prometheus configuration")

        # Verify Prometheus is ready
        if not self.prom.is_ready(timeout_s=10):
            raise RuntimeError("Prometheus is not ready")

        session_data = {
            "session_id": sid,
            "status": "RUNNING",
            "workdir": str(workdir),
            "prometheus_url": self.prometheus_url,
            "config_path": str(cfg_path),
            "scrape_interval": scrape_interval,
            "labels": cfg.get("labels", {}),
            "created_at": datetime.utcnow().isoformat() + "Z",
            "started_at": datetime.utcnow().isoformat() + "Z",
        }
        
        self.state.write(sid, session_data)
        
        self.logger.info(f"Created and started monitoring session {sid} with {len(targets)} targets")
        return {
            "session_id": sid, 
            "prometheus_url": self.prometheus_url, 
            "status": "RUNNING", 
            "workdir": str(workdir),
            "targets_count": len(targets)
        }

    def start(self, session_id: str) -> Dict[str, Any]:
        """
        DEPRECATED: Sessions are now started automatically when created.
        
        This method is kept for backward compatibility but simply returns
        the session status. Use create_session() instead.
        
        Args:
            session_id: The session identifier
        
        Returns:
            Dictionary with status and prometheus_url
        """
        import warnings
        warnings.warn(
            "MonitoringService.start() is deprecated. Sessions are now started "
            "automatically when created. Use create_session() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.status(session_id)

    def status(self, session_id: str) -> Dict[str, Any]:
        """
        Get the status of a monitoring session.
        
        Args:
            session_id: The session identifier
        
        Returns:
            Dictionary with status and Prometheus health
        """
        st = self.state.read(session_id)
        if not st:
            raise ValueError(f"Unknown session_id: {session_id}")
        
        # Check Prometheus health
        prom_healthy = self.prom.is_healthy()
        prom_ready = self.prom.is_ready(timeout_s=3)
        
        # Get target count
        targets = self.registry.list_targets(session_id)
        
        return {
            "session_id": session_id,
            "status": st.get("status", "UNKNOWN"),
            "prometheus": {
                "url": self.prometheus_url,
                "healthy": prom_healthy,
                "ready": prom_ready
            },
            "targets_count": len(targets),
            "created_at": st.get("created_at"),
            "started_at": st.get("started_at")
        }

    def stop(self, session_id: str) -> bool:
        """
        Stop a monitoring session.
        
        Marks the session as stopped and removes its targets from Prometheus config.
        Prometheus continues running but stops scraping this session's targets.
        
        Args:
            session_id: The session identifier
        
        Returns:
            True if successful
        """
        st = self.state.read(session_id)
        if not st:
            raise ValueError(f"Unknown session_id: {session_id}")
        
        # Get target count before clearing (for logging)
        targets_before = self.registry.list_targets(session_id)
        num_targets = (
            len(targets_before.get("node", [])) + 
            len(targets_before.get("dcgm", [])) + 
            len(targets_before.get("services", []))
        )
        
        # Clear targets for this session from registry
        # This removes them from future Prometheus configs
        self.registry.clear_session_targets(session_id)
        
        # Mark session as stopped
        self.state.merge(session_id, {
            "status": "STOPPED", 
            "stopped_at": datetime.utcnow().isoformat() + "Z"
        })
        
        # Regenerate Prometheus config without this session's targets
        workdir = Path(st.get("workdir", self.state_dir / session_id))
        renderer = ConfigRenderer(workdir)
        
        # Aggregate all remaining targets from other RUNNING sessions (if any)
        combined_targets = {"node": [], "dcgm": [], "services": []}
        for session in self.state.list_all():
            if session.get("session_id") != session_id and session.get("status") == "RUNNING":
                session_targets = self.registry.list_targets(session["session_id"])
                combined_targets["node"].extend(session_targets.get("node", []))
                combined_targets["dcgm"].extend(session_targets.get("dcgm", []))
                combined_targets["services"].extend(session_targets.get("services", []))
        
        renderer.render(
            combined_targets,
            st.get("scrape_interval", settings.default_scrape_interval),
            output_path=self.config_path
        )
        
        # Hot reload Prometheus to stop scraping stopped session's targets
        self.prom.reload_config()
        
        self.logger.info(f"Stopped monitoring session {session_id} and removed {num_targets} targets from Prometheus config")
        return True

    def delete(self, session_id: str) -> bool:
        """
        Delete a monitoring session (state only, not collected data).
        
        Args:
            session_id: The session identifier
        
        Returns:
            True if successful
        """
        self.state.clear(session_id)
        self.logger.info(f"Deleted monitoring session {session_id}")
        return True

    def list_sessions(self) -> list[Dict[str, Any]]:
        """
        List all monitoring sessions.
        
        Returns:
            List of session dictionaries sorted by creation time (newest first)
        """
        sessions = self.state.list_all()
        # Sort by created_at descending (newest first)
        sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return sessions

    # -------------------- Targets registry --------------------

    def register_client(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register a client with its exporters for monitoring.
        
        Args:
            req: Registration request with:
                - session_id: Monitoring session ID
                - client_id: Unique client identifier
                - node: Node name where client runs
                - exporters: Dict of exporter types to endpoints
                - preferences: Dict of enabled exporters
        
        Returns:
            Confirmation dictionary with client_id
        """
        self.registry.upsert_client(req)
        st = self.state.read(req["session_id"])
        
        if st.get("status") == "RUNNING":
            # Hot reload config
            workdir = Path(st["workdir"])
            renderer = ConfigRenderer(workdir)
            renderer.render(
                self.registry.list_targets(req["session_id"]), 
                st.get("scrape_interval", settings.default_scrape_interval),
                output_path=self.config_path
            )
            self.prom.reload_config()
        
        self.logger.info(f"Registered client {req['client_id']} for session {req['session_id']}")
        return {"ok": True, "client_id": req["client_id"]}

    def register_service(self, svc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register a service endpoint for monitoring.
        
        Automatically resolves the metrics endpoint from the Server API using the service_id.
        The service_id is used as the Prometheus job label name.
        
        Args:
            svc: Service registration with:
                - session_id: Monitoring session ID
                - service_id: Server API service ID (used as job label, endpoint auto-resolved)
                - labels (optional): Additional Prometheus labels for filtering/grouping
        
        Returns:
            Confirmation dictionary with service_id and endpoint
            
        Raises:
            ValueError: If service_id is not provided
            RuntimeError: If endpoint resolution from Server API fails
        """
        service_id = svc.get("service_id")
        
        if not service_id:
            raise ValueError("service_id is required for service registration")
        
        # Resolve endpoint from Server API
        endpoint = self._resolve_service_endpoint(service_id)
        svc["endpoint"] = endpoint
        self.logger.info(f"Resolved endpoint for service {service_id}: {endpoint}")
        
        # Set name and client_id to service_id
        svc["name"] = service_id
        svc["client_id"] = service_id
        
        self.registry.upsert_service(svc)
        st = self.state.read(svc["session_id"])
        
        if st.get("status") == "RUNNING":
            workdir = Path(st["workdir"])
            renderer = ConfigRenderer(workdir)
            renderer.render(
                self.registry.list_targets(svc["session_id"]), 
                st.get("scrape_interval", settings.default_scrape_interval),
                output_path=self.config_path
            )
            self.prom.reload_config()
        
        self.logger.info(f"Registered service {service_id} for session {svc['session_id']}")
        return {"ok": True, "service_id": service_id, "endpoint": endpoint}
    
    def _resolve_service_endpoint(self, service_id: str) -> str:
        """
        Resolve a service's metrics endpoint from the Server API.
        
        Uses the generic /api/v1/services/{service_id}/metrics endpoint
        which automatically routes to the appropriate service-specific metrics.
        
        Args:
            service_id: Server API service ID
            
        Returns:
            Metrics endpoint URL (e.g., "http://localhost:8001/api/v1/services/12345/metrics")
            
        Raises:
            RuntimeError: If unable to resolve endpoint
        """
        import requests
        
        # Server API URL from settings
        server_url = settings.server_api_url
        
        try:
            # Verify service exists
            # Increased timeout to 60s to handle slow SLURM API queries via SSH tunnel
            response = requests.get(f"{server_url}/api/v1/services/{service_id}", timeout=60)
            response.raise_for_status()
            
            # Use the generic metrics endpoint - Server API will route based on recipe type
            metrics_endpoint = f"{server_url}/api/v1/services/{service_id}/metrics"
            
            return metrics_endpoint
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to resolve endpoint for service {service_id}: {e}")

    # -------------------- Metrics collection --------------------

    def collect(
        self, 
        session_id: str, 
        window: Tuple[str, str], 
        out_dir: str, 
        run_id: str = "run"
    ) -> Dict[str, Any]:
        """
        Collect metrics for a time window and save to disk.
        
        Args:
            session_id: Monitoring session ID
            window: Tuple of (start_time, end_time) as ISO strings
            out_dir: Output directory for collected metrics
            run_id: Run identifier for the collection
        
        Returns:
            Dictionary with artifacts (file paths)
        """
        st = self.state.read(session_id)
        if not st:
            raise ValueError(f"Unknown session_id: {session_id}")
        
        coll = CollectorAgg(self.prometheus_url)
        summary = coll.collect_window(window[0], window[1])
        artifacts = coll.save(
            summary, 
            Path(out_dir), 
            run_id, 
            session_id, 
            window[0], 
            window[1]
        )
        
        self.state.merge(session_id, {
            "last_collect_at": datetime.utcnow().isoformat() + "Z", 
            "artifacts": artifacts
        })
        
        self.logger.info(f"Collected metrics for session {session_id}, window {window}")
        return {"artifacts": artifacts}
    
    # -------------------- Prometheus queries --------------------
    
    def query_prometheus(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Execute a PromQL query against Prometheus.
        
        Args:
            query: PromQL query string
        
        Returns:
            Query result or None if failed
        """
        return self.prom.query_instant(query)
    
    def get_targets_status(self) -> Optional[Dict[str, Any]]:
        """
        Get status of all Prometheus scrape targets.
        
        Returns:
            Targets status dict or None if failed
        """
        return self.prom.get_targets()
