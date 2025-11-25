#!/bin/bash
set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Go up two levels to project root (Benchmarking-AI-Factories)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "========================================================"
echo "AI Factory Client Tests"
echo "========================================================"
echo "Project Root: $PROJECT_ROOT"
echo ""

MODE=$1

# Docker compose file for tests (includes SSH config for live client)
COMPOSE_FLAGS="-f $PROJECT_ROOT/docker-compose.test.yml"

# Helper function to run tests in Docker
run_in_docker() {
    local description=$1
    shift
    local pytest_targets="$*"

    echo "$description"
    docker compose $COMPOSE_FLAGS run --rm \
        -e TESTING=true \
        client-test \
        bash -c "cd /app && pip install -q -r requirements-dev.txt && python -m pytest $pytest_targets -v --tb=short --color=yes"
}

run_unit() {
    echo "[Unit] Running Unit Tests..."
    echo "   Tests: services/client/tests/unit (API, Client Manager, Deployment)"
    run_in_docker "Testing Unit Layer..." "tests/unit"
}

run_integration() {
    echo "[Integration] Running End-to-End Tests..."
    echo "   Tests: Full system with live services (server, client, SLURM)"
    echo "   NOTE: Requires server and client services to be running"
    run_in_docker "Testing Integration..." "tests/integration -m integration"
}

run_all() {
    echo "Running ALL Tests (Unit + Integration)..."
    run_unit
    echo ""
    run_integration
}

case "$MODE" in
    "unit")
        run_unit
        ;;
    "integration")
        # Ensure `server`, `client`, and `logs` are started with the test compose
        echo "[Integration] Ensuring server, client, and logs containers are running..."
        docker compose $COMPOSE_FLAGS up -d --remove-orphans server client logs
        run_integration
        ;;
    "all")
        # Ensure services are running for integration tests
        echo "[All] Ensuring server, client, and logs containers are running..."
        docker compose $COMPOSE_FLAGS up -d --remove-orphans server client logs
        run_all
        ;;
    "help")
        echo "Usage: ./run_tests.sh [MODE]"
        echo ""
        echo "Modes:"
        echo "  unit          - Run unit tests (API, Client Manager, Deployment)"
        echo "  integration   - Run integration tests (requires live services)"
        echo "  all           - Run all tests (unit + integration)"
        echo "  (no argument) - Run unit tests only"
        echo ""
        exit 0
        ;;
    *)
        run_unit
        ;;
esac

echo ""
echo "Done."
