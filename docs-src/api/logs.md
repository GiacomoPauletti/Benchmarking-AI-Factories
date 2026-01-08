# Logs API Documentation

## Overview

The Logs API (port `8004`) provides access to SLURM job logs synced from MeluXina, automatically categorized by service type.

## Interactive API Reference

<swagger-ui src="logs-openapi.json"/>

## Quick Start

### Check Sync Status

```bash
curl http://localhost:8004/status
```

### List Service Categories

```bash
curl http://localhost:8004/services
```

Returns: `["server", "client", "vllm", "vector-db", "monitoring", "uncategorized"]`

### Query Logs

```bash
# All logs (paginated)
curl "http://localhost:8004/logs?limit=50"

# Filter by service
curl "http://localhost:8004/logs?service=client&limit=20"
```

### Get Log Content

```bash
# Full content
curl "http://localhost:8004/logs/content?path=categorized/client/loadgen-12345.out"

# Last 100 lines
curl "http://localhost:8004/logs/content?path=categorized/client/loadgen-12345.out&tail=100"
```

### Trigger Manual Sync

```bash
curl -X POST http://localhost:8004/sync/trigger
```

### Get Service Statistics

```bash
curl http://localhost:8004/services/stats
```

## Log Categories

Logs are automatically categorized by filename patterns:

| Category | Patterns |
|----------|----------|
| `client` | `loadgen-*.out`, `loadgen-*.err` |
| `vllm` | `vllm-*.out`, `inference-*.out` |
| `vector-db` | `vectordb-*.out`, `qdrant-*.out` |
| `server` | `server-*.out`, `orchestrator-*.out` |
| `monitoring` | `prometheus-*.out`, `exporter-*.out` |

## See Also

- [Logs Service Overview](../services/logs.md) - Architecture and configuration
- [Server API](server.md) - Create services that generate logs
