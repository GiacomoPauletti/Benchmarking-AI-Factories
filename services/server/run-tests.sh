#!/bin/bash
# Run tests in isolated Docker test environment
# This uses docker-compose.test.yml for a clean test environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Running Server Tests (Isolated Test Container)${NC}"
echo "================================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    echo "Please start Docker Desktop or Docker daemon"
    exit 1
fi

# Navigate to project root
cd "$PROJECT_ROOT"

# Cleanup function to remove test container
cleanup() {
    echo ""
    echo -e "${YELLOW}Cleaning up test container...${NC}"
    docker compose -f docker-compose.test.yml down -v 2>/dev/null || true
}

# Set trap to cleanup on exit
trap cleanup EXIT INT TERM

# Clean up any existing test containers
echo -e "${YELLOW}Cleaning up old test containers...${NC}"
docker compose -f docker-compose.test.yml down -v 2>/dev/null || true

# Build and run tests in isolated container
echo ""
echo -e "${GREEN}Building test container...${NC}"
docker compose -f docker-compose.test.yml build

echo ""
echo -e "${GREEN}Running tests...${NC}"
echo "=================="

# Run tests and capture exit code
if docker compose -f docker-compose.test.yml up --abort-on-container-exit --exit-code-from server-test; then
    TEST_STATUS=0
else
    TEST_STATUS=$?
fi

# Cleanup happens automatically via trap

if [ $TEST_STATUS -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "  • Commit your changes: git commit -am 'Your message'"
    echo "  • Push to your branch: git push"
    echo "  • Create a pull request on GitHub"
    exit 0
else
    echo ""
    echo -e "${RED}✗ Tests failed!${NC}"
    echo "Check the output above for details."
    exit 1
fi