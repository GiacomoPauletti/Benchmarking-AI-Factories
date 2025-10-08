# Testing Guide for AI Factory Server

## Container-based Testing (Recommended)

### Quick Start
```bash
# Build and run all tests in container
cd /home/users/u103056/Benchmarking-AI-Factories/services/server
./run-tests.sh
```

This will:
1. Build an Apptainer test container
2. Request interactive compute node (15min, 8GB RAM)
3. Launch your server using `launch_server.sh`
4. Run all tests (unit + integration + live API tests)
5. Clean up automatically

### What the Test Container Does

The test container (`test-container.def`) performs a complete workflow:

1. **Interactive Node**: Requests SLURM compute node for testing
2. **Unit Tests**: Fast tests without server (mocked)
3. **Server Launch**: Starts server using your existing `launch_server.sh` 
4. **Integration Tests**: Tests with live server endpoints
5. **Live API Tests**: Real HTTP calls to running server
6. **Cleanup**: Stops server and cleans up

### Manual Testing (Alternative)

If you prefer manual testing:

```bash
# Install test dependencies
cd /home/users/u103056/Benchmarking-AI-Factories/services/server
pip install -r tests/requirements-test.txt

# Run unit tests only (no server needed)
python -m pytest tests/test_api.py tests/test_slurm.py -v

# For integration tests, start server first:
cd /home/users/u103056/Benchmarking-AI-Factories
./launch_server.sh &

# Then run integration tests
cd services/server
python -m pytest tests/test_integration.py -v
```

## Test Structure

```
tests/
├── test-container.def         # Apptainer container for testing
├── test_api.py               # Unit tests (mocked)
├── test_slurm.py             # SLURM unit tests
├── test_integration.py       # Integration tests (live server)
├── conftest.py               # Test configuration
├── requirements-test.txt     # Test dependencies
└── README.md                 # This file
```

## Development Workflow

### 1. Make Changes
```bash
# Edit your server code
vim services/server/src/main.py
```

### 2. Test Changes
```bash
# Run comprehensive tests
cd services/server
./run-tests.sh
```

### 3. Commit if Tests Pass
```bash
git add .
git commit -m "Your changes"
git push origin feature/your-branch
```

## Container Benefits

✅ **Isolated Environment**: Tests run in clean container  
✅ **Complete Workflow**: Tests real server launch  
✅ **Compute Node**: Uses proper SLURM resources, not login node  
✅ **Supercomputer Compatible**: Works in SLURM environment  
✅ **Reproducible**: Same environment every time  
✅ **No Cleanup Needed**: Container handles everything  

## Troubleshooting

### Container Build Issues
```bash
# Check Apptainer is available
module load Apptainer/1.2.4-GCCcore-12.3.0

# Rebuild container
cd services/server/tests
rm -f test-container.sif
apptainer build test-container.sif test-container.def
```

### Server Launch Issues
- Check SLURM allocation is available
- Verify `launch_server.sh` works independently
- Check logs in `services/server/logs/`

### Test Failures
- Container logs show exactly which step failed
- Unit test failures: Fix code syntax/logic
- Integration test failures: Check server startup
- API test failures: Check endpoint responses

The container approach gives you confidence that your code works in the real supercomputer environment!