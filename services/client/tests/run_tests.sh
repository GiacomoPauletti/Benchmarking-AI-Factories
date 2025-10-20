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

EXAMPLES:
    $0                              # Run all unit tests locally
    $0 --verbose                    # Run all tests with verbose output
    $0 --coverage                   # Run tests with coverage report
    $0 --container                  # Run all tests in container (unit + integration)
    $0 --integration                # Run integration tests only
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
    
    local test_path=""
    local module_name=""
    
    case $module in
        "client")
            test_path="$TESTS_DIR/client"
            module_name="Client Core Components"
            ;;
        "client.api")
            test_path="$TESTS_DIR/client/api"
            module_name="Client API Components"
            ;;
        "client_service")
            test_path="$TESTS_DIR/client_service"
            module_name="Client Service Components"
            ;;
        "client_service.api")
            test_path="$TESTS_DIR/client_service/api"
            module_name="Client Service API Components"
            ;;
        "client_service.client_manager")
            test_path="$TESTS_DIR/client_service/client_manager"
            module_name="Client Manager Components"
            ;;
        "client_service.deployment")
            test_path="$TESTS_DIR/client_service/deployment"
            module_name="Deployment Components"
            ;;
        "main")
            test_path="$TESTS_DIR/test_main.py"
            module_name="Main Application"
            ;;
        "integration")
            test_path="$TESTS_DIR/integration"
            module_name="Integration Tests"
            ;;
        *)
            print_error "Unknown module: $module"
            print_warning "Use --list-modules to see available modules"
            exit 1
            ;;
    esac
    
    if [[ ! -e "$test_path" ]]; then
        print_error "Test path not found: $test_path"
        return 1
    fi
    
    # Special handling for integration tests
    if [[ "$module" == "integration" ]]; then
        print_warning "Integration tests require live services"
        print_status "Make sure CLIENT_SERVICE_ADDR and AI_SERVER_ADDR are set"
        print_status "Or use --container to run with automatic service setup"
    fi
    
    print_status "Running tests for: $module_name"
    
    # Build Python command using pytest for better compatibility
    local python_cmd="python3 -m pytest \"$test_path\""
    
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
    print_status "Running tests in Apptainer container..."
    print_warning "This will build a container and request Slurm resources"
    
    # Check if we have the container definition
    local container_def="$TESTS_DIR/test-container.def"
    if [[ ! -f "$container_def" ]]; then
        print_error "Container definition not found: $container_def"
        print_error "Make sure test-container.def exists in $TESTS_DIR"
        return 1
    fi
    
    print_status "Starting container-based testing..."
    print_status "This will:"
    print_status "  1. Build test container with Apptainer"
    print_status "  2. Request Slurm compute resources"
    print_status "  3. Run unit tests in container"
    print_status "  4. Start client service and mock AI server"
    print_status "  5. Run integration tests"
    print_status "  6. Generate coverage reports"
    print_status "  7. Clean up services"
    
    # Run container tests using salloc
    print_status "Requesting Slurm compute resources..."
    
    # Find the project root (Benchmarking-AI-Factories directory)
    # SCRIPT_DIR is /path/to/Benchmarking-AI-Factories/services/client/tests
    # We need /path/to/Benchmarking-AI-Factories
    PROJECT_ROOT=$(dirname $(dirname $(dirname "$SCRIPT_DIR")))
    print_status "Project root: $PROJECT_ROOT"
    print_status "Client directory: $CLIENT_DIR"
    
    # Change to client directory for container operations
    cd "$CLIENT_DIR"
    
    if salloc -A p200981 -t 00:30:00 -p cpu -q short -N 1 --ntasks-per-node=1 --mem=8G << EOF
        
        # Load required modules
        module load env/release/2023.1
        module load Apptainer/1.2.4-GCCcore-12.3.0 || { 
            echo "ERROR: Apptainer module not available"; 
            exit 1; 
        }
        
        # Check for existing container first
        echo "Checking for existing container..."
        cd tests
        
        if [ -f test-container.sif ]; then
            echo "Using existing container: test-container.sif"
            echo "Container size: \$(ls -lh test-container.sif | awk '{print \$5}')"
        else
            echo "Building new client test container..."
            # Try to build container (first without fakeroot, then with if needed)
            if apptainer build --force test-container.sif test-container.def 2>/dev/null; then
                echo "Container built successfully (without fakeroot)"
            elif apptainer build --fakeroot --force test-container.sif test-container.def; then
                echo "Container built successfully (with fakeroot)"
            else
                echo "Container build failed with both methods"
                echo "Check network connectivity and Apptainer configuration"
                exit 1
            fi
        fi
        
        # Navigate back to client directory
        cd ..
        
        # Get SLURM JWT token
        echo "Getting SLURM JWT token..."
        export SLURM_JWT=\$(scontrol token | grep SLURM_JWT | cut -d= -f2)
        echo "Token obtained: \${SLURM_JWT:0:20}..."
        
        # Change to project root for proper binding
        cd "$PROJECT_ROOT"
        echo "Running container from: \$(pwd)"
        echo "Binding \$(pwd) to /app"
        
        # Run the container with proper bindings (project root -> /app)
        if apptainer run \
            --env SLURM_JWT="\${SLURM_JWT}" \
            --env CLIENT_SERVICE_HOST="localhost" \
            --env CLIENT_SERVICE_PORT="8001" \
            --env AI_SERVER_HOST="localhost" \
            --env AI_SERVER_PORT="8000" \
            --bind "\$(pwd):/app" \
            services/client/tests/test-container.sif; then
            echo "All client tests passed!"
        else
            echo "Client tests failed!"
            exit 1
        fi
        
EOF
    then
        print_success "Container tests completed successfully!"
        print_status "Check test logs:"
        print_status "  - Unit tests: $TESTS_DIR/unit-test.log"
        print_status "  - Integration tests: $TESTS_DIR/integration-test.log"
        print_status "  - Coverage: $TESTS_DIR/htmlcov/index.html"
        return 0
    else
        print_error "Container tests failed!"
        print_status "Check logs for details:"
        print_status "  - Unit tests: $TESTS_DIR/unit-test.log"
        print_status "  - Integration tests: $TESTS_DIR/integration-test.log"
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