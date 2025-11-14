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
git clone https://github.com/GiacomoPauletti/Benchmarking-AI-Factories.git
cd Benchmarking-AI-Factories
```

### 2. Configure Environment

Create a `.env` file in the project root with your MeluXina credentials:

```bash
cp .env.example .env
# Edit .env with your settings
```

Required environment variables:
- `SSH_HOST` - MeluXina hostname
- `SSH_PORT` - SSH port (typically 8822)
- `SSH_USER` - Your MeluXina username
- `REMOTE_BASE_PATH` - Working directory on MeluXina

Example:
```bash
SSH_HOST=login.lxp.lu              # MeluXina login node
SSH_PORT=8822                       # MeluXina SSH port
SSH_USER=u123456                    # Your MeluXina username
REMOTE_BASE_PATH=/project/home/p200981/u123456/path/to/temp/generated/files
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

### 4. Start the Microservice

TODO: Later, this will be replaced by the actual app using the microservices.

```bash
docker compose up -d <microservice to launch>
```

## Next Steps

- [Overview](overview.md) - Learn about the framework
- [Architecture](../architecture/overview.md) - Understand the system architecture
- [Server API Documentation](../api/server.md) - Explore the Server API endpoints
- [Client API Documentation](../api/client.md) - Explore the Client API endpoints
- [Logs API Documentation](../api/logs.md) - Explore the Logs API endpoints
- [Monitoring API Documentation](../api/monitoring.md) - Explore the Monitoring API endpoints

---

Note: the repository uses `docker compose` for local development and testing. For realistic benchmarking and production deployments these services should run on a Kubernetes (K8s) cluster instead. The docker-compose setup is intended for local testing only.

