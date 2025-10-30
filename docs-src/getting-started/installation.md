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
- `SSH_PORT` - SSH port (typically 22)
- `SSH_USER` - Your MeluXina username
- `SSH_KEY_PATH` - Path to your SSH private key
- `REMOTE_BASE_PATH` - Working directory on MeluXina

Example:
```bash
SSH_HOST=login.lxp.lu              # MeluXina login node
SSH_PORT=8822                       # MeluXina SSH port
SSH_USER=u123456                    # Your MeluXina username
SSH_KEY_PATH=~/.ssh/id_ed25519     # Path to your SSH key
REMOTE_BASE_PATH=/project/home/p200981/u123456/path/to/temp/generated/files
```

The Dockerfile automatically:
    1. Copies your SSH key into the container
    2. Sets correct permissions (600)
    3. Configures SSH client for MeluXina

### 3. Start the Microservice

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

