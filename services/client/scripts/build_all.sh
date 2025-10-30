#!/bin/bash
# =============================================================================
# AI Factory Container Build All Script
# =============================================================================
# Description: Builds both client service and client containers
# Usage: ./build_all.sh [--force] [--local] [--help]
# Author: AI Assistant
# =============================================================================

set -e

# Colors for output
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
CYAN="\033[0;36m"
WHITE="\033[1;37m"
NC="\033[0m" # No Color

# Configuration
FORCE_BUILD=false
LOCAL_MODE=false

print_banner() {
    echo -e "${WHITE}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${WHITE}║              AI Factory Container Build All Script                 ║${NC}"
    echo -e "${WHITE}╚════════════════════════════════════════════════════════════════════╝${NC}"
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

print_step() {
    echo -e "${CYAN}🔨 $1${NC}"
}

show_help() {
    echo -e "${CYAN}Usage:${NC}"
    echo "  ./build_all.sh [--force] [--local] [--help]"
    echo ""
    echo -e "${CYAN}Options:${NC}"
    echo "  --force    Force rebuild even if containers already exist"
    echo "  --local    Build locally on login node (default: use Slurm compute nodes)"
    echo "  --help     Show this help message"
    echo ""
    echo -e "${CYAN}Description:${NC}"
    echo "  Builds both AI Factory containers in sequence:"
    echo "  1. Client Service Container (client_service.sif)"
    echo "  2. Client Container (client_container.sif)"
    echo ""
    echo "  By default, builds are performed on Slurm compute nodes for optimal"
    echo "  performance and to avoid impacting login node resources."
    echo ""
    echo -e "${CYAN}Individual Build Scripts:${NC}"
    echo "  - ./build_service_container.sh  - Build only client service container"
    echo "  - ./build_client_container.sh   - Build only client container"
    echo ""
    echo -e "${CYAN}Output:${NC}"
    echo "  Creates:"
    echo "    ../src/client_service.sif"
    echo "    ../src/client/client_container.sif"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  ./build_all.sh                  # Build both containers on compute nodes"
    echo "  ./build_all.sh --local          # Build both containers locally"
    echo "  ./build_all.sh --force          # Force rebuild both containers"
    echo "  ./build_all.sh --force --local  # Force rebuild locally"
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

# Display configuration
print_info "Build Configuration:"
echo -e "  ${CYAN}Force Rebuild:${NC} $([ "$FORCE_BUILD" = "true" ] && echo "Yes" || echo "No")"
echo -e "  ${CYAN}Execution Mode:${NC} $([ "$LOCAL_MODE" = "true" ] && echo "Local (login node)" || echo "Slurm (compute nodes)")"
echo ""

if [ "$LOCAL_MODE" = "true" ]; then
    print_warning "Building locally on login node"
    print_info "This may be slower and could impact other users"
else
    print_info "Building on Slurm compute nodes for optimal performance"
fi
echo ""

# Build flags
BUILD_FLAGS=""
[ "$FORCE_BUILD" = "true" ] && BUILD_FLAGS="$BUILD_FLAGS --force"
[ "$LOCAL_MODE" = "true" ] && BUILD_FLAGS="$BUILD_FLAGS --local"

# Build counters
TOTAL_BUILDS=2
SUCCESSFUL_BUILDS=0
FAILED_BUILDS=0

echo "========================================="
echo "Starting Container Build Process"
echo "========================================="
echo ""

# Step 1: Build Client Service Container
print_step "Step 1/2: Building Client Service Container"
echo ""

if ./build_service_container.sh $BUILD_FLAGS; then
    print_success "Client Service Container build completed successfully"
    SUCCESSFUL_BUILDS=$((SUCCESSFUL_BUILDS + 1))
else
    print_error "Client Service Container build failed"
    FAILED_BUILDS=$((FAILED_BUILDS + 1))
fi

echo ""
echo "========================================="
echo ""

# Step 2: Build Client Container
print_step "Step 2/2: Building Client Container"
echo ""

if ./build_client_container.sh $BUILD_FLAGS; then
    print_success "Client Container build completed successfully"
    SUCCESSFUL_BUILDS=$((SUCCESSFUL_BUILDS + 1))
else
    print_error "Client Container build failed"
    FAILED_BUILDS=$((FAILED_BUILDS + 1))
fi

echo ""
echo "========================================="
echo "Build Process Summary"
echo "========================================="

print_info "Build Results:"
echo -e "  ${GREEN}✅ Successful builds: $SUCCESSFUL_BUILDS/$TOTAL_BUILDS${NC}"
if [ $FAILED_BUILDS -gt 0 ]; then
    echo -e "  ${RED}❌ Failed builds: $FAILED_BUILDS/$TOTAL_BUILDS${NC}"
fi
echo ""

if [ $SUCCESSFUL_BUILDS -eq $TOTAL_BUILDS ]; then
    print_success "🎉 All containers built successfully!"
    echo ""
    print_info "Container Locations:"
    echo -e "  ${CYAN}Client Service:${NC} ../src/client_service.sif"
    echo -e "  ${CYAN}Client:${NC}         ../src/client/client_container.sif"
    echo ""
    print_info "You can now use the containers with:"
    echo -e "  ${CYAN}./start_client_service.sh <server_addr> <time> --container${NC}"
    exit 0
elif [ $SUCCESSFUL_BUILDS -gt 0 ]; then
    print_warning "⚠️  Partial success: $SUCCESSFUL_BUILDS/$TOTAL_BUILDS containers built"
    print_info "Check the error messages above for failed builds"
    exit 1
else
    print_error "💥 All container builds failed"
    print_info "Check the error messages above for details"
    exit 1
fi