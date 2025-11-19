````markdown
# AI Factory Client Services

A comprehensive suite of services for managing and coordinating AI benchmarking clients for local execution.

## 🎯 Overview

The AI Factory Client Services system is designed to orchestrate performance tests on AI services running locally. It provides a scalable architecture for launching and managing client groups that execute coordinated benchmarks against AI servers.

### Main Components

- **Client Service**: FastAPI service for client group management
- **VLLMClient**: Specialized client for vLLM service interactions
- **Local Execution**: Native Python process execution for load testing
- **No Containerization**: Direct execution without containers for simplicity

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Docker & Docker Compose (for containerized services)

### Installation

```bash
# Clone repository
git clone <repository-url>
cd Benchmarking-AI-Factories

# Set up environment (if needed)
cp .env.example .env

# Start all services
docker compose up -d

# Or start only client service
docker compose up -d client

# View logs
docker compose logs -f client

# Stop services
docker compose down
```

### Configuration

The client service runs locally and does not require SSH or SLURM configuration.

### Custom Configuration

You can override default settings using environment variables:

```bash
# Custom server address and port
CLIENT_SERVICE_SERVER_ADDR=http://192.168.1.100:8001 \
CLIENT_SERVICE_PORT=8002 \
docker compose up -d client
```

### Architecture

- **Client Service**: Runs locally (in Docker container or natively)
- **Clients**: Run as local Python processes on the same machine
- **Communication**: Direct HTTP communication (no SSH tunnels needed)
- **Deployment**: Local subprocess execution for load generators

### Key Features

- 🐳 **Docker-first**: Simple `docker compose up -d client` to start
- 🔄 **Hot Reload**: Source code changes reflected immediately
- 📊 **API Documentation**: Auto-generated at http://localhost:8002/docs
- 🏗️ **Local Execution**: No HPC cluster or SLURM required
- 📦 **No Containers**: Direct Python execution for clients

## 📁 Repository Organization

```
services/client/
├── README.md                    # This documentation
├── docs/                        # In-depth documentation
│   ├── architecture.md          # System architecture
│   ├── api-reference.md         # Complete API reference
│   ├── slurm-integration.md     # Slurm integration guide
│   └── deployment-guide.md      # Deployment guide
├── scripts/                     # Automation scripts
│   ├── README.md                # Scripts documentation
│   ├── build_all.sh            # Unified container build
│   ├── build_client_container.sh
│   ├── build_service_container.sh
│   ├── run_tests.sh             # Test runner
│   └── start_*.sh               # Launch scripts
├── src/                         # Source code
│   ├── main.py                  # Main entry point
│   ├── client/                  # Client components
│   │   ├── client.py           # VLLMClient implementation
│   │   ├── client_group.py     # Client group management
│   │   └── api/                # Client-side APIs
│   └── client_service/         # Management services
│       ├── api/                # Service-side APIs
│       ├── client_manager/     # Client management
│       └── deployment/         # Deployment components
├── tests/                       # Complete test suite
│   ├── README.md               # Testing documentation
│   └── ...                     # Tests for each component
└── requirements.txt            # Python dependencies
```

## 🏗️ Architecture

### Service Layer
- **ClientManager**: Singleton for client group management
- **Frontend API**: Endpoints for group creation/management
- **Local Execution**: Automatic process spawning for load tests

### Client Layer
- **VLLMClient**: Specialized client for vLLM services
- **ClientGroup**: Local client group management
- **Observer Pattern**: Notification system for monitoring

### Deployment Layer
- **Local Execution**: Python subprocess-based execution
- **Configuration Management**: Load test configuration management

## 🔧 Typical Workflow

1. **Start Client Service**
   ```bash
   python src/main.py http://ai-server:8000
   ```

2. **Create Client Group** (via API)
   ```bash
   curl -X POST http://localhost:8002/api/v1/client-groups \
     -H "Content-Type: application/json" \
     -d '{"target_url": "http://localhost:8001", "service_id": "test", "num_clients": 5, "requests_per_second": 1.0, "duration_seconds": 60, "prompts": ["Hello"], "time_limit": 10}'
   ```

3. **Client Process Registration** (automatic)
   - System automatically spawns local Python processes
   - Clients run in background and execute load tests

4. **Monitor Results**
   - Check logs in `./logs/` directory
   - View results JSON files for detailed metrics

## 🧪 Testing

The project includes a comprehensive test suite:

```bash
# Run all tests
./scripts/run_tests.sh

# Specific tests
./scripts/run_tests.sh --module client --verbose

# With coverage
./scripts/run_tests.sh --coverage
```

See `tests/README.md` for complete testing system documentation.

## 📚 In-Depth Documentation

- **[Architecture Guide](docs/architecture.md)**: Detailed system architecture
- **[API Reference](docs/api-reference.md)**: Complete API documentation
- **[Deployment Guide](docs/deployment-guide.md)**: Deployment procedures
- **[Scripts Documentation](scripts/README.md)**: Scripts usage guide

## 🛠️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLIENT_SERVICE_PORT` | Port for client service | 8002 |
| `CLIENT_SERVICE_SERVER_ADDR` | Server address | http://localhost:8001 |

## 🔍 Troubleshooting

### Common Issues

**Port already in use**
```bash
# Change the port
CLIENT_SERVICE_PORT=8003 python src/main.py
```

**Connection problems**
- Verify that AI server is reachable
- Check firewall and open ports
- Verify network configuration

**Process issues**
- Check available system resources
- Verify Python dependencies are installed
- Check available disk space for logs

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Implement with tests
4. Update documentation
5. Submit pull request

### Development Standards

- Every new feature must have corresponding tests
- API documentation must be updated
- Follow existing naming conventions
- Integration tests for complete workflows

## 📄 License

See LICENSE file in repository root.

## 🆘 Support

For issues and questions:
- Create GitHub issues
- Consult documentation in `docs/`
- Check troubleshooting section

---

**Version**: 2.0.0  
**Compatibility**: Python 3.8+  
**Last updated**: November 2025