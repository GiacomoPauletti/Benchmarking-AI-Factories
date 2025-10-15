import tempfile
from pathlib import Path
from unittest import mock

from services.monitoring.core.state_store import StateStore
from services.monitoring.registry.registry import Registry
from services.monitoring.config.renderer import ConfigRenderer


def test_state_store_rw_merge_clear():
    with tempfile.TemporaryDirectory() as td:
        st = StateStore(td)
        st.write("s1", {"a": 1})
        assert st.read("s1")["a"] == 1
        st.merge("s1", {"b": 2})
        d = st.read("s1")
        assert d["a"] == 1 and d["b"] == 2
        st.clear("s1")
        assert st.read("s1") == {}


def test_registry_targets_building():
    with tempfile.TemporaryDirectory() as td:
        reg = Registry(td)
        reg.upsert_client({
            "session_id": "sid",
            "client_id": "c1",
            "node": "nodeA",
            "exporters": {"node": "nodeA:9100", "dcgm": "nodeA:9400"},
            "preferences": {"enable_node": True, "enable_dcgm": True},
        })
        reg.upsert_service({
            "session_id": "sid",
            "client_id": "c1",
            "name": "triton",
            "endpoint": "http://nodeA:8000/metrics",
            "labels": {}
        })
        targets = reg.list_targets("sid")
        assert "nodeA:9100" in targets["node"]
        assert "nodeA:9400" in targets["dcgm"]
        assert any(s["url"].endswith(":8000/metrics") for s in targets["services"])


def test_renderer_generates_yaml_and_reload_ok():
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        r = ConfigRenderer(workdir)
        targets = {
            "node": ["nodeA:9100"],
            "dcgm": [],
            "services": [{"name": "svc", "url": "http://h:1/metrics"}],
        }
        cfg = r.render(targets, "1s")
        content = Path(cfg).read_text()
        assert "scrape_configs:" in content and "nodeA:9100" in content

        with mock.patch("urllib.request.urlopen") as m:
            m.return_value.__enter__.return_value.status = 200
            assert r.reload("http://localhost:9090") is True
