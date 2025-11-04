````markdown
# AI Factory Client Services

A comprehensive suite of services for managing and coordinating AI benchmarking clients on HPC infrastructures with Slurm.

## 🎯 Overview

The AI Factory Client Services system is designed to orchestrate performance tests on distributed AI services. It provides a scalable architecture for launching and managing client groups that execute coordinated benchmarks against AI servers.

### Main Components

- **Client Service**: FastAPI service for client group management
- **VLLMClient**: Specialized client for vLLM service interactions
- **Slurm Integration**: Native integration with Slurm scheduler for HPC deployment
- **Container Support**: Complete support for Apptainer container execution

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Slurm cluster access (for HPC deployment)
- Valid JWT token for Slurm REST API
- Apptainer (optional, for container mode)

### Installation

```bash
# Clone repository
git clone <repository-url>
cd Benchmarking-AI-Factories/services/client

# Install dependencies
pip install -r requirements.txt

# Build containers (optional)
./scripts/build_all.sh
```

### Quick Launch

```bash
# Start client service
python src/main.py http://your-server:8000

# With custom Slurm configuration
python src/main.py http://your-server:8000 config/slurm.conf

# With container support
python src/main.py http://your-server:8000 --container
```

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
- **Slurm Integration**: Automatic job dispatch on HPC clusters

### Client Layer
- **VLLMClient**: Specialized client for vLLM services
- **ClientGroup**: Local client group management
- **Observer Pattern**: Notification system for monitoring

### Deployment Layer
- **Container Support**: Execution in Apptainer containers
- **Slurm Dispatcher**: Automatic job submission
- **Configuration Management**: Credentials and configuration management

## 🔧 Typical Workflow

1. **Start Client Service**
   ```bash
   python src/main.py http://ai-server:8000
   ```

2. **Create Client Group** (via API)
   ```bash
   curl -X POST http://client-service:8001/api/v1/client-group/123 \
     -H "Content-Type: application/json" \
     -d '{"num_clients": 5, "time_limit": 10}'
   ```

3. **Client Process Registration** (automatic via Slurm)
   - System automatically dispatches Slurm jobs
   - Clients register with service on startup

4. **Benchmark Execution**
   ```bash
   curl -X POST http://client-service:8001/api/v1/client-group/123/run
   ```

## 🧪 Testing

The project includes a comprehensive test suite:

```bash
# Run all tests
./scripts/run_tests.sh

# Specific tests
./scripts/run_tests.sh --module client --verbose

# With coverage
./scripts/run_tests.sh --coverage

# Container mode (unit + integration tests)
./scripts/run_tests.sh --container

# Integration tests only
./scripts/run_tests.sh --integration
```

See `tests/README.md` for complete testing system documentation.

## 📚 In-Depth Documentation

- **[Architecture Guide](docs/architecture.md)**: Detailed system architecture
- **[API Reference](docs/api-reference.md)**: Complete API documentation
- **[Slurm Integration](docs/slurm-integration.md)**: HPC integration guide
- **[Deployment Guide](docs/deployment-guide.md)**: Deployment procedures
- **[Scripts Documentation](scripts/README.md)**: Scripts usage guide

## 🛠️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SLURM_JWT` | JWT token for Slurm API | Auto-generated |
| `USER` | Username for Slurm | Auto-detected |

### Configuration Files

Example `slurm.conf`:
```
url=http://slurmrestd.cluster.domain:6820
user_name=myuser
api_ver=v0.0.40
account=myaccount
jwt=<token-if-available>
```

## 🐳 Container Mode

The system supports complete container execution:

```bash
# Build containers
./scripts/build_all.sh

# Launch with container mode
python src/main.py http://server:8000 --container
```

Containers use Apptainer for HPC compatibility and include all necessary dependencies.

## 🔍 Troubleshooting

### Common Issues

**Invalid Slurm token**
```bash
# Verify token
scontrol token

# Regenerate if needed
export SLURM_JWT=$(scontrol token | grep SLURM_JWT | cut -d= -f2)
```

**Connection problems**
- Verify that AI server is reachable
- Check firewall and open ports
- Verify Slurm network configuration

**Container issues**
- Ensure Apptainer is installed
- Verify permissions for container build
- Check available disk space

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

**Version**: 1.0.0  
**Compatibility**: Python 3.8+, Slurm 20.02+  
**Last updated**: October 2025