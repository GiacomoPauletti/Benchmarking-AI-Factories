from pathlib import Path
from unittest import mock

from services.monitoring.managers.slurm import SlurmRunner
from services.monitoring.managers.prometheus import PrometheusManager


@mock.patch("subprocess.run")
def test_slurm_runner_submit_status_cancel(mrun):
    # sbatch
    mrun.return_value.returncode = 0
    mrun.return_value.stdout = "Submitted batch job 12345\n"
    mrun.return_value.stderr = ""

    sr = SlurmRunner(logs_dir="logs")
    jobid = sr.submit("echo hello", job_name="tjob", time="00:01:00")
    assert jobid == "12345"

    # squeue
    mrun.return_value.stdout = "R\n"
    st = sr.status(jobid)
    assert st["state"] == "R"

    # scancel
    mrun.return_value.returncode = 0
    assert sr.cancel(jobid) is True


class _FakeSlurm:
    def submit(self, *a, **k): return "99999"
    def cancel(self, jobid): return True


def test_prometheus_manager_start_ready_stop():
    pm = PrometheusManager(_FakeSlurm())
    jid = pm.start(config_path=Path("/tmp/prom.yml"), port=9090, storage_dir=Path("/tmp/prom"))
    assert jid == "99999"

    # readiness 200
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__.return_value.status = 200
        assert pm.is_ready("http://localhost:9090", timeout_s=1) is True

    assert pm.stop(jid) is True
