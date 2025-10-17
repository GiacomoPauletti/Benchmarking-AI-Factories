# Docker Compose Structure

This project uses a multi-service architecture with Docker Compose.

## Directory Structure

```
Benchmarking-AI-Factories/
├── docker-compose.yml           # Main compose file (all services)
├── docker-compose.dev.yml       # Development overrides
├── .env                         # Environment variables (create from .env.example)
├── .env.example                 # Template for environment configuration
└── services/
    ├── server/                  # Main API server
    │   ├── launch_local.sh     # Convenience launcher
    │   └── .env.local          # Server-specific configuration
    ├── client/                  # Client CLI/UI
    ├── monitoring/              # Monitoring service
    └── logs/                    # Log aggregation
```

## Setup

### 1. Configure Environment

First time setup:
```bash
# Copy the template
cp .env.example .env

# Edit with your credentials
nano .env
```

Required configuration:
- `SSH_USER` - Your MeluXina username
- `SSH_KEY_PATH` - Path to your SSH private key
- `REMOTE_BASE_PATH` - Update with your username

## Usage

### Running Specific Services

**Server only:**
```bash
# From project root
docker compose up server

# Or use the launcher (syncs recipes + starts server)
./services/server/launch_local.sh
```

**All services:**
```bash
docker compose up
```

**Development mode (with hot-reload):**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up server
```

### Management Commands

**Stop services:**
```bash
docker compose down
```

**Rebuild and restart:**
```bash
docker compose up --build server
```

**View logs:**
```bash
docker compose logs -f server
```

**Shell into container:**
```bash
docker compose exec server bash
```

## Configuration

**Root-level configuration** (`.env`):
- SSH connection details (host, port, user, key path)
- Remote base path on MeluXina
- Global application settings

**Service-specific configuration** (`services/<service>/.env.local`):
- Service-specific overrides
- Additional environment variables

The root `.env` file is automatically loaded by docker-compose.
Service `.env.local` files provide additional configuration.

## Adding New Services

Edit `docker-compose.yml` and uncomment/configure the service sections:
- `client`
- `monitoring`
- `logs`
