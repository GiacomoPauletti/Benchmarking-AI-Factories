#!/bin/bash
set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Go up two levels to project root (Benchmarking-AI-Factories)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "========================================================"
echo "AI Factory Server Tests"
echo "========================================================"
echo "Project Root: $PROJECT_ROOT"
echo ""

MODE=$1

# Helper function to run tests in Docker
run_in_docker() {
    local test_file=$1
    local description=$2
    
    echo "$description"
    docker compose -f "$PROJECT_ROOT/docker-compose.test.yml" run --rm \
        -e TESTING=true \
        server-test \
        bash -c "cd /app && pip install -q -r requirements-dev.txt && python -m pytest $test_file -v --tb=short --color=yes"
}

run_gateway() {
    echo "[Gateway] Running Public API Tests..."
    echo "   Tests: services/server/src/api (The Proxy Layer)"
    run_in_docker "tests/unit/test_gateway_api.py" "Testing Gateway Layer..."
}

run_orchestrator_api() {
    echo "[Orchestrator] Running Internal API Tests..."
    echo "   Tests: services/server/src/service_orchestration/api (The Internal API)"
    run_in_docker "tests/unit/test_orchestrator_api.py" "Testing Orchestrator API Layer..."
}

run_orchestrator_core() {
    echo "[Orchestrator] Running Core Logic Tests..."
    echo "   Tests: services/server/src/service_orchestration/core (The Business Logic)"
    run_in_docker "tests/unit/test_orchestrator_core.py" "Testing Orchestrator Core Logic..."
}

run_integration() {
    echo "[Integration] Running End-to-End Tests..."
    echo "   Tests: Full system with live services"
    run_in_docker "tests/integration/test_integration.py" "Testing Integration..."
}

run_all_unit() {
    echo "Running ALL Unit Tests (Gateway + Orchestrator API + Core)..."
    run_gateway
    echo ""
    run_orchestrator_api
    echo ""
    run_orchestrator_core
}

case "$MODE" in
    "gateway")
        run_gateway
        ;;
    "orch-api")
        run_orchestrator_api
        ;;
    "orch-core")
        run_orchestrator_core
        ;;
    "integration")
        run_integration
        ;;
    "help")
        echo "Usage: ./run_tests.sh [MODE]"
        echo ""
        echo "Modes:"
        echo "  gateway       - Run Gateway (public API) tests"
        echo "  orch-api      - Run Orchestrator API (internal) tests"
        echo "  orch-core     - Run Orchestrator Core logic tests"
        echo "  integration   - Run integration tests (requires live services)"
        echo "  (no argument) - Run all unit tests"
        echo ""
        exit 0
        ;;
    *)
        run_all_unit
        ;;
esac

echo ""
echo "Done."
