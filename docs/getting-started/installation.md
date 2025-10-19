# Installation Guide

This page provides detailed installation instructions for the AI Factory Benchmarking Framework.

## Prerequisites

### System Requirements

- **Operating System**: Linux (tested on MeluXina with Red Hat Enterprise Linux)
- **CPU**: Multi-core processor (4+ cores recommended)
- **RAM**: 16GB+ recommended for development
- **Storage**: 50GB+ free space (for containers and models)

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.11+ | Server service and scripts |
| Apptainer/Singularity | 1.2.4+ | Container runtime |
| SLURM | Latest | Job scheduling |
| Git | 2.0+ | Version control |

### MeluXina Modules

```bash
module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0
```

## Installation Steps

### 1. Clone Repository

```bash
cd $HOME
git clone https://github.com/GiacomoPauletti/Benchmarking-AI-Factories.git
cd Benchmarking-AI-Factories
```

### 2. Install Python Dependencies

#### Server Service

```bash
cd services/server
pip install -r requirements.txt
```

Required packages:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pyyaml` - YAML parsing
- `requests` - HTTP client
- `pydantic` - Data validation

#### Documentation (Optional)

```bash
cd ../..
pip install -r docs-requirements.txt
```

### 3. Verify Installation

```bash
# Check Python version
python --version  # Should be 3.11+

# Check Apptainer
apptainer --version  # Should be 1.2.4+

# Check SLURM
sinfo  # Should show cluster info
```

## Configuration

### Environment Variables

Set up required environment variables:

```bash
# Add to ~/.bashrc or ~/.bash_profile
export SERVER_BASE_PATH="$HOME/Benchmarking-AI-Factories/services/server"
```

### SLURM Account

Verify you have access to a SLURM project:

```bash
sacctmgr show user $USER
```

You should see your project allocation (e.g., `p200981`).

### File Permissions

Make scripts executable:

```bash
chmod +x services/server/launch_server.sh
chmod +x services/server/run-tests.sh
chmod +x services/server/server-shell.sh
chmod +x build-docs.sh
```

## Building Containers

### Server Container

```bash
cd services/server

# Build the server container
apptainer build server.sif server.def
```

**Build time**: ~5-10 minutes (first time only)

### Test Container

```bash
cd tests

# Build the test container
apptainer build --fakeroot test-container.sif test-container.def
```

## Verification

### Run Health Check

```bash
cd services/server

# Start server on current node (for testing)
./launch_server.sh --use-current-node

# In another terminal, check health
curl http://$(hostname):8001/health
```

Expected response:
```json
{
  "status": "healthy"
}
```

### Run Tests

```bash
cd services/server
./run-tests.sh
```

All tests should pass.

## Troubleshooting

### Module Load Fails

**Issue**: `module: command not found`

**Solution**:
```bash
source /etc/profile.d/modules.sh
```

### Apptainer Build Permission Denied

**Issue**: Cannot create container in shared directory

**Solution**:
```bash
# Use --fakeroot flag
apptainer build --fakeroot server.sif server.def

# Or build in home directory
cd $HOME
apptainer build server.sif $HOME/Benchmarking-AI-Factories/services/server/server.def
```

### Python Package Installation Fails

**Issue**: No permission to install packages

**Solution**:
```bash
# Install in user space
pip install --user -r requirements.txt
```

### SLURM Job Submission Fails

**Issue**: Invalid account or partition

**Solution**:
```bash
# Check available partitions
sinfo

# Check your accounts
sacctmgr show user $USER

# Update launch_server.sh with your account
# Edit line: salloc -A p200981 ...
```

## Next Steps

- [Quick Start Guide](quickstart.md) - Run your first service
- [Architecture Overview](../architecture/overview.md) - Understand the system
- [Development Setup](../development/setup.md) - Set up for development

---

**Installation complete!** Continue to the [Quick Start](quickstart.md) guide.
