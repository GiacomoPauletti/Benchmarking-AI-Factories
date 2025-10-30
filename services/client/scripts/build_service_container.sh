#!/bin/bash
# =============================================================================
# Container Builder for AI Factory Client Service
# =============================================================================
# Description: Builds Apptainer container image for the Client Service
# Usage: ./build_service_container.sh [--force] [--local]
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

CONTAINER_IMAGE="client_service.sif"
DEFINITION_FILE="service_container.def"
FORCE_BUILD=false
LOCAL_MODE=false
SRC_DIR="../src"

# Slurm configuration
SLURM_ACCOUNT="p200981"
SLURM_QOS="default"
SLURM_TIME="00:10:00"

print_banner() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║           AI Factory Client Service Container Builder         ║${NC}"
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
    echo "  ./build_service_container.sh [--force] [--local]"
    echo ""
    echo -e "${CYAN}Options:${NC}"
    echo "  --force    Force rebuild even if container already exists"
    echo "  --local    Build locally on login node (default: use Slurm compute node)"
    echo ""
    echo -e "${CYAN}Description:${NC}"
    echo "  Builds an Apptainer container for the AI Factory Client Service"
    echo "  using the service_container.def definition file in ../src directory."
    echo "  By default, builds on a Slurm compute node for optimal performance."
    echo ""
    echo -e "${CYAN}Requirements:${NC}"
    echo "  - Apptainer/Singularity must be installed"
    echo "  - service_container.def must exist in ../src directory"
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
            ;;
        --local)
            LOCAL_MODE=true
            ;;
        -h|--help)
            print_banner
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown argument: $1"
            show_help
            exit 1
            ;;
    esac
    shift
done

print_banner
echo ""

print_success "Apptainer found: $(apptainer --version)"

# Check if definition file exists
if [ ! -f "$SRC_DIR/$DEFINITION_FILE" ]; then
    print_error "Definition file '$DEFINITION_FILE' not found in $SRC_DIR"
    print_info "Make sure you're running this script from the scripts directory"
    exit 1
fi

print_success "Definition file found: $SRC_DIR/$DEFINITION_FILE"

# Check if container already exists
CONTAINER_PATH="$SRC_DIR/$CONTAINER_IMAGE"
if [ -f "$CONTAINER_PATH" ] && [ "$FORCE_BUILD" = "false" ]; then
    print_warning "Container image '$CONTAINER_IMAGE' already exists in $SRC_DIR"
    print_info "Use --force to rebuild or remove the existing image"
    
    # Show container info
    echo ""
    print_info "Existing container information:"
    apptainer inspect "$CONTAINER_PATH" 2>/dev/null || echo "  Unable to inspect container"
    
    exit 0
fi

if [ -f "$CONTAINER_PATH" ] && [ "$FORCE_BUILD" = "true" ]; then
    print_warning "Removing existing container image..."
    rm -f "$CONTAINER_PATH"
fi

# Display build information
echo ""
print_info "Build Configuration:"
echo -e "  ${CYAN}Definition File:${NC} $SRC_DIR/$DEFINITION_FILE"
echo -e "  ${CYAN}Output Image:${NC} $SRC_DIR/$CONTAINER_IMAGE"
echo -e "  ${CYAN}Build Mode:${NC} $([ "$FORCE_BUILD" = "true" ] && echo "Force rebuild" || echo "New build")"
echo -e "  ${CYAN}Execution Mode:${NC} $([ "$LOCAL_MODE" = "true" ] && echo "Local (login node)" || echo "Slurm (compute node)")"
echo ""

# Function to perform the actual build
perform_build() {
    local build_location="$1"
    
    print_info "Starting container build on $build_location..."
    echo ""

    # Load required modules if not local
    if [ "$LOCAL_MODE" = "false" ]; then
        echo "Loading Apptainer modules..."
        module load env/release/2023.1
        module load Apptainer/1.2.4-GCCcore-12.3.0 || {
            print_error "Apptainer module not available on compute node"
            exit 1
        }
        echo "Apptainer version: $(apptainer --version)"
        echo ""
    fi

    # Change to src directory for build context
    cd "$SRC_DIR"

    # Build the container
    if apptainer build "$CONTAINER_IMAGE" "$DEFINITION_FILE"; then
        echo ""
        print_success "Container built successfully: $CONTAINER_IMAGE"
        
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
        echo -e "  ${CYAN}cd ../src && ./start_client_service.sh <server_address> <time> --container${NC}"
        
    else
        echo ""
        print_error "Container build failed"
        print_info "Check the error messages above for details"
        exit 1
    fi
}

# Execute build based on mode
if [ "$LOCAL_MODE" = "true" ]; then
    print_warning "Building locally on login node"
    print_info "Note: This may be slower and could impact other users"
    echo ""
    
    perform_build "login node"
    
else
    print_info "Requesting Slurm compute node for container build..."
    echo ""
    
salloc -A $SLURM_ACCOUNT -t $SLURM_TIME -p cpu -q $SLURM_QOS -N 1 --ntasks-per-node=1 --cpus-per-task=4 << 'EOF'
    echo "========================================="
    echo "Container Build Starting on Compute Node"
    echo "========================================="
    echo "Node: $(hostname)"
    echo "Date: $(date)"
    echo "Working Directory: $(pwd)"
    echo "========================================="
    echo ""
    
    # Source this script's functions and variables
    CONTAINER_IMAGE="client_service.sif"
    DEFINITION_FILE="service_container.def"
    SRC_DIR="../src"
    LOCAL_MODE=false
    
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
    print_info "Starting container build on compute node..."
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

    # Change to src directory for build context
    cd "$SRC_DIR"

    # Build the container
    if apptainer build "$CONTAINER_IMAGE" "$DEFINITION_FILE"; then
        echo ""
        print_success "Container built successfully: $CONTAINER_IMAGE"
        
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
        echo -e "  ${CYAN}cd ../src && ./start_client_service.sh <server_address> <time> --container${NC}"
        
    else
        echo ""
        print_error "Container build failed"
        print_info "Check the error messages above for details"
        exit 1
    fi
EOF
fi