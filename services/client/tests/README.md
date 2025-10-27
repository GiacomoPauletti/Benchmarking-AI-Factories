````markdown
# AI Factory Client Services - Test Suite

This directory contains comprehensive unit and integration tests for all components of the AI Factory Client Services system.

## Test Modes

The test suite supports three different execution modes:

### 1. Local Mode (Default)
- Runs unit tests with mocks
- No external services required
- Fast execution, isolated testing
- Perfect for development and CI/CD

### 2. Container Mode
- Builds Apptainer container on Slurm
- Runs unit tests + integration tests
- Automatically starts required services
- Production-like environment testing

### 3. Integration Mode
- Runs integration tests against live services
- Requires external Client Service and AI Server
- End-to-end workflow validation

## Test Structure

The test suite follows the same hierarchical structure as the source code:

```
tests/
├── __init__.py
├── test_main.py                    # Main application tests
├── client/                         # Core client components
│   ├── __init__.py
│   ├── test_client.py             # VLLMClient class tests
│   ├── test_client_group.py       # ClientGroup singleton tests
│   ├── test_client_observer.py    # ClientObserver pattern tests
│   └── api/                       # Client API tests
│       ├── __init__.py
│       ├── test_client_service_router.py  # Client service API
│       └── test_monitor_router.py         # Monitor proxy API
├── client_service/                # Service management components
│   ├── __init__.py
│   ├── api/                       # Service API tests
│   │   ├── __init__.py
│   │   ├── test_frontend_router.py    # Frontend API
│   │   ├── test_client_router.py     # Client registration API
│   │   └── test_monitor_router.py    # Monitor service API
│   ├── client_manager/            # Client management tests
│   │   ├── __init__.py
│   │   ├── test_client_manager.py    # ClientManager singleton
│   │   └── test_client_group.py     # Service-side ClientGroup
│   └── deployment/                # Deployment component tests
│       ├── __init__.py
│       ├── test_client_dispatcher.py # Slurm job dispatch
│       ├── test_slurm_config.py     # Slurm configuration
│       └── test_slurm_token.py      # JWT token handling
├── integration/                   # Integration tests
│   ├── __init__.py
│   ├── test_integration.py        # End-to-end workflow tests
│   └── mock_ai_server.py          # Mock AI server for testing
├── test-container.def             # Apptainer container definition
└── scripts/
    └── run_tests.sh               # Test runner script
```

## Test Coverage

### Unit Tests (Local/Container Mode)

- **VLLMClient** (`test_client.py`)
  - Client initialization and ID management
  - Static service management (`setup_benchmark`)
  - Dynamic server configuration
  - HTTP communication with vLLM services
  - Observer pattern integration
  - Error handling and edge cases

- **ClientGroup** (`test_client_group.py`)
  - Singleton pattern implementation
  - Thread safety
  - Client management and configuration
  - Observer registration
  - Status reporting

- **ClientObserver** (`test_client_observer.py`)
  - Observer pattern interface
  - Inheritance and customization
  - Update notification handling

- **Client APIs** (`client/api/`)
  - Client service router endpoints
  - Monitor proxy integration
  - Request/response validation
  - Error handling

- **Service APIs** (`client_service/api/`)
  - Frontend API lifecycle management
  - Client registration endpoints
  - Monitor service integration
  - REST API validation

- **Client Management** (`client_service/client_manager/`)
  - ClientManager singleton pattern
  - Thread-safe operations
  - Service-side client group management
  - Slurm integration

- **Deployment Components** (`client_service/deployment/`)
  - Slurm job dispatcher
  - Configuration management
  - JWT token handling
  - Container support

### Integration Tests (Container/Integration Mode)

- **Client Service API** (`test_integration.py`)
  - Complete API workflow testing
  - Client group lifecycle management
  - Client registration and connection
  - Error handling and edge cases

- **Mock AI Server** (`mock_ai_server.py`)
  - OpenAI-compatible API endpoints
  - Model management simulation
  - Completion and chat completion
  - Statistics and health monitoring

- **End-to-End Workflows** 
  - Complete benchmark setup and execution
  - Service communication validation
  - Error recovery and cleanup
  - Production scenario simulation

## Running Tests

### Quick Start

```bash
# Local unit tests (default)
./scripts/run_tests.sh

# Container tests (unit + integration)
./scripts/run_tests.sh --container

# Integration tests only (requires services)
./scripts/run_tests.sh --integration

# Run with verbose output
./scripts/run_tests.sh --verbose

# Run specific module
./scripts/run_tests.sh --module client

# Run with coverage
./scripts/run_tests.sh --coverage
```

### Test Modes Detailed

#### Local Mode (Default)
```bash
# Run all unit tests locally
./scripts/run_tests.sh

# Run with coverage and verbose output
./scripts/run_tests.sh --coverage --verbose

# Run specific module only
./scripts/run_tests.sh --module client_service

# Run tests matching pattern
./scripts/run_tests.sh --pattern "*router*"
```

**Features:**
- Fast execution (no container build)
- Isolated unit testing with mocks
- No external dependencies required
- Perfect for development workflow

#### Container Mode
```bash
# Run full test suite in container
./scripts/run_tests.sh --container
```

**What happens:**
1. Builds Apptainer test container
2. Requests Slurm compute resources (30min, 8GB RAM)
3. Runs unit tests in container
4. Starts Client Service and Mock AI Server
5. Runs integration tests
6. Generates coverage reports
7. Cleans up all services

**Features:**
- Production-like testing environment
- Automatic service orchestration
- Complete test coverage (unit + integration)
- Coverage reports generated

**Outputs:**
- `tests/unit-test.log` - Unit test results
- `tests/integration-test.log` - Integration test results
- `tests/coverage-test.log` - Coverage analysis
- `tests/htmlcov/` - HTML coverage report

#### Integration Mode
```bash
# Run integration tests against live services
export CLIENT_SERVICE_ADDR="http://client-service:8001"
export AI_SERVER_ADDR="http://ai-server:8000"
./scripts/run_tests.sh --integration

# Or run specific integration test class
./scripts/run_tests.sh --module integration
```

**Prerequisites:**
- Running Client Service at `$CLIENT_SERVICE_ADDR`
- Running AI Server at `$AI_SERVER_ADDR`
- Network connectivity to both services

**Features:**
- Tests against real service deployments
- End-to-end workflow validation
- Production environment testing

### Available Options

```bash
./scripts/run_tests.sh --help
```

**Local Testing Options:**
- `--verbose, -v`: Detailed test output
- `--coverage`: Generate coverage reports
- `--module MODULE`: Run specific module tests
- `--list-modules`: Show available test modules
- `--failfast`: Stop on first failure
- `--pattern PATTERN`: Run tests matching pattern

**Mode Selection Options:**
- `--container`: Run in Apptainer container (unit + integration)
- `--integration`: Run integration tests only (requires services)

**Examples:**
```bash
# Container testing
./scripts/run_tests.sh --container

# Local testing with coverage
./scripts/run_tests.sh --coverage --verbose

# Integration testing
./scripts/run_tests.sh --integration

# Module-specific testing
./scripts/run_tests.sh --module client_service.api

# Pattern-based testing
./scripts/run_tests.sh --pattern "*client*"
```

### Module-Specific Testing

```bash
# Test only client components
./scripts/run_tests.sh --module client

# Test only APIs
./scripts/run_tests.sh --module client.api
./scripts/run_tests.sh --module client_service.api

# Test deployment components
./scripts/run_tests.sh --module client_service.deployment

# Test client management
./scripts/run_tests.sh --module client_service.client_manager
```

### Pattern-Based Testing

```bash
# Run only VLLMClient tests
./scripts/run_tests.sh --pattern "*client*"

# Run only API tests
./scripts/run_tests.sh --pattern "*api*"

# Run only singleton pattern tests
./scripts/run_tests.sh --pattern "*singleton*"
```

## Test Design Principles

### 1. Isolation
- Each test is independent and can run in any order
- Mock external dependencies (HTTP requests, file system, etc.)
- Reset singleton instances between tests

### 2. Comprehensive Coverage
- Test normal operation paths
- Test error conditions and edge cases
- Test boundary conditions
- Test thread safety where applicable

### 3. Clear Structure
- Descriptive test names that explain what is being tested
- Setup and teardown methods for clean test environments
- Grouped related tests in logical classes

### 4. Mocking Strategy
- Mock external HTTP requests using `unittest.mock`
- Mock file system operations
- Mock time-dependent operations
- Preserve actual business logic testing

### 5. No Integration Testing
- Tests focus on individual classes and methods
- No testing of communication between services
- No testing of actual HTTP client-server communication
- No testing of real Slurm job submission

## Dependencies

### Local Mode Dependencies
- Python 3.8+
- `unittest` framework (built-in)
- `unittest.mock` for mocking (built-in)
- `fastapi` and `fastapi.testclient` for API testing
- `requests` for HTTP client testing (mocked)
- Standard library modules: `threading`, `time`, `json`, `base64`

### Container Mode Dependencies
- Slurm cluster access
- Apptainer/Singularity
- Container build permissions
- Network access for service communication
- All dependencies installed automatically in container

### Integration Mode Dependencies
- Running Client Service instance
- Running AI Server instance (or mock)
- Network connectivity to services
- `requests` library for HTTP testing
- Environment variables for service endpoints

## Coverage Reporting

### Local Mode Coverage
```bash
./scripts/run_tests.sh --coverage
```
Generates:
1. **Console Report**: Summary of coverage percentages
2. **HTML Report**: Detailed line-by-line coverage in `htmlcov/` directory

### Container Mode Coverage
Coverage is automatically generated in container mode:
- Console summary displayed during test run
- HTML report saved to `tests/htmlcov/`
- Coverage log saved to `tests/coverage-test.log`

To view HTML coverage report:
```bash
# After local coverage run
open htmlcov/index.html

# After container run
open tests/htmlcov/index.html
```

## Troubleshooting

### Local Mode Issues

**Import Errors**
Tests add the `src/` directory to Python path automatically. If you encounter import errors:
1. Ensure you're running tests from the client service root directory
2. Check that all `__init__.py` files exist
3. Verify the test runner script has execute permissions

**Test Failures**
1. Check if all dependencies are installed
2. Ensure Python 3.8+ is being used
3. Run individual modules to isolate issues:
   ```bash
   ./scripts/run_tests.sh --module client --verbose
   ```

**Mock Issues**
If mocks aren't working as expected:
1. Verify mock paths match the actual import structure
2. Check that mocks are patched before the tested code imports modules
3. Use `--verbose` flag to see detailed test output

### Container Mode Issues

**Container Build Failures**
1. Check Apptainer module availability: `module load Apptainer`
2. Verify container definition syntax
3. Check network access for package downloads
4. Try building manually: `apptainer build test.sif test-container.def`

**Slurm Resource Issues**
1. Check Slurm account and partition access
2. Verify resource availability: `sinfo`
3. Check job queue: `squeue -u $USER`
4. Try shorter time limits or fewer resources

**Service Startup Issues**
1. Check port availability in container
2. Verify service health endpoints
3. Check container logs for startup errors
4. Increase service startup timeouts

### Integration Mode Issues

**Service Connectivity**
1. Verify service URLs are correct
2. Check network connectivity: `curl -f $CLIENT_SERVICE_ADDR/docs`
3. Ensure services are running and healthy
4. Check firewall and proxy settings

**Authentication Issues**
1. Verify service authentication requirements
2. Check if JWT tokens are needed
3. Ensure environment variables are set correctly

**Test Environment Issues**
1. Services might be in inconsistent state
2. Try restarting services before testing
3. Check service logs for errors
4. Verify test data cleanup between runs

### Performance Issues

**Slow Test Execution**
```bash
# Run specific modules only
./scripts/run_tests.sh --module client

# Skip coverage for faster execution
./scripts/run_tests.sh --verbose

# Use fail-fast to identify issues quickly
./scripts/run_tests.sh --failfast
```

**Container Resource Limits**
If container tests are slow or failing due to resources:
1. Check Slurm job limits
2. Increase memory allocation in container script
3. Reduce parallel test execution
4. Use faster storage for container builds

### Log Analysis

**Local Mode Logs**
```bash
# Verbose output shows detailed test results
./scripts/run_tests.sh --verbose 2>&1 | tee test-output.log

# Coverage logs
./scripts/run_tests.sh --coverage | grep -A5 "TOTAL"
```

**Container Mode Logs**
```bash
# Container logs are saved automatically
cat tests/unit-test.log
cat tests/integration-test.log
cat tests/coverage-test.log

# Slurm job logs
ls -la slurm-*.out slurm-*.err
```

**Integration Mode Logs**
```bash
# Integration tests with verbose output
./scripts/run_tests.sh --integration --verbose

# Service-specific logs
curl $CLIENT_SERVICE_ADDR/docs  # Check service health
curl $AI_SERVER_ADDR/health     # Check AI server health
```

## Contributing

When adding new components:

1. **Create corresponding test files** following the naming convention `test_*.py`
2. **Add comprehensive test coverage** for all public methods and edge cases
3. **Update this README** to document the new test modules
4. **Update the test runner script** if new test directories are added
5. **Add integration tests** for new APIs or end-to-end workflows

### Test Naming Convention
- Test files: `test_<module_name>.py`
- Test classes: `Test<ClassName>`
- Test methods: `test_<specific_behavior>`

Example:
```python
class TestVLLMClient(unittest.TestCase):
    def test_initialization_with_default_recipe(self):
        # Test implementation
        pass
    
    def test_setup_benchmark_success(self):
        # Test implementation
        pass
```

### Adding Integration Tests

For new integration test scenarios:

1. **Add test methods** to `tests/integration/test_integration.py`
2. **Update mock server** if new endpoints are needed
3. **Document service requirements** in test docstrings
4. **Test both success and failure scenarios**

Example integration test:
```python
class TestNewFeature(BaseIntegrationTest):
    def test_new_workflow(self):
        """Test new workflow end-to-end"""
        # Setup
        benchmark_id = self.get_unique_id()
        
        # Test implementation
        response = requests.post(f"{self.client_service_url}/new-endpoint")
        self.assertEqual(response.status_code, 200)
        
        # Cleanup
        self.cleanup_benchmark(benchmark_id)
```

### Container Development

When modifying container behavior:

1. **Update container definition** in `tests/test-container.def`
2. **Test container build** locally before committing
3. **Update container script** in `run-tests.sh` if needed
4. **Document resource requirements** if changed

### CI/CD Integration

The test suite is designed for CI/CD integration:

```yaml
# Example GitHub Actions workflow
- name: Run Unit Tests
  run: ./scripts/run_tests.sh --coverage

- name: Run Container Tests
  run: ./scripts/run_tests.sh --container
  if: github.event_name == 'pull_request'
```

## Test Suite Architecture

### Design Principles

1. **Three-Tier Testing**
   - **Unit Tests**: Fast, isolated, mocked dependencies
   - **Integration Tests**: Service-to-service communication
   - **Container Tests**: Production-like environment

2. **Isolation**
   - Each test is independent and can run in any order
   - Mock external dependencies (HTTP requests, file system, etc.)
   - Reset singleton instances between tests
   - Clean test data and state

3. **Comprehensive Coverage**
   - Test normal operation paths
   - Test error conditions and edge cases
   - Test boundary conditions
   - Test thread safety where applicable

4. **Clear Structure**
   - Descriptive test names that explain what is being tested
   - Setup and teardown methods for clean test environments
   - Grouped related tests in logical classes
   - Consistent patterns across test modules

5. **Production Readiness**
   - Container tests simulate HPC environment
   - Integration tests validate real-world scenarios
   - Performance and load considerations
   - Resource cleanup and error handling

This comprehensive test suite ensures the reliability and maintainability of the AI Factory Client Services system across development, staging, and production environments.
````