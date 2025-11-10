# Testing Guide for Monitoring

This replicates the Server team’s containerized procedure, adapted for the **Monitoring** module.

## Prerequisites

- **Apptainer** available on the system (e.g., `module load Apptainer/1.x` on MeluXina).
- (Optional) **SLURM** if you want the script to request a short allocation automatically.

## Run all tests

```bash
# from repo root
cd services/monitoring
./run-tests.sh
```

The script will:

1. Build an Apptainer test container (`tests/test-container.sif`)

2. If you are not already inside a SLURM job, request a short allocation (15m, 8GB)

3. Run unit tests and integration tests inside the container

4. Save logs to `services/monitoring/tests/`

## What runs
```bash
services/monitoring/tests/
├── test-container.def       # Apptainer container recipe
├── test_unit_core.py        # StateStore, Registry, ConfigRenderer (HTTP reload mocked)
├── test_unit_managers.py    # SlurmRunner (subprocess mocked), PrometheusManager (readiness mocked)
├── test_unit_collector.py   # CollectorAgg (Prometheus HTTP mocked)
└── test_integration.py      # End-to-end with a tiny in-process fake Prometheus server
```

## Logs
- `services/monitoring/tests/unit-test.log`
- `services/monitoring/tests/integration-test.log`

## Manual run (without the script)
Build the container:
```bash
apptainer build services/monitoring/tests/test-container.sif \
  services/monitoring/tests/test-container.def
```
Run all Monitoring tests:
```bash
apptainer run --bind "$(pwd)":/app services/monitoring/tests/test-container.sif
```
Run a specific test file:
```bash
apptainer run --bind "$(pwd)":/app services/monitoring/tests/test-container.sif \
  pytest -q services/monitoring/tests/test_unit_collector.py
```

## Helper script
A convenience script is provided at `services/monitoring/run-tests.sh`.

Make it executable:
```bash
chmod +x services/monitoring/run-tests.sh
```
Usage:
```bash
# from repo root
services/monitoring/run-tests.sh
```
The script:
- Builds `tests/test-container.sif`
- If `salloc` exists and you’re not inside a SLURM job, requests `15m / 8GB` and runs the container there
- Otherwise runs the container directly on the current machine

## Troubleshooting
- Apptainer not found: load the correct module (e.g., `module load Apptainer/1.2.4-...`).

- Permission denied (script): `chmod +x services/monitoring/run-tests.sh`.

- Bind mount issues: ensure you run from the repo root so `--bind "$(pwd)":/app` maps the project correctly.

- Network-restricted nodes: integration tests use an in-process fake Prometheus; no external network is required.


