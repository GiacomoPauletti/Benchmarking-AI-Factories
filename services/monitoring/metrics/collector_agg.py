# services/monitoring/metrics/collector_agg.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Tuple
from urllib import parse, request, error
import csv
import json
import statistics
from datetime import datetime


class CollectorAgg:
    """
    Minimal collector+aggregator in one class.
    - Calls Prometheus HTTP API /api/v1/query_range
    - Aggregates into a compact summary (p50/p95/p99 where possible, throughput, cpu/gpu, etc.)
    - Saves CSV + MANIFEST.json
    No pandas, no external deps.
    """

    def __init__(self, prom_url: str) -> None:
        self.base = prom_url.rstrip("/")

    # -------- HTTP helpers --------
    def _get_json(self, endpoint: str, params: Dict[str, str], timeout: int = 20) -> Dict[str, Any]:
        url = self.base + endpoint + "?" + parse.urlencode(params)
        with request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _series_values(self, data: Dict[str, Any]) -> List[Tuple[float, float]]:
        """Return [(ts, value_float), ...] from a range_query result (one or many series)."""
        vals: List[Tuple[float, float]] = []
        if data.get("status") != "success":
            return vals
        for res in data.get("data", {}).get("result", []):
            for ts, v in res.get("values", []):
                try:
                    vals.append((float(ts), float(v)))
                except ValueError:
                    continue
        return vals

    # -------- queries --------
    def query_range(self, expr: str, start_iso: str, end_iso: str, step: str = "1s") -> List[Tuple[float, float]]:
        payload = {
            "query": expr,
            "start": start_iso,
            "end": end_iso,
            "step": step,
        }
        try:
            data = self._get_json("/api/v1/query_range", payload)
            return self._series_values(data)
        except error.URLError:
            return []

    # -------- aggregation helpers --------
    @staticmethod
    def _percentile(samples: List[float], p: float) -> float | None:
        if not samples:
            return None
        k = max(0, min(len(samples) - 1, int(round(p * (len(samples) - 1)))))
        return sorted(samples)[k]

    def collect_window(self, start_iso: str, end_iso: str) -> Dict[str, Any]:
        """
        Pull a basic set of metrics. If a metric doesn't exist, we return None.
        """
        # Throughput (generic): try http_requests_total rate as a baseline
        th_series = self.query_range('sum(rate(http_requests_total[1m]))', start_iso, end_iso, step="15s")
        throughput = statistics.mean([v for _, v in th_series]) if th_series else None

        # CPU util (node_exporter)
        cpu_series = self.query_range('1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))', start_iso, end_iso, step="15s")
        cpu_util = 100.0 * statistics.mean([v for _, v in cpu_series]) if cpu_series else None

        # GPU util (dcgm)
        gpu_series = self.query_range('avg(DCGM_FI_DEV_GPU_UTIL)', start_iso, end_iso, step="15s")
        gpu_util = statistics.mean([v for _, v in gpu_series]) if gpu_series else None

        # A generic request duration metric (if present)
        lat_series = self.query_range(
            'histogram_quantile(0.50, sum by (le) (rate(http_server_request_duration_seconds_bucket[1m])))',
            start_iso, end_iso, step="15s")
        lat_p50 = statistics.mean([v * 1000.0 for _, v in lat_series]) if lat_series else None

        lat95_series = self.query_range(
            'histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket[1m])))',
            start_iso, end_iso, step="15s")
        lat_p95 = statistics.mean([v * 1000.0 for _, v in lat95_series]) if lat95_series else None

        lat99_series = self.query_range(
            'histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket[1m])))',
            start_iso, end_iso, step="15s")
        lat_p99 = statistics.mean([v * 1000.0 for _, v in lat99_series]) if lat99_series else None

        return {
            "throughput_qps": throughput,
            "cpu_util_avg_pct": cpu_util,
            "gpu_util_avg_pct": gpu_util,
            "latency_p50_ms": lat_p50,
            "latency_p95_ms": lat_p95,
            "latency_p99_ms": lat_p99,
        }

    def save(self, summary: Dict[str, Any], out_dir: Path, run_id: str, session_id: str,
             start_iso: str, end_iso: str) -> Dict[str, str]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        # CSV (one row)
        csv_path = out / "metrics_summary.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "run_id", "session_id", "from", "to",
                "throughput_qps", "cpu_util_avg_pct", "gpu_util_avg_pct",
                "latency_p50_ms", "latency_p95_ms", "latency_p99_ms"
            ])
            writer.writeheader()
            row = {"run_id": run_id, "session_id": session_id, "from": start_iso, "to": end_iso}
            row.update(summary)
            writer.writerow(row)

        # MANIFEST
        manifest = {
            "run_id": run_id,
            "session_id": session_id,
            "generated_at_utc": datetime.utcnow().isoformat() + "Z",
            "window": {"from": start_iso, "to": end_iso},
            "files": {"summary_csv": str(csv_path)},
        }
        manifest_path = out / "MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return {"tables": str(csv_path), "manifest": str(manifest_path)}
