# Monitoring API Documentation

## Overview

The Monitoring API (port `8005`) manages Prometheus-based metrics collection for benchmarking sessions.

## Interactive API Reference

<swagger-ui src="monitor-openapi.json"/>

## Quick Start

### Create a Monitoring Session

```bash
curl -X POST http://localhost:8005/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "benchmark-01",
    "prometheus_port": 9090,
    "prom_host": "localhost"
  }'
```

### Start Prometheus

```bash
curl -X POST http://localhost:8005/api/v1/sessions/benchmark-01/start \
  -H "Content-Type: application/json" \
  -d '{
    "partition": "cpu",
    "time_limit": "02:00:00"
  }'
```

### Register a Service Target

```bash
curl -X POST http://localhost:8005/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "benchmark-01",
    "client_id": "client-001",
    "name": "vllm",
    "endpoint": "http://mel2153:8000/metrics"
  }'
```

### Collect Metrics

```bash
curl -X POST http://localhost:8005/api/v1/sessions/benchmark-01/collect \
  -H "Content-Type: application/json" \
  -d '{
    "window_start": "2026-01-08T10:00:00Z",
    "window_end": "2026-01-08T11:00:00Z",
    "out_dir": "/app/logs/metrics",
    "run_id": "run-001"
  }'
```

### Stop Session

```bash
curl -X POST http://localhost:8005/api/v1/sessions/benchmark-01/stop
```

## See Also

- [Monitoring Service Overview](../services/monitoring.md) - Architecture and GPU metrics
- [Architecture](../architecture/overview.md) - System design
