import socket
import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import tempfile
from pathlib import Path
from unittest import mock

from services.monitoring.main import MonitoringService


# --- tiny in-process "Prometheus" for tests -----------------------------------

def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    _, port = s.getsockname()
    s.close()
    return port

class FakePromHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/-/ready"):
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK"); return
        if self.path.startswith("/api/v1/query_range"):
            # Return small, valid Prometheus API shape
            payload = {
                "status": "success",
                "data": {"resultType": "matrix", "result": [
                    {"metric": {}, "values": [[0,"1"], [1,"2"]]}
                ]}
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        self.send_response(404); self.end_headers()

    def log_message(self, *a, **k):  # silence
        return

def start_fake_prom(port):
    srv = HTTPServer(("0.0.0.0", port), FakePromHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv

# --- tests --------------------------------------------------------------------

class _FakeSlurm:
    def submit(self, *a, **k): return "12345"
    def status(self, jobid): return {"jobid": jobid, "state": "R"}
    def cancel(self, jobid): return True

@mock.patch("services.monitoring.managers.prometheus.SlurmRunner", _FakeSlurm)
def test_end_to_end_session_register_start_collect_stop_delete():
    # start fake Prometheus
    port = _free_port()
    srv = start_fake_prom(port)
    try:
        with tempfile.TemporaryDirectory() as td:
            svc = MonitoringService(state_dir=td, logs_dir=Path(td)/"logs")

            # create session pointing to fake Prometheus
            out = svc.create_session({"run_id":"sid1","prometheus_port":port,"prom_host":"127.0.0.1"})
            assert out["status"] == "CREATED"

            # register one client + one service endpoint
            svc.register_client({
                "session_id":"sid1","client_id":"c1","node":"nodeA",
                "exporters":{"node":None,"dcgm":None},
                "preferences":{"enable_node": False, "enable_dcgm": False}
            })
            svc.register_service({
                "session_id":"sid1","client_id":"c1","name":"svcA",
                "endpoint":"http://nodeA:8000/metrics","labels":{}
            })

            # readiness will hit our fake /-/ready
            s = svc.start("sid1")
            assert s["status"] == "RUNNING"

            # status should report ready=True
            st = svc.status("sid1")
            assert st["prom_ready"] is True

            # collect will call our fake /api/v1/query_range
            art = svc.collect("sid1", ("2025-01-01T00:00:00Z", "2025-01-01T00:10:00Z"),
                              out_dir=str(Path(td)/"out"), run_id="run01")
            assert Path(art["artifacts"]["tables"]).exists()

            assert svc.stop("sid1") is True
            assert svc.delete("sid1") is True
    finally:
        srv.shutdown()
