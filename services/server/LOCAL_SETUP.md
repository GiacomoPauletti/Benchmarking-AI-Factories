# Local Docker Development Setup Guide

This guide walks you through setting up local development with Docker + SSH tunnel to MeluXina.

## Prerequisites Checklist

- [ ] Docker Desktop installed and running
- [ ] SSH access to MeluXina configured
- [ ] SSH keys set up (password-less authentication)
- [ ] Git repository cloned

## Step-by-Step Setup

### 1. Test SSH Connection

First, verify you can connect to MeluXina without a password:

```bash
ssh <your_username>@login.lxp.lu
```

If this prompts for a password, set up SSH keys:

```bash
# Generate SSH key (if you don't have one)
ssh-keygen -t rsa -b 4096

# Copy key to MeluXina
ssh-copy-id <your_username>@login.lxp.lu
```

### 2. Configure SSH Config (Optional but Recommended)

Add to `~/.ssh/config`:

```
Host meluxina
    HostName login.lxp.lu
    User <your_username>
    IdentityFile ~/.ssh/id_rsa
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

Now you can connect with just: `ssh meluxina`

### 3. Create Local Environment File

```bash
cd services/server
cp .env.local.example .env.local
```

Edit `.env.local`:

```bash
# Required: Your MeluXina username
SSH_TUNNEL_USER=<your_username>

# Required: MeluXina login node
SSH_TUNNEL_HOST=login.lxp.lu

# Optional: Log level
LOG_LEVEL=INFO
```

### 4. Launch the Server

```bash
cd services/server
./launch_local.sh
```

This will:
1. Test SSH connection to MeluXina
2. Build Docker image (first time takes ~2-3 minutes)
3. Start FastAPI server on http://localhost:8001
4. Enable hot-reload for code changes

### 5. Verify Server is Running

Open another terminal:

```bash
# Health check
curl http://localhost:8001/health

# Expected response:
# {"status":"healthy"}

# View API documentation
open http://localhost:8001/docs
```

## Common Issues

### Issue: "Cannot connect to SSH_TUNNEL_HOST"

**Solution:** Verify SSH keys are set up correctly:
```bash
ssh -v <your_username>@login.lxp.lu
```

### Issue: "Docker is not running"

**Solution:** Start Docker Desktop and wait for it to be ready.

### Issue: "Permission denied" when running launch_local.sh

**Solution:** Make script executable:
```bash
chmod +x launch_local.sh
```

### Issue: Port 8001 already in use

**Solution:** Stop other services using port 8001:
```bash
# Find process using port 8001
lsof -i :8001

# Kill it or change the port in docker-compose.yml
```

## Development Workflow

### Basic Workflow

1. **Start server:**
   ```bash
   ./launch_local.sh
   ```

2. **Edit code** in `src/` directory
   - Changes are automatically reloaded
   - Check terminal for reload confirmation

3. **Test your changes:**
   ```bash
   # List available recipes
   curl http://localhost:8001/api/v1/recipes

   # Submit a test job (runs on MeluXina)
   curl -X POST http://localhost:8001/api/v1/services \
     -H "Content-Type: application/json" \
     -d '{"recipe_name": "hello", "config": {}}'
   ```

4. **Stop server:** Press `Ctrl+C`

### Advanced: Debugging

To debug the server, you can attach to the running container:

```bash
# In another terminal
docker exec -it benchmarking-ai-server /bin/bash

# Inside container
python -m pdb src/main.py
```

### Advanced: View Logs

```bash
# Server logs
docker logs benchmarking-ai-server

# Follow logs in real-time
docker logs -f benchmarking-ai-server

# Job logs (on MeluXina)
ssh meluxina "cat ~/Benchmarking-AI-Factories/services/server/logs/*.out"
```

## Architecture

```
┌─────────────────────────────────────┐
│  Local Laptop (Docker)              │
│  ┌────────────────────────────────┐ │
│  │  FastAPI Server Container      │ │
│  │  - REST API on port 8001       │ │
│  │  - Hot-reload enabled          │ │
│  │  - Job submission via SSH      │ │
│  └────────────────────────────────┘ │
│           │ SSH Connection           │
└───────────┼─────────────────────────┘
            │
            ▼
┌─────────────────────────────────────┐
│  MeluXina HPC Cluster               │
│  ┌────────────────────────────────┐ │
│  │  sbatch - Submit jobs          │ │
│  │  squeue - Check status         │ │
│  │  scancel - Cancel jobs         │ │
│  │  Apptainer containers          │ │
│  │  GPU nodes                     │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

## Next Steps

- Read the [API documentation](http://localhost:8001/docs)
- Check out example recipes in `src/recipes/`
- Run the test suite: `./run-tests.sh`
- Explore the architecture in `docs/server-architecture.md`

## Stopping the Server

Press `Ctrl+C` in the terminal where `launch_local.sh` is running. The script will automatically:
- Stop the Docker container
- Clean up resources

## Troubleshooting

### View all Docker containers
```bash
docker ps -a
```

### Rebuild from scratch
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up
```

### Check Docker logs
```bash
docker-compose logs
```

### SSH connection testing
```bash
# Test SSH with verbose output
ssh -vvv <your_username>@login.lxp.lu

# Test command execution
ssh <your_username>@login.lxp.lu "squeue -u $USER"
```

### Common SLURM Commands

```bash
# Check your jobs
ssh meluxina "squeue -u $USER"

# Cancel a job
ssh meluxina "scancel <job_id>"

# Check job history
ssh meluxina "sacct -j <job_id>"

# View job details
ssh meluxina "scontrol show job <job_id>"
```
