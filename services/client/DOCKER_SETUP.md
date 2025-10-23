# Client Service Docker Setup

This document explains how to run the Client Service locall### Troubleshooting

### SSH Issues

1. **Check SSH connection**:
   ```bash
   ssh -p 8822 your_username@login.lxp.lu
   ```

2. **Verify SSH key**:
   ```bash
   ssh-add ~/.ssh/id_rsa
   ssh-add -l
   ```

3. **Test from container**:
   ```bash
   docker compose exec client ssh -p 8822 your_username@login.lxp.lu
   ```ead of Apptainer on MeluXina.

## Architecture Overview

With the new setup:
- **Client Service**: Runs locally using Docker Compose
- **Clients**: Still run on MeluXina using Apptainer (launched via SSH)
- **Communication**: SSH tunnels allow clients on MeluXina to connect back to the local client service

## Quick Start

### 1. Environment Setup

Create a `.env` file in the project root with your MeluXina SSH configuration:

```bash
# SSH Configuration for MeluXina
SSH_HOST=login.lxp.lu
SSH_PORT=8822
SSH_USER=your_username
SSH_KEY_PATH=~/.ssh/id_rsa

# Optional: Remote base path on MeluXina
REMOTE_BASE_PATH=/home/users/your_username/Benchmarking-AI-Factories

# Optional: Logging level
LOG_LEVEL=INFO
```

### 2. Start Client Service with Docker Compose

```bash
# Start both server and client services
docker compose up -d

# Or start only the client service
docker compose up -d client

# With custom configuration
CLIENT_SERVICE_SERVER_ADDR=http://localhost:8001 \
CLIENT_SERVICE_PORT=8002 \
CLIENT_SERVICE_CONTAINER_MODE=true \
docker compose up -d client

# View logs
docker compose logs -f client

# Stop services
docker compose down

# Rebuild if needed
docker compose build client
docker compose up -d client
```

## Configuration Options

### Environment Variables

- `CLIENT_SERVICE_SERVER_ADDR`: Address of the server service (default: http://localhost:8001)
- `CLIENT_SERVICE_HOST`: Host to bind client service to (default: 0.0.0.0)
- `CLIENT_SERVICE_PORT`: Port for client service (default: 8002)
- `CLIENT_SERVICE_CONTAINER_MODE`: Enable container mode for MeluXina clients (boolean)

### SSH Configuration

Required for communication with MeluXina:
- `SSH_HOST`: MeluXina login hostname
- `SSH_PORT`: SSH port (usually 8822 for MeluXina)
- `SSH_USER`: Your MeluXina username
- `SSH_KEY_PATH`: Path to your SSH private key

## How It Works

1. **Local Client Service**: Runs in Docker container locally
2. **SSH Connection**: Establishes connection to MeluXina for job submission
3. **Reverse Tunnel**: Creates SSH reverse tunnel so MeluXina clients can reach local service
4. **Job Submission**: Submits SLURM jobs via SSH using the REST API
5. **Code Sync**: Automatically syncs client code to MeluXina before running jobs

## API Endpoints

The client service provides these endpoints:

- `http://localhost:8002/docs` - API documentation
- `http://localhost:8002/api/v1/client-group/{benchmark_id}` - Create client group
- `http://localhost:8002/api/v1/client-group/{benchmark_id}/connect` - Client connection endpoint

## Troubleshooting

### SSH Issues

1. **Check SSH connection**:
   ```bash
   ssh -p 8822 your_username@login.lxp.lu
   ```

2. **Verify SSH key**:
   ```bash
   ssh-add ~/.ssh/id_rsa
   ssh-add -l
   ```

3. **Test from container**:
   ```bash
   docker-compose exec client ssh -p 8822 your_username@login.lxp.lu
   ```

### Container Issues

1. **View logs**:
   ```bash
   docker compose logs -f client
   ```

2. **Rebuild image**:
   ```bash
   docker compose build --no-cache client
   ```

3. **Shell access**:
   ```bash
   docker compose exec client bash
   ```

### Network Issues

1. **Check port availability**:
   ```bash
   netstat -tlnp | grep 8002
   ```

2. **Test API**:
   ```bash
   curl http://localhost:8002/docs
   ```

## Development

### Hot Reload

The Docker setup mounts the source code, so changes are reflected immediately:

```bash
# Edit files in services/client/src/
# Changes are automatically picked up
```

### Debugging

1. **Enable debug logging**:
   ```bash
   LOG_LEVEL=DEBUG docker compose up client
   ```

2. **Interactive mode**:
   ```bash
   docker compose run --rm client bash
   ```

## Migration from Apptainer

If you were previously running client service on MeluXina with Apptainer:

1. Stop the Apptainer-based client service
2. Set up the Docker environment locally
3. Update any scripts that reference the old client service address
4. The client code on MeluXina remains the same (still uses Apptainer)

## Performance Notes

- The Docker container uses host networking for better performance
- SSH connections are reused when possible
- Code synchronization only happens when necessary
- Reverse tunnels are established per benchmark to avoid conflicts