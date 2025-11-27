# Logs API Documentation

## Overview

The Logs API provides access to SLURM job logs synced from MeluXina. It automatically categorizes logs by service type and offers REST endpoints for querying and retrieval.

## Interactive API Reference

<swagger-ui src="logs-openapi.json"/>

## Quick Reference

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/status` | GET | Sync status and statistics |
| `/sync/trigger` | POST | Manually trigger log sync |
| `/services` | GET | List available service categories |
| `/services/stats` | GET | Statistics per service |
| `/logs` | GET | List log files (filterable) |
| `/logs/content` | GET | Get log file content |
| `/logs/delete` | POST | Delete specific log file |
| `/logs/cleanup` | POST | Delete all logs |

### Get Sync Status

```bash
curl http://localhost:8004/status
```

**Response:**
```json
{
  "sync_enabled": true,
  "last_sync_time": "2024-11-25T15:30:00",
  "sync_interval_seconds": 60,
  "total_syncs": 145,
  "failed_syncs": 2,
  "logs_directory": "/app/data/logs",
  "categorized_directory": "/app/data/categorized"
}
```

### List Service Categories

```bash
curl http://localhost:8004/services
```

**Response:**
```json
["server", "client", "vllm", "vector-db", "monitoring", "uncategorized"]
```

### Query Logs

```bash
# All logs (paginated)
curl "http://localhost:8004/logs?limit=50"

# Filter by service
curl "http://localhost:8004/logs?service=client&limit=20"
```

**Response:**
```json
[
  {
    "filename": "loadgen-12345.out",
    "path": "categorized/client/loadgen-12345.out",
    "size_bytes": 45632,
    "modified_time": "2024-11-25T15:30:00.123456",
    "service": "client"
  }
]
```

### Get Log Content

```bash
# Full content
curl "http://localhost:8004/logs/content?path=categorized/client/loadgen-12345.out"

# Last 100 lines
curl "http://localhost:8004/logs/content?path=categorized/client/loadgen-12345.out&tail=100"
```

**Response:** Plain text log content

### Service Statistics

```bash
curl http://localhost:8004/services/stats
```

**Response:**
```json
{
  "client": {
    "service": "client",
    "file_count": 24,
    "total_size_bytes": 1048576,
    "latest_modified": "2024-11-25T15:30:00"
  },
  "vllm": {
    "service": "vllm",
    "file_count": 8,
    "total_size_bytes": 524288,
    "latest_modified": "2024-11-25T15:25:00"
  }
}
```

## Usage Examples

### Python Client

```python
import requests

LOGS_API = "http://localhost:8004"

# Get all client logs
response = requests.get(f"{LOGS_API}/logs", params={
    "service": "client",
    "limit": 50
})
logs = response.json()

for log in logs:
    print(f"{log['filename']}: {log['size_bytes']} bytes")
    
    # Get content of specific log
    content = requests.get(
        f"{LOGS_API}/logs/content",
        params={"path": log["path"], "tail": 100}
    ).text
    
    print(content[:500])  # First 500 chars
```

### Monitor Sync Status

```python
import requests
import time

LOGS_API = "http://localhost:8004"

while True:
    status = requests.get(f"{LOGS_API}/status").json()
    
    print(f"Syncs: {status['total_syncs']} "
          f"(Failed: {status['failed_syncs']}) "
          f"Last: {status['last_sync_time']}")
    
    time.sleep(30)
```

### Cleanup Old Logs

```python
import requests

LOGS_API = "http://localhost:8004"

# Delete all logs (local and remote)
response = requests.post(f"{LOGS_API}/logs/cleanup")
result = response.json()

print(f"Deleted {result['deleted_count']} local files")
print(f"Deleted {result['remote_deleted_count']} remote files")
```

## Log Categories

The service automatically categorizes logs using filename patterns:

- **client**: `loadgen-*.out`, `loadgen-*.err`
- **vllm**: `vllm-*.out`, `inference-*.out`
- **vector-db**: `vectordb-*.out`, `qdrant-*.out`
- **server**: `server-*.out`, `orchestrator-*.out`
- **monitoring**: `prometheus-*.out`, `exporter-*.out`
- **uncategorized**: Files that don't match any pattern


## Related Documentation

- **[Logs Service Overview](../services/logs)**: Architecture and configuration
- **[Server API](server)**: Create services that generate logs
- **[Client API](client)**: Create client groups that generate logs
