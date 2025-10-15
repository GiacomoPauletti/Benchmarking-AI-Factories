# services/monitoring/managers/prometheus.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
from urllib import request, error
import time

from .slurm import SlurmRunner


class PrometheusManager:
    """
    Starts/stops Prometheus via SlurmRunner and checks readiness.
    Assumes 'prometheus' binary is in PATH on the allocated node.
    """

    def __init__(self, slurm: SlurmRunner) -> None:
        self.slurm = slurm

    def start(self,
              config_path: Path,
              port: int,
              storage_dir: Path,
              job_name: str = "prometheus",
              partition: Optional[str] = None,
              time_limit: str = "04:00:00") -> str:
        storage_dir.mkdir(parents=True, exist_ok=True)
        cmd = (
            f"prometheus "
            f"--config.file={config_path} "
            f"--web.enable-lifecycle "
            f"--web.listen-address=:{port} "
            f"--storage.tsdb.path={storage_dir} "
            f"--storage.tsdb.retention.time=6h"
        )
        jobid = self.slurm.submit(
            command=cmd, job_name=job_name, partition=partition, time=time_limit, nodes=1
        )
        return jobid

    def is_ready(self, base_url: str, timeout_s: int = 30) -> bool:
        url = base_url.rstrip("/") + "/-/ready"
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            try:
                with request.urlopen(url, timeout=3) as resp:
                    if 200 <= resp.status < 300:
                        return True
            except error.URLError:
                time.sleep(1)
        return False

    def stop(self, jobid: str) -> bool:
        return self.slurm.cancel(jobid)
