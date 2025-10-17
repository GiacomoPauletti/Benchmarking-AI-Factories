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
if [ -z "$SSH_TUNNEL_USER" ]; then
    echo -e "${RED}Error: SSH_TUNNEL_USER not set in .env.local${NC}"
    exit 1
fi

if [ -z "$SSH_TUNNEL_HOST" ]; then
    echo -e "${YELLOW}Warning: SSH_TUNNEL_HOST not set, using default: login.lxp.lu${NC}"
    SSH_TUNNEL_HOST="login.lxp.lu"
fi

# Check SSH connection
echo -e "${GREEN}Testing SSH connection to $SSH_TUNNEL_USER@$SSH_TUNNEL_HOST${NC}"
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_TUNNEL_USER@$SSH_TUNNEL_HOST" "echo 'SSH connection successful'" 2>/dev/null; then
    echo -e "${RED}Error: Cannot connect to $SSH_TUNNEL_HOST${NC}"
    echo "Please ensure:"
    echo "  1. You have SSH keys set up (~/.ssh/id_rsa or ~/.ssh/config)"
    echo "  2. You can connect without password: ssh $SSH_TUNNEL_USER@$SSH_TUNNEL_HOST"
    echo "  3. Your SSH config is correct"
    exit 1
fi
echo -e "${GREEN}✓ SSH connection successful${NC}"

# Optional: Set up SSH tunnel for SLURM REST API if needed
# Uncomment if you want to tunnel the SLURM REST API directly
# SLURM_TUNNEL_PID=""
# if [ ! -z "$SLURM_REST_URL" ] && [[ "$SLURM_REST_URL" == *"localhost"* ]]; then
#     echo -e "${GREEN}Setting up SSH tunnel for SLURM REST API${NC}"
#     ssh -f -N -L 6820:slurmrestd.meluxina.lxp.lu:6820 "$SSH_TUNNEL_USER@$SSH_TUNNEL_HOST"
#     SLURM_TUNNEL_PID=$!
#     echo -e "${GREEN}✓ SSH tunnel established (PID: $SLURM_TUNNEL_PID)${NC}"
# fi

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    # Kill SSH tunnel if we created one
    # if [ ! -z "$SLURM_TUNNEL_PID" ]; then
    #     kill $SLURM_TUNNEL_PID 2>/dev/null || true
    #     echo -e "${GREEN}✓ SSH tunnel closed${NC}"
    # fi
    
    # Stop Docker container
    docker-compose down
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

# Build and start the Docker container
echo -e "${GREEN}Building and starting Docker container...${NC}"
docker-compose up --build

# The container will keep running until interrupted (Ctrl+C)
# Cleanup will happen automatically via trap
