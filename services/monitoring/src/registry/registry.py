# services/monitoring/registry/registry.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
import json


class Registry:
    """
    Canonical store of clients/services/exporters for a given session.
    Saved under <root>/<session_id>/registry.json
    """

    def __init__(self, root: str | Path = "services/monitoring/state") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _file(self, session_id: str) -> Path:
        d = self.root / session_id
        d.mkdir(parents=True, exist_ok=True)
        return d / "registry.json"

    def _load(self, session_id: str) -> Dict[str, Any]:
        f = self._file(session_id)
        if not f.exists():
            return {"clients": {}, "services": []}
        return json.loads(f.read_text(encoding="utf-8"))

    def _save(self, session_id: str, data: Dict[str, Any]) -> None:
        self._file(session_id).write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ---- mutations ----
    def upsert_client(self, info: Dict[str, Any]) -> None:
        """
        info: {
          "session_id": "...",
          "client_id": "client-001",
          "node": "nodeA",
          "exporters": {"node":"nodeA:9100","dcgm":"nodeA:9400"},
          "preferences": {"enable_node": true, "enable_dcgm": true}
        }
        """
        sid = info["session_id"]
        cid = info["client_id"]
        data = self._load(sid)
        data.setdefault("clients", {})
        data["clients"][cid] = info
        self._save(sid, data)

    def upsert_service(self, svc: Dict[str, Any]) -> None:
        """
        svc: {
          "session_id": "...",
          "client_id": "client-001",
          "name": "triton",
          "endpoint": "http://nodeA:8000/metrics",
          "labels": {...}
        }
        """
        sid = svc["session_id"]
        data = self._load(sid)
        arr = data.setdefault("services", [])
        # replace by (client_id, name)
        arr = [s for s in arr if not (s["client_id"] == svc["client_id"] and s["name"] == svc["name"])]
        arr.append(svc)
        data["services"] = arr
        self._save(sid, data)

    def remove_service(self, session_id: str, client_id: str, name: str) -> None:
        data = self._load(session_id)
        data["services"] = [s for s in data.get("services", []) if not (s["client_id"] == client_id and s["name"] == name)]
        self._save(session_id, data)

    def clear_session_targets(self, session_id: str) -> None:
        """
        Clear all targets (clients and services) for a session.
        This is used when stopping a session to remove targets from Prometheus.
        """
        data = self._load(session_id)
        data["clients"] = {}
        data["services"] = []
        self._save(session_id, data)

    # ---- read model for renderer ----
    def list_targets(self, session_id: str) -> Dict[str, Any]:
        d = self._load(session_id)
        nodes = []
        dcgms = []
        for c in d.get("clients", {}).values():
            if c.get("preferences", {}).get("enable_node", True) and c.get("exporters", {}).get("node"):
                nodes.append(c["exporters"]["node"])
            if c.get("preferences", {}).get("enable_dcgm", True) and c.get("exporters", {}).get("dcgm"):
                dcgms.append(c["exporters"]["dcgm"])

        services: List[Dict[str, str]] = [
            {"name": s["name"], "url": s["endpoint"]} for s in d.get("services", [])
        ]
        return {"node": nodes, "dcgm": dcgms, "services": services}
