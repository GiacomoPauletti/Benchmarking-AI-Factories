# Logs Service

The Logs Service is a microservice that periodically syncs logs from MeluXina HPC cluster and categorizes them by service type (server, client, monitoring, vllm, slurm, etc.).

## Features

- **Automatic Log Syncing**: Periodically fetches logs from MeluXina via rsync over SSH
- **Log Categorization**: Automatically sorts logs into service-specific directories
- **REST API**: Provides endpoints to query, filter, and retrieve logs
- **Statistics**: Tracks sync status and provides per-service statistics
- **Manual Trigger**: Allows manual sync triggering via API

## Architecture

```
services/logs/
├── src/
│   ├── main.py              # FastAPI application with background sync task
│   ├── ssh_manager.py       # SSH connection and rsync management
│   ├── log_categorizer.py   # Log categorization logic
│   └── logging_setup.py     # Logging configuration
├── data/
│   ├── logs/                # Raw synced logs from MeluXina
│   └── categorized/         # Categorized logs by service
│       ├── server/
│       ├── client/
│       ├── monitoring/
│       ├── vllm/
│       ├── slurm/
│       └── uncategorized/
├── Dockerfile
├── requirements.txt
└── .env.local
```

## Configuration

Configure via environment variables in `.env` or `.env.local`:

```bash
# SSH Configuration
SSH_HOST=login.lxp.lu
SSH_PORT=8822
SSH_USER=u103056

# Remote path on MeluXina
REMOTE_BASE_PATH=~/ai-factory-benchmarks

# Sync configuration
SYNC_INTERVAL=60  # Seconds between automatic syncs

# Service configuration
LOG_LEVEL=INFO
```

## API Endpoints

### Health and Status

- `GET /health` - Health check
- `GET /status` - Get sync status and statistics
- `GET /` - Service information

### Sync Operations

- `POST /sync/trigger` - Manually trigger a log sync

### Service Management

- `GET /services` - List all service categories
- `GET /services/stats` - Get statistics for each service

### Log Access

- `GET /logs?service={name}&limit={n}` - List log files (optional filters)
- `GET /logs/content?path={path}&tail={n}` - Get log file content

## Usage Examples

### Check Service Status

```bash
curl http://localhost:8004/status
```

### Trigger Manual Sync

```bash
curl -X POST http://localhost:8004/sync/trigger
```

### List Service Categories

```bash
curl http://localhost:8004/services
```

### Get Service Statistics

```bash
curl http://localhost:8004/services/stats
```

### List Logs for Specific Service

```bash
# List server logs (last 10 files)
curl http://localhost:8004/logs?service=server&limit=10

# List all SLURM logs
curl http://localhost:8004/logs?service=slurm
```

### View Log Content

```bash
# View full log
curl http://localhost:8004/logs/content?path=categorized/server/job_12345.log

# View last 100 lines
curl http://localhost:8004/logs/content?path=categorized/slurm/job_67890.err&tail=100
```

## Log Categorization

The service automatically categorizes logs based on filename patterns:

| Service | Patterns |
|---------|----------|
| **server** | `server-`, `orchestrator`, `slurm-job` |
| **client** | `client-`, `benchmark-` |
| **monitoring** | `monitor`, `prometheus`, `grafana` |
| **vllm** | `vllm`, `model-server`, `inference` |
| **slurm** | `.err`, `.out`, `slurm-`, `sbatch` |
| **logs** | `logs-service` |
| **uncategorized** | Files not matching any pattern |

## Development

### Run Locally

```bash
cd services/logs
python -m pip install -r requirements.txt

# Set environment variables
export SSH_HOST=login.lxp.lu
export SSH_USER=u103056
# ... other variables

# Run the service
python -m uvicorn src.main:app --host 0.0.0.0 --port 8003 --reload
```

### Run with Docker Compose

```bash
# Build and start all services
docker-compose up -d logs

# View logs
docker-compose logs -f logs

# Restart service
docker-compose restart logs
```

### Testing

Test the service endpoints:

```bash
# Check health
curl http://localhost:8004/health

# Get status
curl http://localhost:8004/status

# Trigger sync
curl -X POST http://localhost:8004/sync/trigger

# List services
curl http://localhost:8004/services

# Get statistics
curl http://localhost:8004/services/stats
```

## How It Works

1. **Startup**: Service initializes SSH connection to MeluXina and creates data directories
2. **Background Task**: Asyncio task runs every `SYNC_INTERVAL` seconds
3. **Sync Phase**: Uses rsync over SSH to sync logs from `REMOTE_BASE_PATH/logs/` to local storage
4. **Categorization Phase**: Scans synced logs and copies them to service-specific directories
5. **API Access**: FastAPI endpoints provide access to categorized logs and statistics

## SSH Authentication

The service uses SSH keys for authentication with MeluXina:

- SSH keys are mounted from host `~/.ssh/` directory
- Keys are copied into container's `/root/.ssh/` on startup
- No raw keys are stored in the image
- Supports both password-protected and unprotected keys

## Monitoring

The service exposes health check endpoint for Docker:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

## Troubleshooting

### Logs not syncing

1. Check SSH configuration:
   ```bash
   docker-compose exec logs ssh -p 8822 u103056@login.lxp.lu ls ~/ai-factory-benchmarks/logs/
   ```

2. Check service logs:
   ```bash
   docker-compose logs -f logs
   ```

3. Manually trigger sync:
   ```bash
   curl -X POST http://localhost:8004/sync/trigger
   ```

### SSH permission issues

Ensure SSH keys have correct permissions on host:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_*
chmod 644 ~/.ssh/*.pub
```

### No logs categorized

Check if logs exist in raw directory:

```bash
docker-compose exec logs ls -la /app/data/logs/
```

Check categorization patterns match your log filenames in `src/log_categorizer.py`.

## Future Enhancements

- [ ] Add WebSocket endpoint for real-time log streaming
- [ ] Implement log search functionality
- [ ] Add log parsing and error detection
- [ ] Integrate with Loki for log aggregation
- [ ] Add log retention policies
- [ ] Support log filtering by date range
- [ ] Add compression for old logs
