# services/monitoring/main.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Tuple
from datetime import datetime
import uuid

from .core.state_store import StateStore
from .config.renderer import ConfigRenderer
from .managers.slurm import SlurmRunner
from .managers.prometheus import PrometheusManager
from .registry.registry import Registry
from .metrics.collector_agg import CollectorAgg


class MonitoringService:
    """
    Facade that coordinates state, registry, Prometheus start/stop, config rendering,
    and metrics collection.

    Assumptions (MVP):
    - Prometheus runs via Slurm on a node reachable at http(s)://<prom_host>:<port>.
      Pass prom_host at session creation if not 'localhost'.
    - Exporters (node/dcgm) are already running or their targets are simply URLs.
    """

    def __init__(self,
                 state_dir: str | Path = "services/monitoring/state",
                 logs_dir: str | Path = "logs") -> None:
        self.state = StateStore(state_dir)
        self.registry = Registry(state_dir)
        self.slurm = SlurmRunner(logs_dir)
        self.prom = PrometheusManager(self.slurm)

    # -------------------- Session lifecycle --------------------

    def create_session(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        cfg: {
          "run_id": str (optional),
          "scrape_interval": "1s",
          "retention_hours": int (unused here),
          "prometheus_port": 9090,
          "prom_host": "localhost"  # IMPORTANT in HPC if Prometheus runs on a known host
        }
        """
        sid = cfg.get("run_id") or f"mon-{uuid.uuid4().hex[:8]}"
        workdir = Path(self.state.root) / sid
        workdir.mkdir(parents=True, exist_ok=True)

        prom_port = int(cfg.get("prometheus_port", 9090))
        prom_host = cfg.get("prom_host", "localhost")
        prom_url = f"http://{prom_host}:{prom_port}"

        # initial empty config
        renderer = ConfigRenderer(workdir)
        cfg_path = renderer.render(self.registry.list_targets(sid), cfg.get("scrape_interval", "1s"))

        self.state.write(sid, {
            "session_id": sid,
            "status": "CREATED",
            "workdir": str(workdir),
            "prometheus_port": prom_port,
            "prom_host": prom_host,
            "prometheus_url": prom_url,
            "config_path": str(cfg_path),
            "job_ids": {},
            "created_at": datetime.utcnow().isoformat() + "Z",
        })
        return {"session_id": sid, "prometheus_url": prom_url, "status": "CREATED", "workdir": str(workdir)}

    def start(self, session_id: str, partition: str | None = None, time_limit: str = "04:00:00") -> Dict[str, Any]:
        st = self.state.read(session_id)
        if not st:
            raise ValueError(f"Unknown session_id: {session_id}")

        workdir = Path(st["workdir"])
        renderer = ConfigRenderer(workdir)
        targets = self.registry.list_targets(session_id)
        cfg_path = renderer.render(targets, "1s")

        prom_port = int(st["prometheus_port"])
        jobid = self.prom.start(Path(cfg_path), prom_port, workdir / "prom_data",
                                job_name=f"prom_{session_id}", partition=partition, time_limit=time_limit)

        # Wait until ready
        prom_url = st["prometheus_url"]
        self.prom.is_ready(prom_url, timeout_s=30)

        self.state.merge(session_id, {"status": "RUNNING", "job_ids": {"prometheus": jobid}})
        return {"status": "RUNNING", "job_ids": {"prometheus": jobid}, "prometheus_url": prom_url}

    def status(self, session_id: str) -> Dict[str, Any]:
        st = self.state.read(session_id)
        if not st:
            raise ValueError(f"Unknown session_id: {session_id}")
        jobid = st.get("job_ids", {}).get("prometheus")
        sj = self.slurm.status(jobid) if jobid else {"state": "N/A"}
        ready = self.prom.is_ready(st["prometheus_url"], timeout_s=3)
        return {"status": st.get("status", "UNKNOWN"), "job": sj, "prom_ready": ready}

    def stop(self, session_id: str) -> bool:
        st = self.state.read(session_id)
        jobid = st.get("job_ids", {}).get("prometheus")
        ok = self.prom.stop(jobid) if jobid else True
        self.state.merge(session_id, {"status": "STOPPED", "stopped_at": datetime.utcnow().isoformat() + "Z"})
        return ok

    def delete(self, session_id: str) -> bool:
        # *Does not* remove results, only the state dir file
        self.state.clear(session_id)
        return True

    # -------------------- Targets registry (from clients/services) --------------------

    def register_client(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        req: {
          "session_id": "...",
          "client_id": "client-001",
          "node": "nodeA",
          "exporters": {"node":"nodeA:9100","dcgm":"nodeA:9400"},
          "preferences": {"enable_node": true, "enable_dcgm": true}
        }
        """
        self.registry.upsert_client(req)
        st = self.state.read(req["session_id"])
        if st.get("status") == "RUNNING":
            # hot reload config
            workdir = Path(st["workdir"])
            renderer = ConfigRenderer(workdir)
            cfg_path = renderer.render(self.registry.list_targets(req["session_id"]), "1s")
            renderer.reload(st["prometheus_url"])
            self.state.merge(req["session_id"], {"config_path": str(cfg_path)})
        return {"ok": True, "client_id": req["client_id"]}

    def register_service(self, svc: Dict[str, Any]) -> Dict[str, Any]:
        """
        svc: {
          "session_id":"...", "client_id":"c1",
          "name":"triton", "endpoint":"http://nodeA:8000/metrics", "labels": {...}
        }
        """
        self.registry.upsert_service(svc)
        st = self.state.read(svc["session_id"])
        if st.get("status") == "RUNNING":
            workdir = Path(st["workdir"])
            renderer = ConfigRenderer(workdir)
            cfg_path = renderer.render(self.registry.list_targets(svc["session_id"]), "1s")
            renderer.reload(st["prometheus_url"])
            self.state.merge(svc["session_id"], {"config_path": str(cfg_path)})
        return {"ok": True, "name": svc["name"]}

    # -------------------- Collection --------------------

    def collect(self, session_id: str, window: Tuple[str, str], out_dir: str, run_id: str = "run") -> Dict[str, Any]:
        st = self.state.read(session_id)
        if not st:
            raise ValueError(f"Unknown session_id: {session_id}")
        prom_url = st["prometheus_url"]
        coll = CollectorAgg(prom_url)
        summary = coll.collect_window(window[0], window[1])
        artifacts = coll.save(summary, Path(out_dir), run_id, session_id, window[0], window[1])
        self.state.merge(session_id, {"last_collect_at": datetime.utcnow().isoformat() + "Z", "artifacts": artifacts})
        return {"artifacts": artifacts}
