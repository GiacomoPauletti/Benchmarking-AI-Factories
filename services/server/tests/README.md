# Testing Guide for AI Factory Server

## Running Tests

To run all tests, use the provided script:

```bash
cd path/to/Benchmarking-AI-Factories/services/server
./run-tests.sh
```

This script handles everything automatically: building the test container, requesting compute resources, launching the server, running tests, and cleaning up.

## What Happens

The `run-tests.sh` script:
1. Builds an Apptainer test container
2. Requests an interactive SLURM compute node (15min, 8GB RAM)
3. Launches a test server using `services/server/launch_server.sh`
4. Runs unit tests, integration tests, and live API tests
5. Cleans up 

## Test Structure

```
tests/
├── test-container.def        # Apptainer container definition
├── test_api.py               # Unit tests (mocked)
├── test_integration.py       # Integration tests (live server)
└── README.md                 # This file
```

## Test Logs

Test logs are saved to files in the `tests/` directory:
- `tests/unit-test.log` - Unit test output
- `tests/integration-test.log` - Integration test output

Server logs (when the test server is running) are in `services/server/logs/`.