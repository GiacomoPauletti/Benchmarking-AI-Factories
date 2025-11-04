#!/bin/bash -l
# =============================================================================
# Client Service Launcher with Slurm Allocation
# =============================================================================
# Description: Launches the AI Factory Client Service on a Slurm compute node
# Usage: ./start_client_service.sh <server_address> <time_allocation> [slurm_config_file] [--local] [--container]
# Author: AI Assistant
# =============================================================================

set -e

# Default values
DEFAULT_SLURM_CONFIG="example_slurm_config"
SCRIPT_DIR="../src"
LOCAL_MODE=false
CONTAINER_MODE=false
USE_CURRENT_NODE=false
CONTAINER_IMAGE="client_service.sif"

# Slurm configuration
SLURM_ACCOUNT="p200981"
SLURM_QOS="default"
SLURM_NODES=1
SLURM_CPUS=2

# Colors for output
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
CYAN="\033[0;36m"
NC="\033[0m" # No Color

print_banner() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║              AI Factory Client Service Launcher              ║${NC}"
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
    echo "  ./start_client_service.sh <server_address> <time_allocation> [slurm_config_file] [OPTIONS]"
    echo ""
    echo -e "${CYAN}Parameters:${NC}"
    echo "  server_address     - Address of the server service (e.g., http://server-ip:8000)"
    echo "  time_allocation    - Slurm time allocation (e.g., 30min, 2h, 1:30:00)"
    echo "  slurm_config_file  - Optional: Path to Slurm configuration file"
    echo "                      (default: $DEFAULT_SLURM_CONFIG)"
    echo ""
    echo -e "${CYAN}Options:${NC}"
    echo "  --local           - Run locally without Slurm allocation"
    echo "  --container       - Run using Apptainer container"
    echo "  --use-current-node - Use current node instead of requesting new allocation"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  ./start_client_service.sh http://localhost:8000 2h"
    echo "  ./start_client_service.sh http://192.168.1.100:8000 30min my_slurm_config"
    echo "  ./start_client_service.sh http://localhost:8000 1h --local"
    echo "  ./start_client_service.sh http://localhost:8000 1h --container"
    echo "  ./start_client_service.sh http://localhost:8000 1h --use-current-node --container"
    echo "  ./start_client_service.sh http://localhost:8000 1h my_slurm_config --container"
    echo ""
    echo -e "${CYAN}Slurm Configuration:${NC}"
    echo "  Account: $SLURM_ACCOUNT"
    echo "  QoS: $SLURM_QOS"
    echo "  Nodes: $SLURM_NODES"
    echo "  CPUs per node: $SLURM_CPUS"
    echo ""
    echo -e "${CYAN}Container Configuration:${NC}"
    echo "  Container image: $CONTAINER_IMAGE"
    echo "  Note: Container must be built with 'apptainer build' command"
    echo ""
    echo -e "${CYAN}Notes:${NC}"
    echo "  - The service will start on port 8001"
    echo "  - Make sure the server service is running before starting this"
    echo "  - Use Ctrl+C to stop the service"
    echo "  - Use --local flag for testing on login node"
    echo "  - All Python logs will be printed to console"
}

# Check command line arguments
if [ $# -lt 2 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    print_banner
    show_help
    exit 0
fi

# Parse arguments
SERVER_ADDRESS="$1"
TIME_ALLOCATION="$2"
SLURM_CONFIG=""

# Parse optional arguments
shift 2
while [ $# -gt 0 ]; do
    case "$1" in
        --local)
            LOCAL_MODE=true
            ;;
        --container)
            CONTAINER_MODE=true
            ;;
        --use-current-node)
            USE_CURRENT_NODE=true
            ;;
        *)
            if [ -z "$SLURM_CONFIG" ]; then
                SLURM_CONFIG="$1"
            else
                print_error "Unknown argument: $1"
                exit 1
            fi
            ;;
    esac
    shift
done

# Set default Slurm config if not provided
if [ -z "$SLURM_CONFIG" ]; then
    SLURM_CONFIG="$DEFAULT_SLURM_CONFIG"
fi

validate_time_format() {
    local time="$1"
    
    # Check common time formats: 30min, 2h, 1:30:00, 01:30:00, etc.
    if [[ "$time" =~ ^[0-9]+min$ ]] || [[ "$time" =~ ^[0-9]+h$ ]] || [[ "$time" =~ ^[0-9]+:[0-9]+:[0-9]+$ ]] || [[ "$time" =~ ^[0-9]+-[0-9]+:[0-9]+:[0-9]+$ ]]; then
        return 0
    else
        print_error "Invalid time format: $time"
        print_info "Valid formats: 30min, 2h, 1:30:00, 1-02:30:00"
        return 1
    fi
}

print_banner
echo ""

# Validate server address format
if [[ ! "$SERVER_ADDRESS" =~ ^https?:// ]]; then
    print_error "Invalid server address format. Must start with http:// or https://"
    echo -e "${CYAN}Example:${NC} http://localhost:8000"
    exit 1
fi

# Validate time allocation format
validate_time_format "$TIME_ALLOCATION" || exit 1

# Check if we're in the correct directory
if [ ! -f "$SCRIPT_DIR/main.py" ]; then
    print_error "main.py not found in $SCRIPT_DIR directory"
    print_info "Please run this script from the client scripts directory:"
    print_info "cd /path/to/services/client/scripts && ./start_client_service.sh"
    exit 1
fi

# Check container requirements if container mode is enabled
if [ "$CONTAINER_MODE" = "true" ]; then
    # Check if container image exists
    if [ ! -f "$SCRIPT_DIR/$CONTAINER_IMAGE" ]; then
        print_error "Container image '$CONTAINER_IMAGE' not found in $SCRIPT_DIR"
        print_info "Please build the container first with:"
        print_info "cd scripts && ./build_service_container.sh"
        exit 1
    fi
    
    print_success "Container image found: $SCRIPT_DIR/$CONTAINER_IMAGE"
    print_info "Apptainer will be loaded on the compute node"
fi

# Check if Slurm config file exists (only if not in local mode)
if [ "$LOCAL_MODE" = "false" ] && [ ! -f "$SCRIPT_DIR/$SLURM_CONFIG" ]; then
    print_warning "Slurm config file '$SLURM_CONFIG' not found in $SCRIPT_DIR"
    print_info "The service will use auto-detected Slurm configuration"
    SLURM_CONFIG=""
fi

# Display configuration
print_info "Configuration:"
echo -e "  ${CYAN}Server Address:${NC} $SERVER_ADDRESS"
echo -e "  ${CYAN}Time Allocation:${NC} $TIME_ALLOCATION"
echo -e "  ${CYAN}Execution Mode:${NC} $([ "$LOCAL_MODE" = "true" ] && echo "Local (login node)" || ([ "$USE_CURRENT_NODE" = "true" ] && echo "Current node ($(hostname))" || echo "Slurm (new compute node)"))"
echo -e "  ${CYAN}Container Mode:${NC} $([ "$CONTAINER_MODE" = "true" ] && echo "Enabled ($CONTAINER_IMAGE)" || echo "Disabled")"
if [ "$LOCAL_MODE" = "false" ] && [ "$USE_CURRENT_NODE" = "false" ]; then
    echo -e "  ${CYAN}Slurm Account:${NC} $SLURM_ACCOUNT"
    echo -e "  ${CYAN}Slurm QoS:${NC} $SLURM_QOS"
    echo -e "  ${CYAN}Nodes:${NC} $SLURM_NODES"
    echo -e "  ${CYAN}CPUs per node:${NC} $SLURM_CPUS"
fi
echo -e "  ${CYAN}Slurm Config:${NC} ${SLURM_CONFIG:-"Auto-detected"}"
echo -e "  ${CYAN}Service Port:${NC} 8001"
echo -e "  ${CYAN}Working Directory:${NC} $SCRIPT_DIR"
echo ""

# Check dependencies based on execution mode
if [ "$CONTAINER_MODE" = "false" ]; then
    # Check if Python 3 is available
    if ! command -v python3 >/dev/null 2>&1; then
        print_error "Python 3 is not installed or not in PATH"
        exit 1
    fi

    # Check if required Python packages are available
    python3 -c "import fastapi, uvicorn" 2>/dev/null || {
        print_error "Required Python packages not found (fastapi, uvicorn)"
        print_info "Install with: pip install fastapi uvicorn"
        exit 1
    }
fi

print_success "All dependencies satisfied"

# Function to run the client service
run_client_service() {
    local current_node=$(hostname)
    echo "========================================="
    echo "AI Factory Client Service Starting"
    echo "========================================="
    echo "Node: $current_node"
    echo "Date: $(date)"
    echo "Working Directory: $(pwd)"
    echo "Server Address: $SERVER_ADDRESS"
    echo "Slurm Config: ${SLURM_CONFIG:-"Auto-detected"}"
    echo "Container Mode: $([ "$CONTAINER_MODE" = "true" ] && echo "Enabled ($CONTAINER_IMAGE)" || echo "Disabled")"
    echo "========================================="
    echo ""
    
    # Load required modules if container mode is enabled
    if [ "$CONTAINER_MODE" = "true" ]; then
        echo "Loading Apptainer modules..."
        module load env/release/2023.1
        module load Apptainer/1.2.4-GCCcore-12.3.0 || { 
            echo "ERROR: Apptainer module not available on node: $current_node"
            exit 1
        }
        echo "Apptainer version: $(apptainer --version)"
        echo ""
        
        # Get current user for container
        export CONTAINER_USER="${USER:-$(whoami)}"
        echo "Container user: $CONTAINER_USER"
        
        # Generate JWT token on host for container use
        echo "Generating JWT token on host for container..."
        HOST_JWT=$(scontrol token | grep SLURM_JWT | cut -d= -f2 2>/dev/null || echo "")
        if [ -n "$HOST_JWT" ]; then
            echo "Host token generated: ${HOST_JWT:0:20}..."
        else
            print_error "Could not generate JWT token on host"
            exit 1
        fi
        echo ""
    fi
    
    # Start the client service
    if [ "$CONTAINER_MODE" = "true" ]; then
        if [ -n "$SLURM_CONFIG" ]; then
            echo "Starting: apptainer run $SCRIPT_DIR/$CONTAINER_IMAGE $SERVER_ADDRESS $SLURM_CONFIG"
            apptainer run \
                --env USER="$CONTAINER_USER" \
                --env SLURM_JWT="$HOST_JWT" \
                --bind /home/users/${CONTAINER_USER}:/home/users/${CONTAINER_USER} \
                "$SCRIPT_DIR/$CONTAINER_IMAGE" "$SERVER_ADDRESS" "$SLURM_CONFIG" --container
        else
            echo "Starting: apptainer run $SCRIPT_DIR/$CONTAINER_IMAGE $SERVER_ADDRESS"
            apptainer run \
                --env USER="$CONTAINER_USER" \
                --env SLURM_JWT="$HOST_JWT" \
                --bind /home/users/${CONTAINER_USER}:/home/users/${CONTAINER_USER} \
                "$SCRIPT_DIR/$CONTAINER_IMAGE" "$SERVER_ADDRESS" --container
        fi
    else
        if [ -n "$SLURM_CONFIG" ]; then
            if [ "$CONTAINER_MODE" = "true" ]; then
                echo "Starting: python3 main.py $SERVER_ADDRESS $SLURM_CONFIG --container"
                cd "$SCRIPT_DIR" && python3 main.py "$SERVER_ADDRESS" "$SLURM_CONFIG" --container
            else
                echo "Starting: python3 main.py $SERVER_ADDRESS $SLURM_CONFIG"
                cd "$SCRIPT_DIR" && python3 main.py "$SERVER_ADDRESS" "$SLURM_CONFIG"
            fi
        else
            if [ "$CONTAINER_MODE" = "true" ]; then
                echo "Starting: python3 main.py $SERVER_ADDRESS --container"
                cd "$SCRIPT_DIR" && python3 main.py "$SERVER_ADDRESS" --container
            else
                echo "Starting: python3 main.py $SERVER_ADDRESS"
                cd "$SCRIPT_DIR" && python3 main.py "$SERVER_ADDRESS"
            fi
        fi
    fi
}

# Check for --use-current-node flag
if [ "$USE_CURRENT_NODE" = "true" ]; then
    echo "Using current node: $(hostname)"
    echo "========================================="
    
    cd "${SCRIPT_DIR}"
    run_client_service

elif [ "$LOCAL_MODE" = "true" ]; then
    print_warning "Running in LOCAL MODE on login node (for testing only)"
    print_info "Starting Client Service locally..."
    echo ""
    
    cd "${SCRIPT_DIR}"
    run_client_service

else
    echo "Requesting compute node allocation..."
    echo ""

salloc -A $SLURM_ACCOUNT -t $TIME_ALLOCATION -p cpu -q $SLURM_QOS -N $SLURM_NODES --ntasks-per-node=1 --cpus-per-task=$SLURM_CPUS << EOF
    # Use SCRIPT_DIR from parent shell
    cd "${SCRIPT_DIR}"
    
    echo "========================================="
    echo "AI Factory Client Service Starting"
    echo "========================================="
    echo "Node: \$(hostname)"
    echo "Date: \$(date)"
    echo "Working Directory: \$(pwd)"
    echo "Server Address: $SERVER_ADDRESS"
    echo "Slurm Config: ${SLURM_CONFIG:-"Auto-detected"}"
    echo "Container Mode: $([ "$CONTAINER_MODE" = "true" ] && echo "Enabled ($CONTAINER_IMAGE)" || echo "Disabled")"
    echo "========================================="
    echo ""
    
    # Load required modules if container mode is enabled
    if [ "$CONTAINER_MODE" = "true" ]; then
        echo "Loading Apptainer modules..."
        module load env/release/2023.1
        module load Apptainer/1.2.4-GCCcore-12.3.0 || { 
            echo "ERROR: Apptainer module not available on compute node"
            exit 1
        }
        echo "Apptainer version: \$(apptainer --version)"
        echo ""
        
        # Get current user for container
        export CONTAINER_USER="\${USER:-\$(whoami)}"
        echo "Container user: \$CONTAINER_USER"
        
        # Generate JWT token on host for container use
        echo "Generating JWT token on host for container..."
        HOST_JWT=\$(scontrol token | grep SLURM_JWT | cut -d= -f2 2>/dev/null || echo "")
        if [ -n "\$HOST_JWT" ]; then
            echo "Host token generated: \${HOST_JWT:0:20}..."
        else
            echo "ERROR: Could not generate JWT token on host"
            exit 1
        fi
        echo ""
    fi
    
    # Start the client service
    if [ "$CONTAINER_MODE" = "true" ]; then
        if [ -n "$SLURM_CONFIG" ]; then
            echo "Starting: apptainer run $SCRIPT_DIR/$CONTAINER_IMAGE $SERVER_ADDRESS $SLURM_CONFIG"
            apptainer run \\
                --env USER="\$CONTAINER_USER" \\
                --env SLURM_JWT="\$HOST_JWT" \\
                --bind /home/users/\${CONTAINER_USER}:/home/users/\${CONTAINER_USER} \\
                "$SCRIPT_DIR/$CONTAINER_IMAGE" "$SERVER_ADDRESS" "$SLURM_CONFIG" --container
        else
            echo "Starting: apptainer run $SCRIPT_DIR/$CONTAINER_IMAGE $SERVER_ADDRESS"
            apptainer run \\
                --env USER="\$CONTAINER_USER" \\
                --env SLURM_JWT="\$HOST_JWT" \\
                --bind /home/users/\${CONTAINER_USER}:/home/users/\${CONTAINER_USER} \\
                "$SCRIPT_DIR/$CONTAINER_IMAGE" "$SERVER_ADDRESS" --container
        fi
    else
        if [ -n "$SLURM_CONFIG" ]; then
            if [ "$CONTAINER_MODE" = "true" ]; then
                echo "Starting: python3 main.py $SERVER_ADDRESS $SLURM_CONFIG --container"
                python3 main.py "$SERVER_ADDRESS" "$SLURM_CONFIG" --container
            else
                echo "Starting: python3 main.py $SERVER_ADDRESS $SLURM_CONFIG"
                python3 main.py "$SERVER_ADDRESS" "$SLURM_CONFIG"
            fi
        else
            if [ "$CONTAINER_MODE" = "true" ]; then
                echo "Starting: python3 main.py $SERVER_ADDRESS --container"
                python3 main.py "$SERVER_ADDRESS" --container
            else
                echo "Starting: python3 main.py $SERVER_ADDRESS"
                python3 main.py "$SERVER_ADDRESS"
            fi
        fi
    fi
EOF
fi