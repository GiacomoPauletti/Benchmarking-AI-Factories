# Testing Guide for AI Factory Server

## Quick Start

Run all tests with one command:

```bash
cd ~/Documents/Career_Academics/EUMaster4HPC/Courses/Semester_3/challenge/Benchmarking-AI-Factories
./services/server/run-tests.sh
```

This runs tests inside the Docker container (no MeluXina access needed for basic tests).

## Test Structure

```
tests/
├── test_api.py               # Unit tests (mocked, fast)
├── test_integration.py       # Integration tests (live server)
├── requirements-dev.txt      # Test dependencies
└── README.md                 # This file
```

## Running Tests Manually

### Option 1: Inside Docker Container (Recommended)

```bash
# Start the server
cd ~/Documents/Career_Academics/EUMaster4HPC/Courses/Semester_3/challenge/Benchmarking-AI-Factories
docker compose up -d server

# Install test dependencies
docker compose exec server pip install pytest pytest-mock

# Run unit tests
docker compose exec server python -m pytest tests/test_api.py -v

# Run integration tests (requires live server)
docker compose exec server python -m pytest tests/test_integration.py -v

# Run all tests
docker compose exec server python -m pytest tests/ -v
```

### Option 2: On MeluXina (Full End-to-End)

For testing actual SLURM job submission and vLLM services:

```bash
# SSH to MeluXina
ssh u103056@meluxina

# Navigate to project
cd ~/Benchmarking-AI-Factories

# Run integration tests (requires server running on MeluXina)
# TODO: Create run-tests-meluxina.sh for full end-to-end testing
```

## Test Types

### Unit Tests (`test_api.py`)
- **Fast** (~1 second)
- **Mocked** dependencies (SLURM, SSH, filesystem)
- **No external requirements**
- Tests API logic, validation, error handling

### Integration Tests (`test_integration.py`)  
- **Requires running server**
- Tests real HTTP endpoints
- Validates request/response flow
- No actual job submission (would need MeluXina)

## Continuous Integration

Tests are automatically run:
- Locally before commits (run `./run-tests.sh`)
- In CI/CD pipeline (GitHub Actions - TODO)
- Before merging PRs

## Writing New Tests

### Unit Test Example

```python
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

def test_my_endpoint(client):
    """Test description."""
    response = client.post("/api/v1/my-endpoint", json={...})
    assert response.status_code == 200
```

### Integration Test Example

```python
import requests

def test_live_endpoint(server_endpoint):
    """Test against live server."""
    response = requests.get(f"{server_endpoint}/health")
    assert response.status_code == 200
```

## Troubleshooting

**Tests failing with import errors?**
```bash
docker compose exec server pip install pytest pytest-mock
```

**Server not running?**
```bash
docker compose up -d server
docker compose logs -f server
```

**Need to debug?**
```bash
docker compose exec server bash
python -m pytest tests/test_api.py -v --pdb
```