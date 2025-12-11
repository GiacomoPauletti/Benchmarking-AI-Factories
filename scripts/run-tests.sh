#!/bin/bash
#
# Run unit tests for server and client in isolated Docker containers
# No live services required - uses mocked SSH/SLURM
#
# Usage:
#   ./scripts/run-tests.sh           # Run all tests
#   ./scripts/run-tests.sh server    # Run server tests only
#   ./scripts/run-tests.sh client    # Run client tests only
#
# To install as pre-commit hook:
#   ln -sf ../../scripts/run-tests.sh .git/hooks/pre-commit
#

set -e

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(dirname "$(readlink -f "$0")")")"
cd "$REPO_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track failures
FAILED=0

# Function to run tests
run_tests() {
    local service=$1
    local name=$2
    
    echo ""
    echo -e "${YELLOW}▶ Running $name tests...${NC}"
    
    if docker compose -f docker-compose.test.yml run --rm --no-deps \
        -e TESTING=true \
        "${service}-test" 2>&1; then
        echo -e "${GREEN}✓ $name tests passed${NC}"
    else
        echo -e "${RED}✗ $name tests failed${NC}"
        FAILED=1
    fi
}

echo "=============================================="
echo "Running Unit Tests"
echo "=============================================="

# Parse arguments
RUN_SERVER=false
RUN_CLIENT=false

if [ $# -eq 0 ]; then
    RUN_SERVER=true
    RUN_CLIENT=true
else
    for arg in "$@"; do
        case $arg in
            server) RUN_SERVER=true ;;
            client) RUN_CLIENT=true ;;
            *) echo "Unknown argument: $arg"; exit 1 ;;
        esac
    done
fi

# Build required test containers
echo ""
echo -e "${YELLOW}▶ Building test containers...${NC}"
BUILD_TARGETS=""
[ "$RUN_SERVER" = true ] && BUILD_TARGETS="$BUILD_TARGETS server-test"
[ "$RUN_CLIENT" = true ] && BUILD_TARGETS="$BUILD_TARGETS client-test"

docker compose -f docker-compose.test.yml build $BUILD_TARGETS --quiet 2>/dev/null || \
docker compose -f docker-compose.test.yml build $BUILD_TARGETS

# Run tests
[ "$RUN_SERVER" = true ] && run_tests "server" "Server"
[ "$RUN_CLIENT" = true ] && run_tests "client" "Client"

echo ""
echo "=============================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo "=============================================="
    exit 0
else
    echo -e "${RED}✗ Some tests failed.${NC}"
    echo "=============================================="
    exit 1
fi
