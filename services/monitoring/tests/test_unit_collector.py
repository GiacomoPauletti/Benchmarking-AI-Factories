import tempfile
from pathlib import Path
from unittest import mock

from services.monitoring.metrics.collector_agg import CollectorAgg


def test_collector_agg_collect_and_save():
    def fake_get_json(endpoint, params, timeout=20):
        q = params["query"]
        if "http_requests_total" in q:
            return {"status":"success","data":{"result":[{"values":[[0,"1"],[1,"2"],[2,"3"]]}]}}
        if "node_cpu_seconds_total" in q:
            return {"status":"success","data":{"result":[{"values":[[0,"0.9"],[1,"0.8"]]}]}}
        if "DCGM_FI_DEV_GPU_UTIL" in q:
            return {"status":"success","data":{"result":[{"values":[[0,"50"],[1,"70"]]}]}}
        if "histogram_quantile(0.50" in q:
            return {"status":"success","data":{"result":[{"values":[[0,"0.100"],[1,"0.200"]]}]}}
        if "histogram_quantile(0.95" in q:
            return {"status":"success","data":{"result":[{"values":[[0,"0.300"]]}]}}
        if "histogram_quantile(0.99" in q:
            return {"status":"success","data":{"result":[{"values":[[0,"0.400"]]}]}}
        return {"status":"success","data":{"result":[]}}

    coll = CollectorAgg("http://fake-prom:9090")
    with mock.patch.object(CollectorAgg, "_get_json", side_effect=fake_get_json):
        summary = coll.collect_window("2025-01-01T00:00:00Z","2025-01-01T00:10:00Z")
        assert summary["throughput_qps"] == 2.0
        assert summary["cpu_util_avg_pct"] == 100.0 * (1 - 0.85)
        assert summary["gpu_util_avg_pct"] == 60.0
        assert round(summary["latency_p50_ms"]) == 150

        with tempfile.TemporaryDirectory() as td:
            art = coll.save(summary, Path(td), "run01", "sidX",
                            "2025-01-01T00:00:00Z","2025-01-01T00:10:00Z")
            assert Path(art["tables"]).exists()
            assert Path(art["manifest"]).exists()
