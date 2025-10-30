#!/bin/bash
#
# Launch script for running the Benchmarking AI Factories server locally with Docker
# This script sets up SSH tunnels to MeluXina and starts the Docker container
#

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env.local exists
if [ ! -f .env.local ]; then
    echo -e "${YELLOW}Warning: .env.local not found${NC}"
    echo "Please create .env.local from .env.local.example:"
    echo "  cp .env.local.example .env.local"
    echo "  # Edit .env.local with your credentials"
    exit 1
fi

# Load environment variables
echo -e "${GREEN}Loading environment from .env.local${NC}"
export $(cat .env.local | grep -v '^#' | xargs)

# Validate required variables
if [ -z "$SSH_USER" ]; then
    echo -e "${RED}Error: SSH_USER not set in .env.local${NC}"
    exit 1
fi

# Set defaults
SSH_HOST="${SSH_HOST:-login.lxp.lu}"
SSH_PORT="${SSH_PORT:-22}"

# Build SSH connection string
SSH_TARGET="$SSH_USER@$SSH_HOST"
SSH_CMD="ssh"
if [ "$SSH_PORT" != "22" ]; then
    SSH_CMD="$SSH_CMD -p $SSH_PORT"
fi
if [ ! -z "$SSH_KEY_PATH" ]; then
    SSH_CMD="$SSH_CMD -i $(eval echo $SSH_KEY_PATH)"
fi

# Check SSH connection
echo -e "${GREEN}Testing SSH connection to $SSH_TARGET:$SSH_PORT${NC}"
if ! $SSH_CMD -o BatchMode=yes -o ConnectTimeout=5 "$SSH_TARGET" "echo 'SSH connection successful'" 2>/dev/null; then
    echo -e "${RED}Error: Cannot connect to $SSH_HOST:$SSH_PORT${NC}"
    echo "Please ensure:"
    echo "  1. You have SSH keys set up"
    echo "  2. You can connect without password: $SSH_CMD $SSH_TARGET"
    echo "  3. SSH_HOST, SSH_PORT, and SSH_USER are correct in .env.local"
    exit 1
fi
echo -e "${GREEN}✓ SSH connection successful${NC}"

# Set remote path from config or use default
if [ -z "$REMOTE_BASE_PATH" ]; then
    REMOTE_PATH="/project/home/p200981/$SSH_USER/Benchmarking-AI-Factories/services/server"
    echo -e "${YELLOW}REMOTE_BASE_PATH not set, using default: $REMOTE_PATH${NC}"
else
    REMOTE_PATH="$REMOTE_BASE_PATH"
    echo -e "${GREEN}Using remote path: $REMOTE_PATH${NC}"
fi

# Create remote directory structure (recipes and logs)
echo -e "${GREEN}Creating remote directories on MeluXina...${NC}"
$SSH_CMD "$SSH_TARGET" "mkdir -p $REMOTE_PATH/src/recipes $REMOTE_PATH/logs"
echo -e "${GREEN}✓ Remote directories ready${NC}"

# Sync recipes to MeluXina
echo -e "${GREEN}Syncing recipes to MeluXina...${NC}"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Build SSH command for rsync
RSYNC_SSH_CMD="ssh"
if [ "$SSH_PORT" != "22" ]; then
    RSYNC_SSH_CMD="$RSYNC_SSH_CMD -p $SSH_PORT"
fi
if [ ! -z "$SSH_KEY_PATH" ]; then
    RSYNC_SSH_CMD="$RSYNC_SSH_CMD -i $(eval echo $SSH_KEY_PATH)"
fi

# Sync essential directories (recipes, configs, .sif files)
# Exclude logs, cache, and other runtime data
rsync -avz --delete \
    -e "$RSYNC_SSH_CMD" \
    --exclude='logs/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='huggingface_cache/' \
    --exclude='*.sif' \
    "$REPO_ROOT/services/server/src/recipes/" \
    "$SSH_TARGET:$REMOTE_PATH/src/recipes/" || {
        echo -e "${YELLOW}Warning: Failed to sync recipes. Jobs may use stale data.${NC}"
        echo -e "${YELLOW}You can manually sync with: rsync -avz -e \"$RSYNC_SSH_CMD\" services/server/src/recipes/ $SSH_TARGET:$REMOTE_PATH/src/recipes/${NC}"
    }

# Also sync container images if they exist
if [ -d "$REPO_ROOT/services/server/containers" ]; then
    rsync -avz \
        -e "$RSYNC_SSH_CMD" \
        "$REPO_ROOT/services/server/containers/" \
        "$SSH_TARGET:$REMOTE_PATH/containers/" || {
            echo -e "${YELLOW}Warning: Failed to sync containers${NC}"
        }
fi

echo -e "${GREEN}✓ Sync complete (or skipped if failed)${NC}"

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    
    # Stop Docker container (from root directory)
    cd "$REPO_ROOT"
    docker compose down
    echo -e "${GREEN}✓ Docker container stopped${NC}"
}

# Set up trap for cleanup on exit
trap cleanup EXIT INT TERM

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    echo "Please start Docker Desktop or Docker daemon"
    exit 1
fi

# Build and start the Docker container from root directory
echo -e "${GREEN}Building and starting Docker container...${NC}"
cd "$REPO_ROOT"
docker compose up --build server

# The container will keep running until interrupted (Ctrl+C)
# Cleanup will happen automatically via trap
