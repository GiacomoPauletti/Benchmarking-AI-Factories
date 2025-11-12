#!/bin/bash
# =============================================================================
# AI Factory Interactive Shell for Meluxina
# =============================================================================
# Description: Interactive shell for testing AI Factory client service APIs
# Usage: ./start_shell.sh [--test-local]
# Author: AI Assistant
# =============================================================================

set -e

# Default values - now runs locally by default
LOCAL_MODE=true

# Parse command line arguments
if [ "$1" = "--cluster" ]; then
    echo "🚀 Running on cluster with Slurm allocation..."
    echo "📋 Allocation: Account p200981, Queue default, Time limit 2h"
    LOCAL_MODE=false
fi

if [ "$LOCAL_MODE" = "true" ]; then
    echo "🧪 Starting shell in local mode..."
    echo "💻 Running on local machine for development testing"
else
    echo "🚀 Starting interactive Meluxina shell for AI Factory testing..."
    echo "⏳ Requesting compute node allocation..."
fi
echo ""

# Create temporary script in home directory (accessible from compute nodes)
TEMP_SCRIPT="$HOME/ai-factory-shell-$$-$(date +%s).sh"

# Create the interactive shell script that will run inside Slurm
cat > "$TEMP_SCRIPT" << 'SCRIPT_EOF'
#!/bin/bash
# =============================================================================
# INTERACTIVE SHELL FUNCTIONS FOR AI TESTING
# =============================================================================

# Colors for output formatting
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
PURPLE="\033[0;35m"
CYAN="\033[0;36m"
WHITE="\033[1;37m"
NC="\033[0m" # No Color

# Default client service URL
CLIENT_SERVICE_URL="http://localhost:8000"

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

print_banner() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║          AI Factory Client Service Interactive Shell          ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    printf "║ Node: %-55s ║\n" "$(hostname)"
    printf "║ Time: %-55s ║\n" "$(date)"
    echo "╚══════════════════════════════════════════════════════════════╝"
}

print_section() {
    echo -e "\n${CYAN}=== $1 ===${NC}"
}

print_command() {
    echo -e "${YELLOW}► $1${NC}"
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

format_json_response() {
    if command -v python3 >/dev/null 2>&1; then
        echo "$1" | python3 -m json.tool 2>/dev/null || echo "$1"
    else
        echo "$1"
    fi
}

# =============================================================================
# API TESTING FUNCTIONS
# =============================================================================

show_help() {
    print_section "Available Commands"
    echo -e "${WHITE}Configuration:${NC}"
    echo -e "  ${YELLOW}set_url <url>${NC}        - Set client service URL"
    echo -e "  ${YELLOW}show_config${NC}          - Show current configuration"
    echo ""
    echo -e "${WHITE}Health & Testing:${NC}"
    echo -e "  ${YELLOW}test_health${NC}          - Test service health"
    echo -e "  ${YELLOW}health${NC}               - Alias for test_health"
    echo ""
    echo -e "${WHITE}Client Group Management:${NC}"
    echo -e "  ${YELLOW}create_client_group <id> [n] [time]${NC} - Create client group with a certain ID, n clients (default: 3) and time limit (default: 30min)"
    echo -e "  ${YELLOW}create [n]${NC}           - Alias for create_client_group"
    echo -e "  ${YELLOW}get_client_group <id>${NC} - Get client group by ID"
    echo -e "  ${YELLOW}get <id>${NC}             - Alias for get_client_group"
    echo -e "  ${YELLOW}run_client_group <id>${NC} - Run client group"
    echo -e "  ${YELLOW}run <id>${NC}             - Alias for run_client_group"
    echo -e "  ${YELLOW}list_client_groups${NC}   - List all client groups"
    echo -e "  ${YELLOW}list${NC}                 - Alias for list_client_groups"
    echo ""
    echo -e "${WHITE}Utility:${NC}"
    echo -e "  ${YELLOW}clear${NC}                - Clear screen"
    echo -e "  ${YELLOW}help${NC} / ${YELLOW}h${NC}             - Show this help"
    echo -e "  ${YELLOW}exit${NC} / ${YELLOW}quit${NC} / ${YELLOW}q${NC}       - Exit shell"
}

set_url() {
    if [ -z "$1" ]; then
        print_error "Please provide a URL"
        echo -e "${CYAN}Usage:${NC} set_url http://client-service-ip:8000"
        return 1
    fi
    
    CLIENT_SERVICE_URL="$1"
    print_success "Client service URL set to: $CLIENT_SERVICE_URL"
}

show_config() {
    print_section "Current Configuration"
    echo -e "${CYAN}Client Service URL:${NC} $CLIENT_SERVICE_URL"
    echo -e "${CYAN}Current Node:${NC} $(hostname)"
    echo -e "${CYAN}Working Directory:${NC} $(pwd)"
}

test_health() {
    print_section "Health Check"
    print_command "GET $CLIENT_SERVICE_URL/health"
    
    response=$(curl -s -w "\\n%{http_code}" "$CLIENT_SERVICE_URL/health" 2>/dev/null || echo -e "\nconnection_failed")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "200" ]; then
        print_success "Service is healthy"
        echo -e "${CYAN}Response:${NC}"
        format_json_response "$body"
    elif [ "$http_code" = "connection_failed" ]; then
        print_error "Cannot connect to service at $CLIENT_SERVICE_URL"
        print_info "Check if the service is running and URL is correct"
    else
        print_error "Service health check failed (HTTP $http_code)"
        echo -e "${RED}Response:${NC} $body"
    fi
    echo ""
}

create_client_group() {
    local group_id="$1"
    local num_clients=${2:-3}
    local time_limit=${3:-"30"}

    print_section "Create Client Group"
    print_command "POST $CLIENT_SERVICE_URL/api/v1/client-group/$group_id"
    print_info "Creating group with $num_clients clients and time limit $time_limit"
    
    payload=$(cat <<EOF
{
    "num_clients": $num_clients,
    "time_limit": "$time_limit"
}
EOF
)
    
    echo -e "${CYAN}Payload:${NC}"
    format_json_response "$payload"
    echo ""
    
    response=$(curl -s -w "\\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "$CLIENT_SERVICE_URL/api/v1/client-group/$group_id" 2>/dev/null || echo -e "\nconnection_failed")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
        print_success "Client group created successfully"
        echo -e "${CYAN}Response:${NC}"
        format_json_response "$body"
    elif [ "$http_code" = "connection_failed" ]; then
        print_error "Cannot connect to service at $CLIENT_SERVICE_URL"
    else
        print_error "Failed to create client group (HTTP $http_code)"
        echo -e "${RED}Response:${NC} $body"
    fi
    echo ""
}

get_client_group() {
    if [ -z "$1" ]; then
        print_error "Please provide a client group ID"
        echo -e "${CYAN}Usage:${NC} get_client_group <group_id>"
        return 1
    fi
    
    local group_id="$1"
    
    print_section "Get Client Group"
    print_command "GET $CLIENT_SERVICE_URL/api/v1/client-group/$group_id"
    
    response=$(curl -s -w "\\n%{http_code}" "$CLIENT_SERVICE_URL/api/v1/client-group/$group_id" 2>/dev/null || echo -e "\nconnection_failed")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "200" ]; then
        print_success "Client group retrieved successfully"
        echo -e "${CYAN}Response:${NC}"
        format_json_response "$body"
    elif [ "$http_code" = "404" ]; then
        print_error "Client group not found (ID: $group_id)"
    elif [ "$http_code" = "connection_failed" ]; then
        print_error "Cannot connect to service at $CLIENT_SERVICE_URL"
    else
        print_error "Failed to get client group (HTTP $http_code)"
        echo -e "${RED}Response:${NC} $body"
    fi
    echo ""
}

run_client_group() {
    if [ -z "$1" ]; then
        print_error "Please provide a client group ID"
        echo -e "${CYAN}Usage:${NC} run_client_group <group_id>"
        return 1
    fi
    
    local group_id="$1"
    
    print_section "Start Client Group"
    print_command "POST $CLIENT_SERVICE_URL/api/v1/client-group/$group_id/run"
    
    response=$(curl -s -w "\\n%{http_code}" \
        -X POST \
        "$CLIENT_SERVICE_URL/api/v1/client-group/$group_id/run" 2>/dev/null || echo -e "\nconnection_failed")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "200" ]; then
        print_success "Client group started successfully"
        echo -e "${CYAN}Response:${NC}"
        format_json_response "$body"
    elif [ "$http_code" = "404" ]; then
        print_error "Client group not found (ID: $group_id)"
    elif [ "$http_code" = "connection_failed" ]; then
        print_error "Cannot connect to service at $CLIENT_SERVICE_URL"
    else
        print_error "Failed to start client group (HTTP $http_code)"
        echo -e "${RED}Response:${NC} $body"
    fi
    echo ""
}

list_client_groups() {
    print_section "List Client Groups"
    print_command "GET $CLIENT_SERVICE_URL/api/v1/client-groups"
    
    response=$(curl -s -w "\\n%{http_code}" "$CLIENT_SERVICE_URL/api/v1/client-groups" 2>/dev/null || echo -e "\nconnection_failed")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "200" ]; then
        print_success "Client groups retrieved successfully"
        echo -e "${CYAN}Response:${NC}"
        format_json_response "$body"
    elif [ "$http_code" = "connection_failed" ]; then
        print_error "Cannot connect to service at $CLIENT_SERVICE_URL"
    else
        print_error "Failed to list client groups (HTTP $http_code)"
        echo -e "${RED}Response:${NC} $body"
    fi
    echo ""
}

# =============================================================================
# MAIN INTERACTIVE SHELL FUNCTION
# =============================================================================

start_interactive_shell() {
    print_banner
    echo ""
    
    print_info "Welcome to the AI Factory interactive testing shell!"
    print_info "This shell is running on compute node: $(hostname)"
    echo ""
    
    echo "╭─────────────────────────────────────────────────────────────╮"
    echo "│ Setup Instructions                                        │"
    echo "╰─────────────────────────────────────────────────────────────╯"
    echo -e "\033[1;37m1.\033[0m First, set the client service URL:"
    echo -e "   \033[1;33mset_url http://<client_service_ip>:8000\033[0m"
    echo ""
    echo -e "\033[1;37m2.\033[0m Test the connection:"
    echo -e "   \033[1;33mtest_health\033[0m"
    echo ""
    echo -e "\033[1;37m3.\033[0m Start testing APIs:"
    echo -e "   \033[1;33mcreate_client_group 3\033[0m"
    echo -e "   \033[1;33mrun_client_group\033[0m"
    echo ""
    echo -e "\033[1;37m4.\033[0m Type \033[1;33mhelp\033[0m for all available commands"
    echo ""
    
    print_info "Type \033[1;37mexit\033[0m to leave the interactive shell"
    echo ""
    
    echo -e "\033[1;32m✅ Interactive shell ready on node: $(hostname)! Type 'help' to get started.\033[0m"
    echo ""
    
    # Custom interactive loop with proper function access
    echo "🔄 Starting AI Factory interactive shell..."
    echo "💡 All functions are available. Type 'help' to see commands."
    
    while true; do
        printf "\e[1;36mAI-Factory\e[0m:\e[1;34m%s\e[0m$ " "$(pwd)"
        read -r command args
        
        case "$command" in
            "help"|"h")
                show_help
                ;;
            "exit"|"quit"|"q")
                echo "👋 Goodbye!"
                exit 0
                ;;
            "set_url")
                set_url $args
                ;;
            "test_health"|"health")
                test_health
                ;;
            "create_client_group"|"create")
                create_client_group $args
                ;;
            "get_client_group"|"get")
                get_client_group $args
                ;;
            "run_client_group"|"start")
                run_client_group $args
                ;;
            "list_client_groups"|"list")
                list_client_groups
                ;;
            "show_config"|"config")
                show_config
                ;;
            "clear")
                clear
                print_banner
                print_info "Shell cleared. Type 'help' for available commands."
                ;;
            "")
                # Empty command, just continue
                ;;
            *)
                print_error "Unknown command: $command"
                print_info "Type 'help' to see available commands"
                ;;
        esac
    done
}

# Call the interactive shell function
start_interactive_shell
SCRIPT_EOF

# Make the temporary script executable
chmod +x "$TEMP_SCRIPT"

if [ "$LOCAL_MODE" = "true" ]; then
    # Run locally for testing
    echo "🔄 Running shell locally..."
    echo "📝 Temporary script created: $TEMP_SCRIPT"
    echo "⚡ Starting interactive session on login node (test mode)..."
    echo ""
    
    bash "$TEMP_SCRIPT"
else
    # Submit interactive job using srun to actually run on the compute node
    echo "🔄 Submitting job to Slurm scheduler..."
    echo "📝 Temporary script created in home directory: $TEMP_SCRIPT"
    echo "⚡ Starting interactive session on compute node..."
    echo "💡 Note: Using shared filesystem (home directory) for script access"
    echo ""

    # Use the script from shared filesystem (home directory is accessible from compute nodes)
    srun \
        --account=p200981 \
        --qos=default \
        --time=02:00:00 \
        --nodes=1 \
        --ntasks-per-node=1 \
        --cpus-per-task=4 \
        --mem=8GB \
        --job-name="ai-factory-shell" \
        --pty \
        bash "$TEMP_SCRIPT"
fi

# Clean up temporary script when session ends
echo ""
echo "🧹 Cleaning up temporary files..."
rm -f "$TEMP_SCRIPT"
echo "✅ Session ended. Temporary script removed from home directory."