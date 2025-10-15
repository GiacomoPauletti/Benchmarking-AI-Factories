# services/monitoring/managers/slurm.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional
import subprocess
import shlex
import re
import tempfile


class SlurmRunner:
    """
    Tiny wrapper around sbatch/squeue/scancel.
    """

    def __init__(self, logs_dir: str | Path = "logs") -> None:
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def submit(self,
               command: str,
               job_name: str = "monitor",
               partition: Optional[str] = None,
               time: str = "01:00:00",
               nodes: int = 1,
               gpus: int = 0,
               cpus_per_task: Optional[int] = None,
               mem: Optional[str] = None,
               workdir: str | Path = ".") -> str:
        """
        Writes a temporary sbatch script and submits it.
        Returns the jobid string.
        """
        out_log = self.logs_dir / f"{job_name}-%j.out"
        gres = f"#SBATCH --gpus={gpus}\n" if gpus else ""
        cpus = f"#SBATCH --cpus-per-task={cpus_per_task}\n" if cpus_per_task else ""
        meml = f"#SBATCH --mem={mem}\n" if mem else ""
        part = f"#SBATCH -p {partition}\n" if partition else ""
        script = f"""#!/bin/bash
#SBATCH -J {job_name}
{part}#SBATCH -N {nodes}
#SBATCH -t {time}
{gres}{cpus}{meml}#SBATCH -o {out_log}

set -euo pipefail
cd {shlex.quote(str(workdir))}
echo "[sbatch] starting {job_name} on $(hostname) at $(date)"
{command}
echo "[sbatch] finished {job_name} at $(date)"
"""
        with tempfile.NamedTemporaryFile("w", delete=False, prefix=f"{job_name}_", suffix=".sbatch") as tmp:
            tmp.write(script)
            tmp_path = tmp.name

        res = subprocess.run(["sbatch", tmp_path], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"sbatch failed: {res.stderr.strip()}")
        m = re.search(r"Submitted batch job (\d+)", res.stdout)
        if not m:
            raise RuntimeError(f"Cannot parse job id from sbatch output: {res.stdout.strip()}")
        return m.group(1)

    def status(self, jobid: str) -> Dict:
        """Return {'jobid':..., 'state': 'PD/R/CG/..'} or {'state':'NOTFOUND'}"""
        res = subprocess.run(["squeue", "-j", jobid, "-h", "-o", "%T"], capture_output=True, text=True, check=False)
        state = res.stdout.strip()
        return {"jobid": jobid, "state": state if state else "NOTFOUND"}

    def cancel(self, jobid: str) -> bool:
        res = subprocess.run(["scancel", jobid], capture_output=True, text=True, check=False)
        return res.returncode == 0
