#!/bin/bash
# =============================================================================
# Client Service Launcher with Slurm Allocation
# =============================================================================
# Description: Launches the AI Factory Client Service on a Slurm compute node
# Usage: ./start_client_service.sh <server_address> <time_allocation> [slurm_config_file] [--local]
# Author: AI Assistant
# =============================================================================

set -e

# Default values
DEFAULT_SLURM_CONFIG="example_slurm_config"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_MODE=false

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
    echo "  ./start_client_service.sh <server_address> <time_allocation> [slurm_config_file] [--local]"
    echo ""
    echo -e "${CYAN}Parameters:${NC}"
    echo "  server_address     - Address of the server service (e.g., http://server-ip:8000)"
    echo "  time_allocation    - Slurm time allocation (e.g., 30min, 2h, 1:30:00)"
    echo "  slurm_config_file  - Optional: Path to Slurm configuration file"
    echo "                      (default: $DEFAULT_SLURM_CONFIG)"
    echo "  --local           - Optional: Run locally without Slurm allocation"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  ./start_client_service.sh http://localhost:8000 2h"
    echo "  ./start_client_service.sh http://192.168.1.100:8000 30min my_slurm_config"
    echo "  ./start_client_service.sh http://localhost:8000 1h --local"
    echo ""
    echo -e "${CYAN}Slurm Configuration:${NC}"
    echo "  Account: $SLURM_ACCOUNT"
    echo "  QoS: $SLURM_QOS"
    echo "  Nodes: $SLURM_NODES"
    echo "  CPUs per node: $SLURM_CPUS"
    echo ""
    echo -e "${CYAN}Notes:${NC}"
    echo "  - The service will start on port 8001"
    echo "  - Make sure the server service is running before starting this"
    echo "  - Use Ctrl+C to stop the service"
    echo "  - Use --local flag for testing on login node"
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
LOCAL_MODE=false

# Parse optional arguments
shift 2
while [ $# -gt 0 ]; do
    case "$1" in
        --local)
            LOCAL_MODE=true
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
if [ ! -f "main.py" ]; then
    print_error "main.py not found in current directory"
    print_info "Please run this script from the client service directory:"
    print_info "cd /path/to/services/client/src && ./start_client_service.sh"
    exit 1
fi

# Check if Slurm config file exists (only if not in local mode)
if [ "$LOCAL_MODE" = "false" ] && [ ! -f "$SLURM_CONFIG" ]; then
    print_warning "Slurm config file '$SLURM_CONFIG' not found"
    print_info "The service will use auto-detected Slurm configuration"
    SLURM_CONFIG=""
fi

# Display configuration
print_info "Configuration:"
echo -e "  ${CYAN}Server Address:${NC} $SERVER_ADDRESS"
echo -e "  ${CYAN}Time Allocation:${NC} $TIME_ALLOCATION"
echo -e "  ${CYAN}Execution Mode:${NC} $([ "$LOCAL_MODE" = "true" ] && echo "Local (login node)" || echo "Slurm (compute node)")"
if [ "$LOCAL_MODE" = "false" ]; then
    echo -e "  ${CYAN}Slurm Account:${NC} $SLURM_ACCOUNT"
    echo -e "  ${CYAN}Slurm QoS:${NC} $SLURM_QOS"
    echo -e "  ${CYAN}Nodes:${NC} $SLURM_NODES"
    echo -e "  ${CYAN}CPUs per node:${NC} $SLURM_CPUS"
fi
echo -e "  ${CYAN}Slurm Config:${NC} ${SLURM_CONFIG:-"Auto-detected"}"
echo -e "  ${CYAN}Service Port:${NC} 8001"
echo -e "  ${CYAN}Working Directory:${NC} $SCRIPT_DIR"
echo ""

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

print_success "All dependencies satisfied"

if [ "$LOCAL_MODE" = "true" ]; then
    print_warning "Running in LOCAL MODE on login node (for testing only)"
    print_info "Starting Client Service locally..."
    echo ""
    
    # Start the client service locally
    if [ -n "$SLURM_CONFIG" ]; then
        print_info "Command: python3 main.py $SERVER_ADDRESS $SLURM_CONFIG"
        exec python3 main.py "$SERVER_ADDRESS" "$SLURM_CONFIG"
    else
        print_info "Command: python3 main.py $SERVER_ADDRESS"
        exec python3 main.py "$SERVER_ADDRESS"
    fi
else
    print_info "Preparing Slurm job submission..."
    echo ""
    
    # Create temporary script for Slurm execution
    TEMP_SCRIPT="$HOME/client-service-$$-$(date +%s).sh"
    
    cat > "$TEMP_SCRIPT" << EOF
#!/bin/bash
# Auto-generated script for Client Service execution on compute node

set -e

# Change to the correct directory
cd "$SCRIPT_DIR"

# Display node information
echo "======================================"
echo "AI Factory Client Service Starting"
echo "======================================"
echo "Node: \$(hostname)"
echo "Date: \$(date)"
echo "Working Directory: \$(pwd)"
echo "Server Address: $SERVER_ADDRESS"
echo "Slurm Config: ${SLURM_CONFIG:-"Auto-detected"}"
echo "======================================"
echo ""

# Start the client service
if [ -n "$SLURM_CONFIG" ]; then
    echo "Starting: python3 main.py $SERVER_ADDRESS $SLURM_CONFIG"
    python3 main.py "$SERVER_ADDRESS" "$SLURM_CONFIG"
else
    echo "Starting: python3 main.py $SERVER_ADDRESS"
    python3 main.py "$SERVER_ADDRESS"
fi
EOF

    chmod +x "$TEMP_SCRIPT"
    
    print_success "Temporary script created: $TEMP_SCRIPT"
    print_info "Submitting job to Slurm scheduler..."
    print_info "Job will run for: $TIME_ALLOCATION"
    echo ""
    
    # Submit the job using srun
    srun \
        --account="$SLURM_ACCOUNT" \
        --qos="$SLURM_QOS" \
        --time="$TIME_ALLOCATION" \
        --nodes="$SLURM_NODES" \
        --ntasks-per-node=1 \
        --cpus-per-task="$SLURM_CPUS" \
        --job-name="ai-factory-client-service" \
        --pty \
        bash "$TEMP_SCRIPT"
    
    # Cleanup
    rm -f "$TEMP_SCRIPT"
    print_info "Job completed. Temporary script removed."
fi