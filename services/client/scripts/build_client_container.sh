#!/bin/bash
# =============================================================================
# AI Factory Client Container Builder
# =============================================================================
# Description: Builds an Apptainer container for the AI Factory Client
# Usage: ./build_client_container.sh [--force] [--local]
# Author: AI Assistant
# =============================================================================

set -e

# Colors for output
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
CYAN="\033[0;36m"
NC="\033[0m" # No Color

# Configuration
CONTAINER_IMAGE="client_container.sif"
DEFINITION_FILE="client_container.def"
CLIENT_DIR="../src/client"
FORCE_BUILD=false
LOCAL_MODE=false

# Slurm configuration
SLURM_ACCOUNT="p200981"
SLURM_QOS="default"
SLURM_TIME="00:10:00"

print_banner() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║             AI Factory Client Container Builder              ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

show_help() {
    echo -e "${CYAN}Usage:${NC}"
    echo "  ./build_client_container.sh [--force] [--local]"
    echo ""
    echo -e "${CYAN}Options:${NC}"
    echo "  --force    Force rebuild even if container already exists"
    echo "  --local    Build locally on login node (default: use Slurm compute node)"
    echo ""
    echo -e "${CYAN}Description:${NC}"
    echo "  Builds an Apptainer container for the AI Factory Client"
    echo "  using the client_container.def definition file in ../src/client directory."
    echo "  By default, builds on a Slurm compute node for optimal performance."
    echo ""
    echo -e "${CYAN}Requirements:${NC}"
    echo "  - Apptainer/Singularity must be installed"
    echo "  - client_container.def must exist in ../src/client directory"
    echo "  - Internet connection for downloading base image"
    echo ""
    echo -e "${CYAN}Slurm Configuration:${NC}"
    echo "  Account: $SLURM_ACCOUNT"
    echo "  QoS: $SLURM_QOS"
    echo "  Time limit: $SLURM_TIME"
    echo ""
    echo -e "${CYAN}Output:${NC}"
    echo "  Creates: $CONTAINER_IMAGE"
}

# Parse arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --force)
            FORCE_BUILD=true
            shift
            ;;
        --local)
            LOCAL_MODE=true
            shift
            ;;
        --help|-h)
            print_banner
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown argument: $1"
            print_info "Use --help for usage information"
            exit 1
            ;;
    esac
done

print_banner
echo ""


print_success "Definition file found: $CLIENT_DIR/$DEFINITION_FILE"

# Check if container already exists
if [ -f "$CLIENT_DIR/$CONTAINER_IMAGE" ] && [ "$FORCE_BUILD" = "false" ]; then
    print_warning "Container '$CONTAINER_IMAGE' already exists in $CLIENT_DIR"
    print_info "Use --force to rebuild or remove the existing container"
    echo ""
    print_info "Existing container information:"
    apptainer inspect "$CLIENT_DIR/$CONTAINER_IMAGE" 2>/dev/null || echo "  Unable to inspect container"
    exit 0
fi

# Remove existing container if force build
if [ -f "$CLIENT_DIR/$CONTAINER_IMAGE" ] && [ "$FORCE_BUILD" = "true" ]; then
    print_info "Removing existing container for rebuild..."
    rm -f "$CLIENT_DIR/$CONTAINER_IMAGE"
fi

# Display build information
echo ""
print_info "Build Configuration:"
echo -e "  ${CYAN}Definition File:${NC} $CLIENT_DIR/$DEFINITION_FILE"
echo -e "  ${CYAN}Output Image:${NC} $CLIENT_DIR/$CONTAINER_IMAGE"
echo -e "  ${CYAN}Build Mode:${NC} $([ "$FORCE_BUILD" = "true" ] && echo "Force rebuild" || echo "New build")"
echo -e "  ${CYAN}Execution Mode:${NC} $([ "$LOCAL_MODE" = "true" ] && echo "Local (login node)" || echo "Slurm (compute node)")"
echo ""

# Execute build based on mode
if [ "$LOCAL_MODE" = "true" ]; then
    print_warning "Building locally on login node"
    print_info "Note: This may be slower and could impact other users"
    echo ""
    
    # Check if running on compute node (module system available)
    if command -v module >/dev/null 2>&1; then
        print_info "Loading Apptainer modules..."
        module load env/release/2023.1
        module load Apptainer/1.2.4-GCCcore-12.3.0 || {
            print_error "Apptainer module not available"
            exit 1
        }
    else
        print_warning "Module system not available - assuming Apptainer is in PATH"
    fi

    # Check if Apptainer is available
    if ! command -v apptainer >/dev/null 2>&1; then
        print_error "Apptainer not found in PATH"
        print_info "Please ensure Apptainer is installed and available"
        print_info "On Meluxina compute nodes, run: module load Apptainer/1.2.4-GCCcore-12.3.0"
        exit 1
    fi

    print_success "Apptainer found: $(apptainer --version)"
    
    print_info "Starting container build on login node..."
    echo ""

    # Change to client directory for build context
    cd "$CLIENT_DIR"

    # Build the container
    if apptainer build "$CONTAINER_IMAGE" "$DEFINITION_FILE"; then
        echo ""
        print_success "Container built successfully: $CLIENT_DIR/$CONTAINER_IMAGE"
        
        # Show final container information
        echo ""
        print_info "Container information:"
        apptainer inspect "$CONTAINER_IMAGE" 2>/dev/null || echo "  Unable to inspect container"
        
        # Show size
        if [ -f "$CONTAINER_IMAGE" ]; then
            SIZE=$(du -h "$CONTAINER_IMAGE" | cut -f1)
            echo -e "  ${CYAN}Size:${NC} $SIZE"
        fi
        
        echo ""
        print_info "You can now use the container with:"
        echo -e "  ${CYAN}apptainer run $CLIENT_DIR/$CONTAINER_IMAGE <num_clients> <server_addr> <client_service_addr> <benchmark_id>${NC}"
        
    else
        echo ""
        print_error "Container build failed"
        print_info "Check the error messages above for details"
        exit 1
    fi
    
else
    print_info "Requesting Slurm compute node for container build..."
    echo ""
    
salloc -A $SLURM_ACCOUNT -t $SLURM_TIME -p cpu -q $SLURM_QOS -N 1 --ntasks-per-node=1 --cpus-per-task=4 << 'EOF'
    echo "========================================="
    echo "Client Container Build on Compute Node"
    echo "========================================="
    echo "Node: $(hostname)"
    echo "Date: $(date)"
    echo "Working Directory: $(pwd)"
    echo "========================================="
    echo ""
    
    # Source this script's functions and variables
    CONTAINER_IMAGE="client_container.sif"
    DEFINITION_FILE="client_container.def"
    CLIENT_DIR="../src/client"
    
    # Colors for output
    RED="\033[0;31m"
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    BLUE="\033[0;34m"
    CYAN="\033[0;36m"
    NC="\033[0m"
    
    print_success() {
        echo -e "${GREEN}✅ $1${NC}"
    }
    
    print_error() {
        echo -e "${RED}❌ $1${NC}"
    }
    
    print_info() {
        echo -e "${BLUE}ℹ️  $1${NC}"
    }
    
    print_warning() {
        echo -e "${YELLOW}⚠️  $1${NC}"
    }
    
    # Perform the build
    print_info "Starting client container build on compute node..."
    echo ""

    # Load required modules
    echo "Loading Apptainer modules..."
    module load env/release/2023.1
    module load Apptainer/1.2.4-GCCcore-12.3.0 || {
        print_error "Apptainer module not available on compute node"
        exit 1
    }
    echo "Apptainer version: $(apptainer --version)"
    echo ""

    # Change to client directory for build context
    cd "$CLIENT_DIR"

    # Build the container
    if apptainer build "$CONTAINER_IMAGE" "$DEFINITION_FILE"; then
        echo ""
        print_success "Container built successfully: $CLIENT_DIR/$CONTAINER_IMAGE"
        
        # Show final container information
        echo ""
        print_info "Container information:"
        apptainer inspect "$CONTAINER_IMAGE" 2>/dev/null || echo "  Unable to inspect container"
        
        # Show size
        if [ -f "$CONTAINER_IMAGE" ]; then
            SIZE=$(du -h "$CONTAINER_IMAGE" | cut -f1)
            echo -e "  ${CYAN}Size:${NC} $SIZE"
        fi
        
        echo ""
        print_info "You can now use the container with:"
        echo -e "  ${CYAN}apptainer run $CLIENT_DIR/$CONTAINER_IMAGE <num_clients> <server_addr> <client_service_addr> <benchmark_id>${NC}"
        
    else
        echo ""
        print_error "Container build failed"
        print_info "Check the error messages above for details"
        exit 1
    fi
EOF
fi