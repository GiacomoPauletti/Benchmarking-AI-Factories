#!/bin/bash -l

# Test runner script for AI Factory Client Services
# This script runs all unit tests for the client service components

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$SCRIPT_DIR/.."
TESTS_DIR="$SCRIPT_DIR"
SRC_DIR="$CLIENT_DIR/src"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_separator() {
    echo "=================================================================================================="
}

# Function to show help
show_help() {
    cat << EOF
AI Factory Client Services Test Runner

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --help, -h          Show this help message
    --verbose, -v       Run tests with verbose output
    --coverage          Run tests with coverage report
    --module MODULE     Run tests for specific module only
    --list-modules      List available test modules
    --failfast          Stop on first test failure
    --pattern PATTERN   Run only tests matching pattern
    --container         Run tests in Apptainer container (includes integration tests)
    --integration       Run integration tests only (requires services)
    --skip-integration  Skip tests marked as integration (for container mode)

EXAMPLES:
    $0                              # Run all unit tests locally
    $0 --verbose                    # Run all tests with verbose output
    $0 --coverage                   # Run tests with coverage report
    $0 --container                  # Run all tests in container (unit + integration)
    $0 --integration                # Run integration tests only
    $0 --skip-integration           # Run tests but skip integration-marked tests
    $0 --module client              # Run only client module tests
    $0 --module client_service      # Run only client_service module tests
    $0 --pattern "*test_client*"    # Run tests matching pattern
    $0 --failfast --verbose         # Stop on first failure with verbose output

TEST MODES:
    Local Mode (default)    - Runs unit tests with mocks, no services required
    Container Mode          - Builds container, starts services, runs unit + integration tests
    Integration Mode        - Runs integration tests against live services

MODULES:
    client                 - VLLMClient, ClientGroup, ClientObserver
    client.api            - client_service_router, monitor_router
    client_service         - main module tests
    client_service.api     - frontend_router, client_router, monitor_router
    client_service.client_manager - ClientManager, ClientGroup
    client_service.deployment - client_dispatcher, slurm_config, slurm_token
    integration           - End-to-end integration tests

EOF
}

# Function to list test modules
list_modules() {
    print_status "Available test modules:"
    echo ""
    echo "  client                              - Core client components"
    echo "    ├── test_client.py               - VLLMClient class tests"
    echo "    ├── test_client_group.py         - ClientGroup singleton tests" 
    echo "    ├── test_client_observer.py      - ClientObserver pattern tests"
    echo "    └── api/"
    echo "        ├── test_client_service_router.py - Client service API tests"
    echo "        └── test_monitor_router.py        - Monitor proxy API tests"
    echo ""
    echo "  client_service                      - Service management components"
    echo "    ├── api/"
    echo "    │   ├── test_frontend_router.py  - Frontend API tests"
    echo "    │   ├── test_client_router.py    - Client registration API tests"
    echo "    │   └── test_monitor_router.py   - Monitor service API tests"
    echo "    ├── client_manager/"
    echo "    │   ├── test_client_manager.py   - ClientManager singleton tests"
    echo "    │   └── test_client_group.py     - Service ClientGroup tests"
    echo "    └── deployment/"
    echo "        ├── test_client_dispatcher.py - Slurm job dispatch tests"
    echo "        ├── test_slurm_config.py      - Slurm configuration tests"
    echo "        └── test_slurm_token.py       - JWT token handling tests"
    echo ""
    echo "  main                                - Main application tests"
    echo "    └── test_main.py                 - FastAPI app and CLI tests"
    echo ""
    echo "  integration                         - Integration tests (requires services)"
    echo "    └── test_integration.py          - End-to-end workflow tests"
    echo ""
}

# Function to check dependencies
check_dependencies() {
    print_status "Checking dependencies..."
    
    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        print_error "python3 not found. Please install Python 3.6 or later."
        exit 1
    fi
    
    # Check Python version
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    print_status "Using Python $python_version"
    
    # Check if required directories exist
    if [[ ! -d "$TESTS_DIR" ]]; then
        print_error "Tests directory not found: $TESTS_DIR"
        exit 1
    fi
    
    if [[ ! -d "$SRC_DIR" ]]; then
        print_error "Source directory not found: $SRC_DIR"
        exit 1
    fi
    
    print_success "Dependencies check passed"
}

# Function to run tests for a specific module
run_module_tests() {
    local module=$1
    local verbose=$2
    local coverage=$3
    local failfast=$4
    local pattern=$5
    
    # Always use flat-file testing mode: map module names to test file patterns
    local module_short="${module##*.}"
    local module_underscored="${module//./_}"
    local module_plain="${module//./-}"

    # Candidate patterns to search for matching test files (ordered)
    candidates=(
        "$TESTS_DIR/test_${module_short}.py"
        "$TESTS_DIR/test_${module_underscored}.py"
        "$TESTS_DIR/*${module_short}*.py"
        "$TESTS_DIR/*${module_underscored}*.py"
        "$TESTS_DIR/*${module_plain}*.py"
        "$TESTS_DIR/${module_underscored}.py"
    )

    found_files=()
    for p in "${candidates[@]}"; do
        for f in $p; do
            if [[ -f "$f" ]]; then
                found_files+=("$f")
            fi
        done
    done

    if [[ ${#found_files[@]} -eq 0 ]]; then
        print_error "No flat test files found for module: $module"
        print_error "Tried patterns: ${candidates[*]}"
        return 1
    fi

    test_path="${found_files[*]}"
    module_name="Flat-file test mode (${module})"
    print_status "Found flat test files for module '$module': $test_path"
    
    # Special handling for integration tests
    if [[ "$module" == "integration" ]]; then
        print_warning "Integration tests require live services"
        print_status "Make sure CLIENT_SERVICE_ADDR and AI_SERVER_ADDR are set"
        print_status "Or use --container to run with automatic service setup"
    fi
    
    print_status "Running tests for: $module_name"
    
    # Build Python command using pytest for better compatibility
    local python_cmd="python3 -m pytest $test_path"
    
    if [[ "$verbose" == "true" ]]; then
        python_cmd="$python_cmd -v"
    fi
    
    if [[ "$failfast" == "true" ]]; then
        python_cmd="$python_cmd -x"
    fi
    
    # Add pattern matching if specified
    if [[ -n "$pattern" ]]; then
        python_cmd="$python_cmd -k \"$pattern\""
    fi
    
    # Set PYTHONPATH to include src directory
    export PYTHONPATH="$SRC_DIR:$PYTHONPATH"
    
    # Run with or without coverage
    if [[ "$coverage" == "true" ]]; then
        if command -v coverage &> /dev/null; then
            print_status "Running with coverage..."
            eval "coverage run --source=\"$SRC_DIR\" $python_cmd"
        else
            print_warning "Coverage not available, running without it"
            eval "$python_cmd"
        fi
    else
        eval "$python_cmd"
    fi
}

# Function to run all tests
run_all_tests() {
    local verbose=$1
    local coverage=$2
    local failfast=$3
    local pattern=$4
    
    print_status "Running all AI Factory Client Service tests..."
    print_separator
    
    local modules=(
        "client"
        "client.api" 
        "client_service.api"
        "client_service.client_manager"
        "client_service.deployment"
        "main"
    )
    
    local total_modules=${#modules[@]}
    local passed_modules=0
    local failed_modules=()
    
    for module in "${modules[@]}"; do
        echo ""
        print_status "[$((passed_modules + ${#failed_modules[@]} + 1))/$total_modules] Testing module: $module"
        print_separator
        
        if run_module_tests "$module" "$verbose" "$coverage" "$failfast" "$pattern"; then
            print_success "Module $module passed"
            ((passed_modules++))
        else
            print_error "Module $module failed"
            failed_modules+=("$module")
            
            if [[ "$failfast" == "true" ]]; then
                break
            fi
        fi
    done
    
    # Print summary
    echo ""
    print_separator
    print_status "TEST SUMMARY"
    print_separator
    
    if [[ ${#failed_modules[@]} -eq 0 ]]; then
        print_success "All $passed_modules modules passed! 🎉"
        
        if [[ "$coverage" == "true" ]] && command -v coverage &> /dev/null; then
            echo ""
            print_status "Generating coverage report..."
            coverage report
            coverage html
            print_success "HTML coverage report generated in htmlcov/"
        fi
        
        return 0
    else
        print_error "$passed_modules modules passed, ${#failed_modules[@]} modules failed"
        print_error "Failed modules: ${failed_modules[*]}"
        return 1
    fi
}

# Function to run tests in container
run_container_tests() {
    print_status "Running tests using docker compose (docker-compose.test.yml)..."

    # Ensure docker compose is available
    if ! command -v docker &> /dev/null; then
        print_error "docker not found. Please install Docker to run container tests."
        return 1
    fi

    # Use the project root and docker-compose.test.yml to run the client-test service
    print_status "Project root: $PROJECT_ROOT"

    # Compose file path
    local dc_file="$PROJECT_ROOT/docker-compose.test.yml"
    if [[ ! -f "$dc_file" ]]; then
        print_error "docker-compose test file not found: $dc_file"
        return 1
    fi

    print_status "Starting docker-compose service: client-test"

    # Run the client-test service defined in the compose file
    # Allow skipping integration-marked tests when requested
    local pytest_marker_args=""
    if [[ "$SKIP_INTEGRATION" == "true" ]]; then
        pytest_marker_args="-m 'not integration'"
    fi

    if docker compose -f "$dc_file" run --rm \
        -e TESTING=true \
        client-test \
        bash -c "cd /app && pip install -q -r requirements-dev.txt && python -m pytest tests/ $pytest_marker_args -v --tb=short --color=yes"; then
        print_success "Container tests completed successfully!"
        return 0
    else
        print_error "Container tests failed or 'client-test' service not defined in $dc_file"
        print_status "Check $dc_file to ensure a 'client-test' service is configured similar to the server's compose file"
        return 1
    fi
}

# Function to run integration tests only
run_integration_tests() {
    local verbose=$1
    
    print_status "Running integration tests..."
    print_warning "Integration tests require live services:"
    print_warning "  - Client Service at \$CLIENT_SERVICE_ADDR"
    print_warning "  - AI Server at \$AI_SERVER_ADDR"
    
    # Check environment variables
    local client_service_addr="${CLIENT_SERVICE_ADDR:-http://localhost:8001}"
    local ai_server_addr="${AI_SERVER_ADDR:-http://localhost:8000}"
    
    print_status "Using service endpoints:"
    print_status "  Client Service: $client_service_addr"
    print_status "  AI Server: $ai_server_addr"
    
    # Test connectivity
    print_status "Testing service connectivity..."
    
    if ! curl -sf "$client_service_addr/docs" >/dev/null 2>&1; then
        print_error "Client Service not reachable at $client_service_addr"
        print_warning "Start the client service or use --container for automatic setup"
        return 1
    fi
    print_success "Client Service is reachable"
    
    if ! curl -sf "$ai_server_addr/health" >/dev/null 2>&1; then
        print_error "AI Server not reachable at $ai_server_addr"
        print_warning "Start an AI server or use --container for automatic mock server"
        return 1
    fi
    print_success "AI Server is reachable"
    
    # Run integration tests
    export CLIENT_SERVICE_ADDR="$client_service_addr"
    export AI_SERVER_ADDR="$ai_server_addr"
    
    if run_module_tests "integration" "$verbose" "false" "false" ""; then
        print_success "Integration tests passed!"
        return 0
    else
        print_error "Integration tests failed!"
        return 1
    fi
}

# Parse command line arguments
VERBOSE="false"
COVERAGE="false"
MODULE=""
FAILFAST="false"
PATTERN=""
CONTAINER="false"
INTEGRATION="false"
SKIP_INTEGRATION="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --verbose|-v)
            VERBOSE="true"
            shift
            ;;
        --coverage)
            COVERAGE="true"
            shift
            ;;
        --module)
            MODULE="$2"
            shift 2
            ;;
        --list-modules)
            list_modules
            exit 0
            ;;
        --failfast)
            FAILFAST="true"
            shift
            ;;
        --pattern)
            PATTERN="$2"
            shift 2
            ;;
        --container)
            CONTAINER="true"
            shift
            ;;
        --integration)
            INTEGRATION="true"
            shift
            ;;
        --skip-integration)
            SKIP_INTEGRATION="true"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            print_warning "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Main execution
print_status "AI Factory Client Services Test Runner"
print_separator

# Validate conflicting options
if [[ "$CONTAINER" == "true" ]] && [[ "$INTEGRATION" == "true" ]]; then
    print_error "Cannot use --container and --integration together"
    print_warning "Use --container for full container testing or --integration for local integration tests"
    exit 1
fi

if [[ "$CONTAINER" == "true" ]] && [[ -n "$MODULE" ]]; then
    print_error "Cannot use --container with --module"
    print_warning "Container mode runs all tests (unit + integration)"
    exit 1
fi

# Container mode takes precedence
if [[ "$CONTAINER" == "true" ]]; then
    print_status "Running in container mode..."
    if run_container_tests; then
        print_success "Container tests completed successfully"
        exit 0
    else
        print_error "Container tests failed"
        exit 1
    fi
fi

# Integration mode
if [[ "$INTEGRATION" == "true" ]]; then
    print_status "Running integration tests only..."
    if run_integration_tests "$VERBOSE"; then
        print_success "Integration tests completed successfully"
        exit 0
    else
        print_error "Integration tests failed"
        exit 1
    fi
fi

# Check dependencies for local testing
check_dependencies

# Change to client directory
cd "$CLIENT_DIR"

# Run tests locally
if [[ -n "$MODULE" ]]; then
    print_status "Running tests for module: $MODULE"
    if run_module_tests "$MODULE" "$VERBOSE" "$COVERAGE" "$FAILFAST" "$PATTERN"; then
        print_success "Module tests completed successfully"
        exit 0
    else
        print_error "Module tests failed"
        exit 1
    fi
else
    if run_all_tests "$VERBOSE" "$COVERAGE" "$FAILFAST" "$PATTERN"; then
        print_success "All tests completed successfully"
        exit 0
    else
        print_error "Some tests failed"
        exit 1
    fi
fi