# Local Development Guide

## Overview

This guide explains how to develop the Benchmarking AI Factories server locally while submitting jobs to the MeluXina HPC cluster.

## Architecture

The local development setup uses a **dual-path architecture**:

```
┌─────────────────┐         SSH Tunnel          ┌──────────────────┐
│  Local Laptop   │◄────────────────────────────►│  MeluXina HPC    │
│  (Docker)       │                              │                  │
│                 │         SLURM REST API       │                  │
│  - FastAPI      │◄────────────────────────────►│  - SLURM Queue   │
│  - Recipes      │                              │  - Recipes (copy)│
│  - Logs (cache) │◄────────────────────────────►│  - Logs (source) │
└─────────────────┘                              └──────────────────┘
```

### Path Types

1. **LOCAL_BASE_PATH** (`/app` in container, `./src` on host)
   - Where recipes and configs are stored locally
   - Used for reading recipe definitions
   - Used for caching fetched logs

2. **REMOTE_BASE_PATH** (e.g., `/project/home/p200981/u103056/Benchmarking-AI-Factories/services/server`)
   - Where the project exists on MeluXina
   - Where SLURM jobs execute
   - Where logs are written

## Features

### 1. Automatic Recipe Syncing

Recipes are automatically synced to MeluXina in two ways:

#### A. Initial Sync on Server Launch

When you run `./launch_local.sh`, it:
- Tests SSH connection to MeluXina
- Syncs entire `recipes/` directory to MeluXina
- Excludes logs, cache, and git files
- Creates remote directory structure if needed

```bash
./launch_local.sh
# Output:
# ✓ SSH connection successful
# Syncing recipes and configs to MeluXina...
# ✓ Sync complete
```

#### B. Per-Job Sync on Submission

When you submit a job, the server:
- Automatically syncs only the specific recipe needed
- Ensures MeluXina has the latest version
- Logs sync status (warnings if sync fails)

```python
# Happens automatically in submit_job()
self._sync_recipe_to_remote(recipe_name)
```

**Manual sync if needed:**
```bash
# From your laptop
rsync -avz services/server/recipes/ meluxina:/project/home/p200981/u103056/Benchmarking-AI-Factories/services/server/recipes/
```

### 2. Automatic Log Fetching

Logs are written on MeluXina but automatically fetched when requested:

#### How It Works

1. Job runs on MeluXina, writes logs to:
   ```
   /project/home/p200981/u103056/Benchmarking-AI-Factories/services/server/logs/vllm_3651945.out
   ```

2. User requests logs via API:
   ```bash
   curl http://localhost:8001/api/v1/services/3651945/logs
   ```

3. Server checks local cache (`/app/logs/`):
   - If found: Returns immediately
   - If not found: Fetches via SSH, caches, then returns

4. Subsequent requests use cached version (instant)

#### Implementation Details

```python
def get_job_logs(self, job_id: str) -> str:
    # Check local cache
    if not stdout_local.exists():
        # Fetch from MeluXina via SSH
        self._fetch_remote_log_file(stdout_remote, stdout_local)
    
    # Return cached log
    return stdout_local.read_text()
```

The `_fetch_remote_log_file()` method:
- Uses SSH to `cat` remote log files
- Saves to local cache for future requests
- Returns gracefully if log doesn't exist yet (job not started)

### 3. SSH Tunnel for SLURM REST API

The server establishes an SSH tunnel at startup:

```
localhost:6820 → ssh → MeluXina → slurmrestd.meluxina.lxp.lu:6820
```

This allows the local server to communicate with SLURM REST API as if it were running on MeluXina.

## Configuration

### Required Environment Variables

In `.env.local`:

```bash
# SSH Configuration
SSH_TUNNEL_HOST=meluxina          # SSH config alias or hostname
SSH_TUNNEL_USER=u103056           # Your MeluXina username

# SLURM Authentication
SLURM_JWT=eyJhbGciOiJIUzI1NiI... # Get from: ssh meluxina "scontrol token"

# Path Configuration (optional)
LOCAL_BASE_PATH=/app              # Default: /app (inside container)
REMOTE_BASE_PATH=/project/home/p200981/u103056/Benchmarking-AI-Factories/services/server
```

### SSH Configuration

Recommended `~/.ssh/config`:

```
Host meluxina
    HostName login.lxp.lu
    Port 8822
    User u103056
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

## Workflow

### 1. Start the Server

```bash
cd services/server
./launch_local.sh
```

This will:
- Test SSH connection
- Sync recipes to MeluXina
- Start Docker container with hot-reload
- Establish SSH tunnel for SLURM API

### 2. Submit a Job

```bash
# Using curl
curl -X POST http://localhost:8001/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{"recipe_name": "inference/vllm"}'

# Using client command (if in container)
docker exec -it server bash
create inference/vllm
```

Behind the scenes:
1. Server syncs `inference/vllm` recipe to MeluXina
2. Generates SLURM batch script with remote paths
3. Submits via REST API
4. Returns job ID

### 3. Check Job Status

```bash
curl http://localhost:8001/api/v1/services/3651945
```

### 4. View Logs

```bash
curl http://localhost:8001/api/v1/services/3651945/logs
```

First request:
- Fetches logs from MeluXina via SSH
- Caches locally in `services/server/src/logs/`
- Returns content

Subsequent requests:
- Returns cached content immediately

### 5. Monitor in Real-Time

You can watch logs update:

```bash
# From your laptop
watch -n 5 "curl -s http://localhost:8001/api/v1/services/3651945/logs | tail -20"
```

Or SSH directly to MeluXina:

```bash
ssh meluxina "tail -f /project/home/p200981/u103056/Benchmarking-AI-Factories/services/server/logs/vllm_3651945.out"
```

## Troubleshooting

### Recipe Sync Issues

If recipes aren't syncing:

```bash
# Check SSH connection
ssh meluxina "ls -la /project/home/p200981/u103056/Benchmarking-AI-Factories/services/server/recipes/"

# Manual sync
rsync -avz services/server/recipes/ meluxina:/project/home/p200981/u103056/Benchmarking-AI-Factories/services/server/recipes/

# Check server logs
docker logs server 2>&1 | grep -i sync
```

### Log Fetching Issues

If logs aren't appearing:

```bash
# Check if logs exist on MeluXina
ssh meluxina "ls -la /project/home/p200981/u103056/Benchmarking-AI-Factories/services/server/logs/"

# Check local cache
ls -la services/server/src/logs/

# Check server logs for SSH errors
docker logs server 2>&1 | grep -i "fetching"
```

### JWT Token Expired

SLURM JWT tokens expire after 30 minutes:

```bash
# Get new token
ssh meluxina "scontrol token"

# Update .env.local with new token
# Restart container
docker compose restart
```

## Benefits of This Architecture

✅ **Local Development** - Edit code locally, see changes immediately (hot-reload)  
✅ **Real HPC Testing** - Jobs run on actual MeluXina infrastructure  
✅ **Automatic Syncing** - Recipes always up-to-date on HPC  
✅ **Log Access** - View remote logs without SSH'ing  
✅ **Caching** - Fetched logs cached locally for speed  
✅ **No Manual Steps** - Everything automated in workflow  

## Limitations

⚠️ **JWT Expiration** - Tokens expire every 30 minutes, must refresh  
⚠️ **Network Dependency** - Requires active SSH connection  
⚠️ **Sync Latency** - Recipe sync adds ~1-2 seconds per job submission  
⚠️ **Remote Path Assumption** - Assumes project exists at specific path on MeluXina  

## Alternative: Full Remote Development

If you prefer developing entirely on MeluXina:

```bash
# SSH to MeluXina
ssh meluxina

# Clone repo
cd /project/home/p200981/u103056
git clone https://github.com/GiacomoPauletti/Benchmarking-AI-Factories.git
cd Benchmarking-AI-Factories

# Run server natively
cd services/server
./launch_server.sh

# Port forward to access from laptop
# From laptop:
ssh -L 8001:mel0533:8001 meluxina
# Then access http://localhost:8001
```

This eliminates syncing but requires all development on MeluXina.
