# Monitoring Service API

## Interactive API Reference

The Monitoring Service provides a REST API for managing Prometheus-based metrics collection in HPC environments.

<swagger-ui src="monitor-openapi.json"/>

## Overview

The Monitoring Service orchestrates:
- **Prometheus deployment** via SLURM
- **Target registration** (clients, services, exporters)
- **Metrics collection** for time windows
- **Artifact generation** (CSV, JSON)

## API Examples

### 1. Create a Monitoring Session

```bash
curl -X POST http://localhost:8002/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "benchmark-01",
    "prometheus_port": 9090,
    "prom_host": "localhost"
  }'
```

### 2. Start Prometheus

```bash
curl -X POST http://localhost:8002/api/v1/sessions/benchmark-01/start \
  -H "Content-Type: application/json" \
  -d '{
    "partition": "cpu",
    "time_limit": "02:00:00"
  }'
```

### 3. Register Targets

**Register a client:**
```bash
curl -X POST http://localhost:8002/api/v1/clients \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "benchmark-01",
    "client_id": "client-001",
    "node": "mel2153",
    "exporters": {
      "node": "mel2153:9100",
      "dcgm": "mel2153:9400"
    },
    "preferences": {
      "enable_node": true,
      "enable_dcgm": true
    }
  }'
```

**Register a service:**
```bash
curl -X POST http://localhost:8002/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "benchmark-01",
    "client_id": "client-001",
    "name": "vllm",
    "endpoint": "http://mel2153:8000/metrics"
  }'
```

### 4. Collect Metrics

```bash
curl -X POST http://localhost:8002/api/v1/sessions/benchmark-01/collect \
  -H "Content-Type: application/json" \
  -d '{
    "window_start": "2025-11-04T10:00:00Z",
    "window_end": "2025-11-04T11:00:00Z",
    "out_dir": "/app/logs/metrics",
    "run_id": "run-001"
  }'
```

## Python Client Example

```python
import requests
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8002/api/v1"

# Create session
response = requests.post(
    f"{BASE_URL}/sessions",
    json={
        "run_id": "my-benchmark",
        "prometheus_port": 9090,
        "prom_host": "localhost"
    }
)
session = response.json()
session_id = session["session_id"]

# Start session
requests.post(
    f"{BASE_URL}/sessions/{session_id}/start",
    json={"partition": "cpu", "time_limit": "01:00:00"}
)

# Register a vLLM service
requests.post(
    f"{BASE_URL}/services",
    json={
        "session_id": session_id,
        "client_id": "client-01",
        "name": "vllm",
        "endpoint": "http://mel2153:8000/metrics",
        "labels": {"model": "gpt2"}
    }
)

# Collect metrics
end_time = datetime.utcnow()
start_time = end_time - timedelta(hours=1)

response = requests.post(
    f"{BASE_URL}/sessions/{session_id}/collect",
    json={
        "window_start": start_time.isoformat() + "Z",
        "window_end": end_time.isoformat() + "Z",
        "out_dir": "/app/logs/metrics",
        "run_id": "benchmark-run"
    }
)

artifacts = response.json()["artifacts"]
print(f"Metrics saved to: {artifacts}")

# Stop session
requests.post(f"{BASE_URL}/sessions/{session_id}/stop")
```


## See Also

- [Getting Started](../../getting-started/overview.md)
- [Monitoring Service Overview](../../services/monitoring/overview.md)
- [Architecture](../../architecture/overview.md)
