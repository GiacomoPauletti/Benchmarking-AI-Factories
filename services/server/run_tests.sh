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

# Docker compose file for tests (includes SSH config for live server)
COMPOSE_FLAGS="-f $PROJECT_ROOT/docker-compose.test.yml"

# Helper function to run tests in Docker
run_in_docker() {
    local description=$1
    shift
    local pytest_targets="$*"

    echo "$description"
    docker compose $COMPOSE_FLAGS run --build --rm \
        -e TESTING=true \
        server-test \
        bash -c "cd /app && pip install -q -r requirements-dev.txt && python -m pytest $pytest_targets -v --tb=short --color=yes"
}

run_gateway() {
    echo "[Gateway] Running Public API Tests..."
    echo "   Tests: services/server/src/api (The Proxy Layer)"
    run_in_docker "Testing Gateway Layer..." "tests/unit/api"
}

run_orchestrator_api() {
    echo "[Orchestrator] Running Internal API Tests..."
    echo "   Tests: services/server/src/service_orchestration/api (The Internal API)"
    run_in_docker "Testing Orchestrator API Layer..." "tests/unit/service_orchestration/api"
}

run_orchestrator_core() {
    echo "[Orchestrator] Running Core Logic Tests..."
    echo "   Tests: services/server/src/service_orchestration/core (The Business Logic)"
    run_in_docker "Testing Orchestrator Core Logic..." \
        "tests/unit/service_orchestration/core" \
        "tests/unit/service_orchestration/services"
}

run_integration() {
    echo "[Integration] Running End-to-End Tests..."
    echo "   Tests: Full system with live services"
    run_in_docker "Testing Integration..." "tests/integration"
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
        # Ensure `server` and `logs` are started with the test compose (SSH already configured)
            echo "[Integration] Ensuring server and logs containers are running..."
            docker compose $COMPOSE_FLAGS up -d --remove-orphans server logs
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
