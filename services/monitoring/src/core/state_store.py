# services/monitoring/core/state_store.py
from __future__ import annotations
from pathlib import Path
import json
from typing import Dict, Any


class StateStore:
    """
    Minimal persistent store for a monitoring *session*.
    Writes one JSON per session under <root>/<session_id>/.state.json
    """

    def __init__(self, root: str | Path = "services/monitoring/state") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _sid_dir(self, session_id: str) -> Path:
        d = self.root / session_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _sid_file(self, session_id: str) -> Path:
        return self._sid_dir(session_id) / ".state.json"

    def read(self, session_id: str) -> Dict[str, Any]:
        f = self._sid_file(session_id)
        if not f.exists():
            return {}
        return json.loads(f.read_text(encoding="utf-8"))

    def write(self, session_id: str, data: Dict[str, Any]) -> None:
        f = self._sid_file(session_id)
        f.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def merge(self, session_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        cur = self.read(session_id)
        cur.update(patch)
        self.write(session_id, cur)
        return cur

    def clear(self, session_id: str) -> None:
        d = self._sid_dir(session_id)
        f = d / ".state.json"
        if f.exists():
            f.unlink()
        # keep directory (it may hold generated files)

    def list_all(self) -> list[Dict[str, Any]]:
        """
        List all sessions by scanning the state directory.
        
        Returns:
            List of session state dictionaries
        """
        sessions = []
        if not self.root.exists():
            return sessions
        
        for session_dir in self.root.iterdir():
            if session_dir.is_dir():
                state_file = session_dir / ".state.json"
                if state_file.exists():
                    try:
                        data = json.loads(state_file.read_text(encoding="utf-8"))
                        sessions.append(data)
                    except (json.JSONDecodeError, OSError):
                        continue
        
        return sessions
