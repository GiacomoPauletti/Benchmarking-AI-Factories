#!/bin/bash

# AI Factory Container Orchestration Management Script
# Provides K8s-like functionality for Meluxina HPC environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTAINER_DIR="$PROJECT_ROOT/containers"
DEPLOYMENT_DIR="$PROJECT_ROOT/deployments"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if we're on Meluxina
check_environment() {
    if [[ ! -f "/etc/slurm/slurm.conf" ]] && [[ ! -command -v squeue >/dev/null 2>&1 ]]; then
        log_warning "SLURM not detected. This script is optimized for Meluxina HPC."
        log_warning "Some features may not work in non-HPC environments."
    fi
    
    if ! command -v apptainer >/dev/null 2>&1 && ! module avail Apptainer >/dev/null 2>&1; then
        log_error "Apptainer not found. Please load the Apptainer module:"
        log_error "  module load Apptainer/1.2.4-GCCcore-12.3.0"
        exit 1
    fi
}

# Function to build container images
build_containers() {
    log_info "Building container images..."
    
    # Load Apptainer module if available
    if command -v module >/dev/null 2>&1; then
        module load Apptainer/1.2.4-GCCcore-12.3.0 2>/dev/null || true
    fi
    
    cd "$CONTAINER_DIR"
    
    # Build each service container
    for def_file in *.def; do
        if [[ -f "$def_file" ]]; then
            service_name=$(basename "$def_file" .def)
            sif_file="${service_name}.sif"
            
            log_info "Building $service_name container..."
            
            if apptainer build "$sif_file" "$def_file"; then
                log_success "Built $sif_file"
            else
                log_error "Failed to build $sif_file"
                exit 1
            fi
        fi
    done
    
    log_success "All containers built successfully!"
}

# Function to deploy microservice stack
deploy_stack() {
    local deployment_file="$1"
    
    if [[ -z "$deployment_file" ]]; then
        deployment_file="$DEPLOYMENT_DIR/microservices.yaml"
    fi
    
    if [[ ! -f "$deployment_file" ]]; then
        log_error "Deployment file not found: $deployment_file"
        exit 1
    fi
    
    log_info "Deploying microservice stack from $deployment_file"
    
    # Start the orchestration service first
    python3 -c "
import sys
import asyncio
sys.path.append('$PROJECT_ROOT/services/shared')
from container_orchestrator import orchestrator

async def deploy():
    deployment = orchestrator.create_deployment_from_yaml('$deployment_file')
    job_id = await orchestrator.deploy(deployment)
    print(f'✅ Deployment submitted with job ID: {job_id}')

asyncio.run(deploy())
"
}

# Function to list deployments
list_deployments() {
    log_info "Listing active deployments..."
    
    python3 -c "
import sys
import asyncio
sys.path.append('$PROJECT_ROOT/services/shared')
from container_orchestrator import orchestrator

async def list_deps():
    deployments = await orchestrator.list_deployments()
    if not deployments:
        print('No active deployments found.')
        return
    
    print(f'{"Name":<20} {"Status":<15} {"Job ID":<10}')
    print('-' * 50)
    for dep in deployments:
        print(f'{dep["name"]:<20} {dep["status"]:<15} {dep.get("job_id", "N/A"):<10}')

asyncio.run(list_deps())
"
}

# Function to stop deployment
stop_deployment() {
    local deployment_name="$1"
    
    if [[ -z "$deployment_name" ]]; then
        log_error "Please specify deployment name to stop"
        exit 1
    fi
    
    log_info "Stopping deployment: $deployment_name"
    
    python3 -c "
import sys
import asyncio
sys.path.append('$PROJECT_ROOT/services/shared')
from container_orchestrator import orchestrator

async def stop():
    await orchestrator.stop_deployment('$deployment_name')
    print('✅ Deployment stopped')

asyncio.run(stop())
"
}

# Function to scale deployment
scale_deployment() {
    local deployment_name="$1"
    local replicas="$2"
    
    if [[ -z "$deployment_name" ]] || [[ -z "$replicas" ]]; then
        log_error "Usage: scale <deployment_name> <replicas>"
        exit 1
    fi
    
    log_info "Scaling deployment $deployment_name to $replicas replicas"
    
    python3 -c "
import sys
import asyncio
sys.path.append('$PROJECT_ROOT/services/shared')
from container_orchestrator import orchestrator

async def scale():
    await orchestrator.scale_deployment('$deployment_name', $replicas)
    print('✅ Deployment scaled')

asyncio.run(scale())
"
}

# Function to get deployment logs
get_logs() {
    local deployment_name="$1"
    
    if [[ -z "$deployment_name" ]]; then
        log_error "Please specify deployment name"
        exit 1
    fi
    
    # Find the job ID for this deployment
    job_id=$(squeue --format="%i %j" --noheader | grep "$deployment_name" | awk '{print $1}' | head -1)
    
    if [[ -z "$job_id" ]]; then
        log_error "No active job found for deployment: $deployment_name"
        exit 1
    fi
    
    log_info "Showing logs for deployment $deployment_name (job $job_id)"
    
    # Show SLURM output files
    output_file="/tmp/ai_factory_orchestrator/${deployment_name}_${job_id}.out"
    error_file="/tmp/ai_factory_orchestrator/${deployment_name}_${job_id}.err"
    
    echo "=== STDOUT ==="
    if [[ -f "$output_file" ]]; then
        tail -f "$output_file"
    else
        echo "Output file not found: $output_file"
    fi
    
    echo "=== STDERR ==="
    if [[ -f "$error_file" ]]; then
        tail -f "$error_file"
    else
        echo "Error file not found: $error_file"
    fi
}

# Function to show help
show_help() {
    cat << EOF
🚀 AI Factory Container Orchestration Manager

Provides Kubernetes-like container orchestration for Meluxina HPC environment.

USAGE:
    $0 <command> [arguments]

COMMANDS:
    build                           Build all container images
    deploy [deployment.yaml]        Deploy microservice stack
    list                           List active deployments
    stop <deployment_name>         Stop a deployment
    scale <deployment_name> <N>    Scale deployment to N replicas
    logs <deployment_name>         Show deployment logs
    help                          Show this help message

EXAMPLES:
    # Build all containers
    $0 build
    
    # Deploy the default microservices stack
    $0 deploy
    
    # Deploy custom configuration
    $0 deploy /path/to/my-stack.yaml
    
    # List all running deployments
    $0 list
    
    # Scale a deployment
    $0 scale ai-factory-microservices 3
    
    # Stop a deployment
    $0 stop ai-factory-microservices
    
    # View logs
    $0 logs ai-factory-microservices

FEATURES:
    ✅ K8s-style YAML deployments
    ✅ Container orchestration via SLURM
    ✅ Service discovery and networking
    ✅ Scaling and lifecycle management
    ✅ Log aggregation
    ✅ Health checking

For more information, see the documentation at:
https://github.com/GiacomoPauletti/Benchmarking-AI-Factories
EOF
}

# Main command dispatcher
main() {
    case "${1:-help}" in
        "build")
            check_environment
            build_containers
            ;;
        "deploy")
            check_environment
            deploy_stack "$2"
            ;;
        "list")
            check_environment
            list_deployments
            ;;
        "stop")
            check_environment
            stop_deployment "$2"
            ;;
        "scale")
            check_environment
            scale_deployment "$2" "$3"
            ;;
        "logs")
            check_environment
            get_logs "$2"
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            log_error "Unknown command: $1"
            echo
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"