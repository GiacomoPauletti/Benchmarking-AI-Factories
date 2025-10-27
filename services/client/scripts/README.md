# AI Factory Client Services - Scripts Documentation

This directory contains scripts for building, testing, and running the AI Factory Client Services system.

## 📄 Available Scripts

### 🧪 Testing

#### `run_tests.sh`
Comprehensive test runner for all AI Factory Client Service components.

**Usage:**
```bash
./run_tests.sh [OPTIONS]
```

**Key Options:**
- `--help` - Show complete help with all options
- `--verbose` - Run tests with detailed output
- `--coverage` - Generate coverage report with HTML output
- `--module MODULE` - Run tests for specific module only (client, client_service, etc.)
- `--container` - Run full test suite in Apptainer container with integration tests
- `--integration` - Run integration tests against live services
- `--list-modules` - Show all available test modules

**Examples:**
```bash
./run_tests.sh                    # Run all unit tests locally
./run_tests.sh --coverage         # Run with coverage report
./run_tests.sh --module client    # Test only client components
./run_tests.sh --container        # Full container testing with services
```

### 🐳 Container Building

#### `build_all.sh`
Builds both client service and client containers in sequence.

**Usage:**
```bash
./build_all.sh [--force] [--local] [--help]
```

**Options:**
- `--force` - Force rebuild even if containers exist
- `--local` - Build on login node (default: use Slurm compute nodes)
- `--help` - Show detailed help

Creates:
- `../src/client_service.sif` - Client service container
- `../src/client/client_container.sif` - Client container

#### `build_service_container.sh`
Builds only the client service container.

**Usage:**
```bash
./build_service_container.sh [--force] [--local]
```

Creates the Apptainer container for the AI Factory Client Service using `../src/service_container.def`.

#### `build_client_container.sh`
Builds only the client container.

**Usage:**
```bash
./build_client_container.sh [--force] [--local]
```

Creates the Apptainer container for AI Factory clients using `../src/client/client_container.def`.

### 🚀 Service Management

#### `start_client_service.sh`
Launches the AI Factory Client Service on Slurm compute nodes or locally.

**Usage:**
```bash
./start_client_service.sh <server_address> <time_allocation> [slurm_config_file] [OPTIONS]
```

**Parameters:**
- `server_address` - Address of the server service (e.g., `http://server-ip:8000`)
- `time_allocation` - Slurm time allocation (e.g., `30min`, `2h`, `1:30:00`)
- `slurm_config_file` - Optional Slurm configuration file

**Options:**
- `--local` - Run locally without Slurm allocation (testing only)
- `--container` - Run using Apptainer container
- `--use-current-node` - Use current node instead of requesting new allocation

**Examples:**
```bash
./start_client_service.sh http://localhost:8000 2h
./start_client_service.sh http://192.168.1.100:8000 30min --container
./start_client_service.sh http://localhost:8000 1h --local
```

### 🔧 Development Tools

#### `start_shell.sh`
Interactive shell for testing AI Factory client service APIs.

**Usage:**
```bash
./start_shell.sh [--test-local]
```

**Options:**
- `--test-local` - Run shell on login node for testing (default: use compute node)

Provides an interactive command-line interface with built-in functions for:
- Health checking (`test_health`)
- Client group management (`create_client_group`, `get_client_group`, `run_client_group`)
- Configuration management (`set_url`, `show_config`)

**Interactive Commands:**
- `set_url <url>` - Set client service URL
- `test_health` - Test service connectivity
- `create_client_group <id> [num_clients] [time_limit]` - Create client group
- `run_client_group <id>` - Start client group execution
- `help` - Show all available commands

## 📋 Prerequisites

### System Requirements
- **Slurm cluster access** for compute node execution
- **Apptainer/Singularity** for container operations
- **Python 3.8+** for native execution
- **Network connectivity** between nodes

### Environment Setup
The scripts are designed for use on Meluxina HPC cluster with:
- Account: `p200981`
- Default QoS: `default`
- Apptainer module: `Apptainer/1.2.4-GCCcore-12.3.0`

## 🎯 Common Workflows

### 1. Build and Test
```bash
# Build containers
./build_all.sh

# Run comprehensive tests
./run_tests.sh --container --coverage
```

### 2. Development Testing
```bash
# Local testing with coverage
./run_tests.sh --coverage --verbose

# Test specific module
./run_tests.sh --module client_service.api
```

### 3. Production Deployment
```bash
# Start client service in production mode
./start_client_service.sh http://ai-server:8000 8h --container

# Interactive testing
./start_shell.sh
```

### 4. Container Development
```bash
# Force rebuild containers
./build_all.sh --force

# Test container functionality
./run_tests.sh --container
```

## 📊 Output Locations

- **Test Results**: Console output with optional HTML coverage in `htmlcov/`
- **Container Images**: `../src/client_service.sif` and `../src/client/client_container.sif`
- **Log Files**: Service logs printed to console, Slurm logs in working directory
- **Temporary Files**: Automatically cleaned up after execution

## 🔍 Troubleshooting

### Common Issues
- **Permission errors**: Ensure scripts are executable (`chmod +x script.sh`)
- **Module loading failures**: Verify Apptainer module availability on compute nodes
- **Container build failures**: Check internet connectivity and disk space
- **Service connection issues**: Verify server address and network connectivity

### Debug Options
Most scripts support verbose output and detailed error messages. Use `--help` on any script for specific troubleshooting guidance.

All scripts are designed to provide clear error messages and suggestions for resolution when issues occur.
