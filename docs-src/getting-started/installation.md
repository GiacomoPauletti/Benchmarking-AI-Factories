# Installation Guide

This page provides detailed installation instructions for the AI Factory Benchmarking Framework.

## Prerequisites

### Requirements

- Access to **MeluXina** supercomputer
- SLURM allocation (account: `p200981` or your project account)
- Docker and Docker Compose installed locally
- SSH access configured to MeluXina
- Git

## Installation Steps

### 1. Clone the Repository

```bash
cd $HOME
git clone https://github.com/janmarxen/Benchmarking-AI-Factories.git
cd Benchmarking-AI-Factories
```

### 2. Configure Environment

Create a `.env` file in the project root with your MeluXina credentials:

```bash
cp .env.example .env
# Edit .env with your settings
```

#### Required environment variables:

#### SSH Configuration:

- `SSH_HOST` - MeluXina hostname (e.g., `login.lxp.lu`)
- `SSH_PORT` - SSH port (`8822` for MeluXina)
- `SSH_USER` - Your MeluXina username (e.g., `u103056`)
- `SSH_KEY_PATH` - Path to your SSH private key (e.g., `~/.ssh/id_ed25519`)

#### Remote Paths:

- `REMOTE_BASE_PATH` - Working directory on MeluXina (e.g., `~/ai-factory-benchmarks`)
- `REMOTE_HF_CACHE_PATH` - HuggingFace model cache directory (e.g., `/project/scratch/p200981/u103056/huggingface_cache`)
- `REMOTE_SIF_DIR` - Singularity image storage directory (e.g., `/project/scratch/p200981/u103056`)

#### HuggingFace:

- `HF_TOKEN` - HuggingFace API token for accessing gated models and higher rate limits

#### SLURM Configuration:

- `ORCHESTRATOR_ACCOUNT` - SLURM account (e.g., `p200981`)
- `ORCHESTRATOR_PARTITION` - Default partition (e.g., `cpu`)
- `ORCHESTRATOR_QOS` - Quality of Service (e.g., `default`)

#### Example configuration:

```bash
# MeluXina SSH Configuration
SSH_HOST=login.lxp.lu
SSH_PORT=8822
SSH_USER=u103056
SSH_KEY_PATH=~/.ssh/id_ed25519

# HuggingFace Authentication
HF_TOKEN=hf_your_token_here

# Remote Paths
REMOTE_BASE_PATH=~/ai-factory-benchmarks
REMOTE_HF_CACHE_PATH=/project/scratch/p200981/u103056/huggingface_cache
REMOTE_SIF_DIR=/project/scratch/p200981/u103056

# SLURM Configuration
ORCHESTRATOR_ACCOUNT=p200981
ORCHESTRATOR_PARTITION=cpu
```

### 3. Configure SSH Agent

The framework uses **SSH agent forwarding** for secure authentication without exposing private keys to containers.

!!! info "SSH Agent Security"
    SSH agent forwarding is more secure than mounting raw SSH keys because:
    
    - Private keys never enter the container filesystem
    - Authentication happens via the agent on your host machine
    - Supports multiple keys and respects your `~/.ssh/config`
    - Follows the principle of least privilege

**Ensure your SSH agent is running:**

```bash
# Check if SSH agent is running
echo $SSH_AUTH_SOCK

# If empty, start the agent (usually automatic on desktop environments)
eval "$(ssh-agent -s)"

# Add your MeluXina SSH key to the agent
ssh-add ~/.ssh/id_ed25519  # Or your key file

# Verify key is loaded
ssh-add -l
```

!!! tip "Desktop Environments"
    Most Linux desktop environments (GNOME, KDE, etc.) automatically start an SSH agent. You typically only need to run `ssh-add` once after login.

The Docker containers will use the `SSH_AUTH_SOCK` environment variable to communicate with your host's SSH agent.

### 4. Start the Application

```bash
docker compose up -d 
```

Once all services are running, you can access the Grafana dashboard at:

**[http://localhost:3000](http://localhost:3000)**

!!! tip "Available Services"
    After starting the application, the following services will be available:
    
    - **Grafana Dashboard**: [http://localhost:3000](http://localhost:3000)
    - **Server API**: [http://localhost:8001/docs](http://localhost:8001/docs)
    - **Client API**: [http://localhost:8002/docs](http://localhost:8002/docs)
    - **Logs API**: [http://localhost:8004/docs](http://localhost:8004/docs)
    - **Monitoring API**: [http://localhost:8005/docs](http://localhost:8005/docs)
    - **Prometheus**: [http://localhost:9090](http://localhost:9090)

## Next Steps

- [Overview](overview.md) - Learn about the framework
- [Architecture](../architecture/overview.md) - Understand the system architecture
- [Server API Documentation](../api/server.md) - Explore the Server API endpoints
- [Client API Documentation](../api/client.md) - Explore the Client API endpoints
- [Logs API Documentation](../api/logs.md) - Explore the Logs API endpoints
- [Monitoring API Documentation](../api/monitoring.md) - Explore the Monitoring API endpoints

---

Note: the repository uses `docker compose` for local development and testing. For realistic benchmarking and production deployments these services should run on a Kubernetes (K8s) cluster instead. The docker-compose setup is intended for local testing only.

