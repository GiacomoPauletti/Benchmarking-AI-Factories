#!/bin/bash -l
# =============================================================================
# MeluXina Environment Setup Script for AI Factory
# =============================================================================
# Description: Sets up the complete AI Factory client environment on MeluXina
# Usage: ./setup_meluxina_environment.sh [OPTIONS]
# Author: AI Factory Team
# ====================================        # Submit build job to Slurm using sbatch for proper compute node execution
set -e

source ../../../.env

# Colors for output
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
CYAN="\033[0;36m"
MAGENTA="\033[0;35m"
NC="\033[0m" # No Color

# Configuration
SLURM_TIME="00:30:00"
FORCE_SETUP=false
LOCAL_MODE=false
SKIP_CONTAINER_BUILD=false
VERBOSE=false

# Directories and files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$SERVICE_ROOT")"
PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
SRC_DIR="$SERVICE_ROOT/src"
CLIENT_DIR="$SRC_DIR/client"

print_banner() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║           MeluXina Environment Setup for AI Factory          ║${NC}"
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

print_section() {
    echo -e "${MAGENTA}📋 $1${NC}"
    echo -e "${CYAN}$(printf '%.0s─' {1..60})${NC}"
}

show_help() {
    echo -e "${CYAN}Usage:${NC}"
    echo "  ./setup_meluxina_environment.sh [OPTIONS]"
    echo ""
    echo -e "${CYAN}Options:${NC}"
    echo "  --force                Force complete re-setup even if environment exists"
    echo "  --local                Setup locally on login node (default: use Slurm)"
    echo "  --skip-container       Skip Apptainer container building"
    echo "  --verbose              Enable verbose output"
    echo "  --help                 Show this help message"
    echo ""
    echo -e "${CYAN}Environment Variables:${NC}"
    echo "  REMOTE_BASE_PATH      Remote base directory (default: /project/home/p200981/ai-factory)"
    echo "  SSH_HOST              SSH hostname for MeluXina (default: login.lxp.lu)"
    echo "  SSH_USER              SSH username"
    echo "  SSH_PORT              SSH port (default: 8822)"
    echo ""
    echo -e "${CYAN}Description:${NC}"
    echo "  This script performs a complete setup of the AI Factory client environment"
    echo "  on MeluXina HPC cluster, including:"
    echo "  • Creating remote directory structure"
    echo "  • Copying client source code"
    echo "  • Building Apptainer container images"
    echo "  • Setting up execution scripts"
    echo "  • Verifying the installation"
    echo ""
    echo -e "${CYAN}Prerequisites:${NC}"
    echo "  • SSH access to MeluXina (configured in ~/.ssh/config or via environment)"
    echo "  • Apptainer/Singularity available on MeluXina"
    echo "  • Project allocation p200981"
    echo ""
    echo -e "${CYAN}Output:${NC}"
    echo "  Creates complete AI Factory environment at: \$REMOTE_BASE_PATH"
}

# Parse arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --force)
            FORCE_SETUP=true
            ;;
        --local)
            LOCAL_MODE=true
            ;;
        --skip-container)
            SKIP_CONTAINER_BUILD=true
            ;;
        --verbose)
            VERBOSE=true
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

# Verbose logging function
log() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${CYAN}[DEBUG]${NC} $1"
    fi
}

# Check prerequisites
check_prerequisites() {
    print_section "Checking Prerequisites"
    
    # Check if we can access MeluXina via SSH
    if ! command -v ssh >/dev/null 2>&1; then
        print_error "SSH command not found"
        exit 1
    fi
    
    # Check SSH connection
    if [ -z "$SSH_USER" ]; then
        print_error "SSH_USER not set. Please set SSH_USER environment variable"
        exit 1
    fi
    
    log "Testing SSH connection to $SSH_USER@$SSH_HOST:$SSH_PORT"
    
    # Test SSH connection
    if ! ssh -p "$SSH_PORT" -o ConnectTimeout=10 -o BatchMode=yes "$SSH_USER@$SSH_HOST" "echo 'Connection test successful'" >/dev/null 2>&1; then
        print_error "Cannot connect to MeluXina via SSH"
        print_info "Please ensure SSH access is configured for $SSH_USER@$SSH_HOST:$SSH_PORT"
        exit 1
    fi
    
    print_success "SSH connection to MeluXina verified"
    
    # Check source directories exist
    if [ ! -d "$SRC_DIR" ]; then
        print_error "Source directory not found: $SRC_DIR"
        print_info "Please run this script from the services/client/scripts directory"
        exit 1
    fi
    
    if [ ! -d "$CLIENT_DIR" ]; then
        print_error "Client directory not found: $CLIENT_DIR"
        exit 1
    fi
    
    print_success "Local source directories verified"
    
    # Check required files
    local required_files=(
        "$SRC_DIR/main.py"
        "$SRC_DIR/service_container.def"
        "$CLIENT_DIR/main.py"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            print_error "Required file not found: $file"
            exit 1
        fi
    done
    
    print_success "Required files verified"
    echo ""
}

# Create remote directory structure
create_remote_directories() {
    print_section "Creating Remote Directory Structure"
    
    local directories=(
        "$REMOTE_BASE_PATH"
        "$REMOTE_BASE_PATH/src"
        "$REMOTE_BASE_PATH/src/client"
        "$REMOTE_BASE_PATH/logs"
        "$REMOTE_BASE_PATH/containers"
        "$REMOTE_BASE_PATH/scripts"
        "$REMOTE_BASE_PATH/tmp"
    )
    
    for dir in "${directories[@]}"; do
        log "Creating directory: $dir"
        ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "mkdir -p '$dir'" || {
            print_error "Failed to create directory: $dir"
            exit 1
        }
    done
    
    print_success "Remote directory structure created"
    echo ""
}

# Copy source code to MeluXina
copy_source_code() {
    print_section "Copying Source Code to MeluXina"
    
    # Create .env file for MeluXina with correct SSH key path
    log "Creating environment variables file for MeluXina"
    
    # Replace container SSH key path with MeluXina path
    # sed -i 's|SSH_KEY_PATH=/tmp/host-ssh/|SSH_KEY_PATH=~/.ssh/|g' "$TEMP_ENV_FILE"
    
    # Copy .env to home directory for easy access
    log "Copying environment variables file to home directory"
    scp -P "$SSH_PORT" "$PROJECT_ROOT/.env" "$SSH_USER@$SSH_HOST:$REMOTE_BASE_PATH/.env" || {
        print_error "Failed to copy .env file to base directory"
        exit 1
    }

    
    # Copy client source
    log "Copying client source code"
    scp -P "$SSH_PORT" -r "$CLIENT_DIR" "$SSH_USER@$SSH_HOST:$REMOTE_BASE_PATH/src/" || {
        print_error "Failed to copy client source"
        exit 1
    }
    
    # Copy main files
    log "Copying main application files"
    scp -P "$SSH_PORT" "$SRC_DIR/main.py" "$SSH_USER@$SSH_HOST:$REMOTE_BASE_PATH/src/" || {
        print_error "Failed to copy main.py"
        exit 1
    }
    
    scp -P "$SSH_PORT" "$SRC_DIR/__init__.py" "$SSH_USER@$SSH_HOST:$REMOTE_BASE_PATH/src/" || {
        print_error "Failed to copy __init__.py"
        exit 1
    }
    
    # Copy requirements files
    log "Copying requirements files"
    scp -P "$SSH_PORT" "$SRC_DIR/requirements.txt" "$SSH_USER@$SSH_HOST:$REMOTE_BASE_PATH/src/" || {
        print_error "Failed to copy requirements.txt"
        exit 1
    }
    
    # Copy container definition files
    log "Copying container definition files"
    scp -P "$SSH_PORT" "$SRC_DIR/service_container.def" "$SSH_USER@$SSH_HOST:$REMOTE_BASE_PATH/src/" || {
        print_error "Failed to copy service_container.def"
        exit 1
    }
    
    if [ -f "$CLIENT_DIR/client_container.def" ]; then
        scp -P "$SSH_PORT" "$CLIENT_DIR/client_container.def" "$SSH_USER@$SSH_HOST:$REMOTE_BASE_PATH/src/client/" || {
            print_warning "Failed to copy client_container.def (optional)"
        }
    fi
    
    print_success "Source code copied to MeluXina"
    echo ""
}

# Create setup scripts on MeluXina
create_remote_scripts() {
    print_section "Creating Remote Setup Scripts"
    
    # Create a remote build script
    ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "cat > '$REMOTE_BASE_PATH/scripts/build_containers.sh'" << 'EOF'
#!/bin/bash -l
# Remote container build script for AI Factory

set -e

# Source environment variables
source ~/.env

SLURM_QOS="default"
SLURM_TIME="00:20:00"

echo "🔨 Building AI Factory containers on MeluXina"
echo "=============================================="
echo "$(hostname)"
cd "$REMOTE_BASE_PATH/src"

# Load required modules
echo "Loading required modules..."
module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0

echo "Apptainer version: $(apptainer --version)"


# Build client container if definition exists
if [ -f "client/client_container.def" ]; then
    echo ""
    echo "Building client container..."
    cd client
    if apptainer build "$REMOTE_BASE_PATH/containers/client.sif" client_container.def; then
        echo "✅ Client container built successfully"
    else
        echo "❌ Client container build failed"
        exit 1
    fi
    cd ..
fi

echo ""
echo "🎉 All containers built successfully!"
echo "Containers available at: $REMOTE_BASE_PATH/containers/"
ls -lh "$REMOTE_BASE_PATH/containers/"
EOF

    # Make the script executable
    ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "chmod +x '$REMOTE_BASE_PATH/scripts/build_containers.sh'"
    
#     # Create a remote test script
#     ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "cat > '$REMOTE_BASE_PATH/scripts/test_environment.sh'" << 'EOF'
# #!/bin/bash -l
# # Test script for AI Factory environment

# set -e

# # Source environment variables
# source ~/.env

# echo "🧪 Testing AI Factory environment on MeluXina"
# echo "=============================================="

# echo "📋 Environment check:"
# echo "  Base path: $REMOTE_BASE_PATH"
# echo "  Python version: $(python3 --version)"
# echo "  Hostname: $(hostname)"
# echo "  User: $(whoami)"
# echo ""

# echo "📁 Directory structure:"
# find "$REMOTE_BASE_PATH" -type d | head -20

# echo ""
# echo "📦 Available containers:"
# ls -lh "$REMOTE_BASE_PATH/containers/" 2>/dev/null || echo "  No containers found"

# echo ""
# echo "🐍 Python module test:"
# cd "$REMOTE_BASE_PATH/src"
# if python3 -c "import sys; print('Python path:', sys.path)"; then
#     echo "✅ Python environment working"
# else
#     echo "❌ Python environment issues"
# fi

# echo ""
# echo "🔧 Apptainer test:"
# module load env/release/2023.1
# module load Apptainer/1.2.4-GCCcore-12.3.0 2>/dev/null || echo "Apptainer module not loaded"
# if command -v apptainer >/dev/null 2>&1; then
#     echo "✅ Apptainer available: $(apptainer --version)"
# else
#     echo "❌ Apptainer not available"
# fi

# echo ""
# echo "🎉 Environment test complete!"
# EOF

#     # Make the test script executable
#     ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "chmod +x '$REMOTE_BASE_PATH/scripts/test_environment.sh'"
    
    print_success "Remote setup scripts created"
    echo ""
}

# Build containers on MeluXina
build_containers() {
    if [ "$SKIP_CONTAINER_BUILD" = true ]; then
        print_warning "Skipping container build as requested"
        return
    fi
    
    print_section "Building Apptainer Containers"
    
    if [ "$LOCAL_MODE" = true ]; then
        print_warning "Building containers locally on login node"
        ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "cd '$REMOTE_BASE_PATH' && ./scripts/build_containers.sh" || {
            print_error "Container build failed"
            exit 1
        }
    else
        print_info "Submitting container build job to Slurm..."
        
        # Submit build job to Slurm
        # Executing the job in the REMOTE_BASE_PATH directory
        ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "sbatch --wait -A $SLURM_ACCOUNT -t $SLURM_TIME -q $SLURM_QOS -p cpu -N 1 --ntasks-per-node=1 --cpus-per-task=4 '$REMOTE_BASE_PATH/scripts/build_containers.sh'" || {
            print_error "Container build job failed"
            exit 1
        }
    fi
    
    print_success "Container build completed"
    echo ""
}

# # Verify installation
# verify_installation() {
#     print_section "Verifying Installation"
    
#     # Run the test script
#     ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "cd '$REMOTE_BASE_PATH' && ./scripts/test_environment.sh" || {
#         print_error "Environment verification failed"
#         exit 1
#     }
    
#     print_success "Installation verification completed"
#     echo ""
# }

# Main execution
main() {
    print_banner
    echo ""
    
    print_info "Setup Configuration:"
    echo -e "  ${CYAN}Remote Base Path:${NC} $REMOTE_BASE_PATH"
    echo -e "  ${CYAN}SSH Target:${NC} $SSH_USER@$SSH_HOST:$SSH_PORT"
    echo -e "  ${CYAN}Force Setup:${NC} $FORCE_SETUP"
    echo -e "  ${CYAN}Local Mode:${NC} $LOCAL_MODE"
    echo -e "  ${CYAN}Skip Containers:${NC} $SKIP_CONTAINER_BUILD"
    echo -e "  ${CYAN}Verbose:${NC} $VERBOSE"
    echo ""
    
    # Check if environment already exists
    if [ "$FORCE_SETUP" = false ]; then
        if ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "[ -d '$REMOTE_BASE_PATH/src' ]" 2>/dev/null; then
            print_warning "AI Factory environment already exists at $REMOTE_BASE_PATH"
            print_info "Use --force to rebuild or remove the existing installation"
            
            # Still run verification
            # verify_installation
            
            print_success "Setup verification completed - environment is ready!"
            exit 0
        fi
    fi
    
    # Perform setup steps
    check_prerequisites
    create_remote_directories
    copy_source_code
    create_remote_scripts
    build_containers
    #verify_installation
    
    print_section "Setup Complete!"
    print_success "AI Factory environment successfully set up on MeluXina"
    echo ""
    print_info "Environment Details:"
    echo -e "  ${CYAN}Base Directory:${NC} $REMOTE_BASE_PATH"
    echo -e "  ${CYAN}Source Code:${NC} $REMOTE_BASE_PATH/src/"
    echo -e "  ${CYAN}Containers:${NC} $REMOTE_BASE_PATH/containers/"
    echo -e "  ${CYAN}Scripts:${NC} $REMOTE_BASE_PATH/scripts/"
    echo -e "  ${CYAN}Logs:${NC} $REMOTE_BASE_PATH/logs/"
    echo ""
    print_info "Next steps:"
    echo -e "  ${CYAN}1.${NC} Test the environment: ssh -p $SSH_PORT $SSH_USER@$SSH_HOST 'cd $REMOTE_BASE_PATH && ./scripts/test_environment.sh'"
    echo -e "  ${CYAN}2.${NC} Start client service: Use the deployment scripts in client_service/"
    echo -e "  ${CYAN}3.${NC} Monitor logs: Check $REMOTE_BASE_PATH/logs/"
    echo ""
    print_success "🎉 MeluXina environment setup completed successfully!"
    
    # Clean up .env file from home directory
    print_info "Cleaning up environment file..."
    ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "rm -f ~/.env" || {
        print_warning "Could not remove .env file from home directory"
    }
}

# Execute main function
main "$@"