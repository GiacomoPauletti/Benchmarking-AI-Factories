#!/bin/bash

# AI Factory Client Wrapper
# Automatically discovers the current server endpoint and makes API calls

# Check if server endpoint file exists
ENDPOINT_FILE="/home/users/u103056/Benchmarking-AI-Factories/services/server/.server-endpoint"

# Function to get current server endpoint
get_server_endpoint() {
    if [ -f "$ENDPOINT_FILE" ]; then
        cat "$ENDPOINT_FILE"
    else
        echo ""
    fi
}

# Function to check if server is reachable
check_server() {
    local endpoint=$(get_server_endpoint)
    if [ -z "$endpoint" ]; then
        echo "No server endpoint found. Is the server running?"
        echo "   Start server with: ./services/server/launch_server.sh"
        return 1
    fi
    
    # Test health endpoint
    if curl -s "${endpoint}/health" >/dev/null 2>&1; then
        echo "Server is running at: $endpoint"
        return 0
    else
        echo "Server endpoint found but not responding: $endpoint"
        echo "   The server may have stopped. Try restarting with: ./services/server/launch_server.sh"
        return 1
    fi
}

# Function to make API calls
api_call() {
    local method=${1:-GET}
    local path=${2:-/health}
    local data=${3:-}
    
    local endpoint=$(get_server_endpoint)
    if [ -z "$endpoint" ]; then
        echo "No server endpoint found. Start server with: ./services/server/launch_server.sh"
        return 1
    fi
    
    local url="${endpoint}${path}"
    echo "Making $method request to: $url"
    
    if [ -n "$data" ]; then
        curl -s -X "$method" "$url" \
            -H "Content-Type: application/json" \
            -d "$data" | python3 -m json.tool 2>/dev/null || echo "Failed to parse JSON response"
    else
        curl -s -X "$method" "$url" | python3 -m json.tool 2>/dev/null || echo "Failed to parse JSON response"
    fi
}

# Interactive mode function
interactive_mode() {
    echo "AI Factory Interactive Client"
    echo "============================="
    
    # Check server status on startup
    check_server
    echo
    echo "Type 'help' for available commands, 'exit' to quit"
    echo
    
    while true; do
        # Show prompt with current endpoint status
        local endpoint=$(get_server_endpoint)
        if [ -n "$endpoint" ]; then
            echo -n "ai-factory [$(echo $endpoint | cut -d'/' -f3)]> "
        else
            echo -n "ai-factory [no server]> "
        fi
        
        # Read user input
        read -r input || break
        
        # Handle empty input
        if [ -z "$input" ]; then
            continue
        fi
        
        # Parse command and arguments
        set -- $input
        local cmd="$1"
        shift
        
        case "$cmd" in
            "exit"|"quit"|"q")
                break
                ;;
            "clear"|"cls")
                clear
                echo "AI Factory Interactive Client"
                echo "============================="
                check_server
                echo
                ;;
            "status")
                check_server
                ;;
            "health")
                api_call "GET" "/health"
                ;;
            "recipes")
                api_call "GET" "/api/v1/recipes"
                ;;
            "services")
                api_call "GET" "/api/v1/services"
                ;;
            "recipe")
                if [ -z "$1" ]; then
                    echo "Usage: recipe <recipe_path>"
                    echo "Example: recipe inference/vllm"
                else
                    api_call "GET" "/api/v1/recipes/$1"
                fi
                ;;
            "create")
                if [ -z "$1" ]; then
                    echo "Usage: create <recipe_name> [additional_params]"
                    echo "Example: create inference/vllm_dummy"
                else
                    recipe_name="$1"
                    payload="{\"recipe_name\": \"$recipe_name\", \"nodes\": 1, \"cpus\": 2, \"memory\": \"4G\", \"time\": \"00:30:00\"}"
                    api_call "POST" "/api/v1/services" "$payload"
                fi
                ;;
            "service")
                if [ -z "$1" ]; then
                    echo "Usage: service <service_id>"
                else
                    api_call "GET" "/api/v1/services/$1"
                fi
                ;;
            "logs")
                if [ -z "$1" ]; then
                    echo "Usage: logs <service_id>"
                else
                    api_call "GET" "/api/v1/services/$1/logs"
                fi
                ;;
            "delete")
                if [ -z "$1" ]; then
                    echo "Usage: delete <service_id>"
                else
                    echo "Are you sure you want to delete service $1? (y/N)"
                    read -r confirm
                    if [[ $confirm =~ ^[Yy]$ ]]; then
                        api_call "DELETE" "/api/v1/services/$1"
                    else
                        echo "Delete cancelled"
                    fi
                fi
                ;;
            "vllm")
                if [ -z "$1" ]; then
                    echo "VLLM Commands:"
                    echo "  vllm list           - List running VLLM services"
                    echo "  vllm prompt <id> <prompt>  - Send prompt to VLLM service"
                    echo "Usage: vllm <subcommand>"
                else
                    case "$1" in
                        "list")
                            api_call "GET" "/api/v1/vllm/services"
                            ;;
                        "prompt")
                            if [ -z "$2" ] || [ -z "$3" ]; then
                                echo "Usage: vllm prompt <service_id> <prompt>"
                                echo "Example: vllm prompt 12345 'Hello, how are you?'"
                            else
                                service_id="$2"
                                shift 2
                                prompt="$*"
                                payload="{\"prompt\": \"$prompt\"}"
                                echo "Sending prompt to VLLM service $service_id: \"$prompt\""
                                api_call "POST" "/api/v1/vllm/$service_id/prompt" "$payload"
                            fi
                            ;;
                        *)
                            echo "Unknown VLLM command: $1"
                            echo "Available: list, prompt"
                            ;;
                    esac
                fi
                ;;
            "prompt")
                # Shorthand for vllm prompt
                if [ -z "$1" ] || [ -z "$2" ]; then
                    echo "Usage: prompt <service_id> <prompt>"
                    echo "Example: prompt 12345 'Hello, how are you?'"
                    echo "Note: This is a shorthand for 'vllm prompt'"
                else
                    service_id="$1"
                    shift
                    prompt="$*"
                    payload="{\"prompt\": \"$prompt\"}"
                    echo "Sending prompt to VLLM service $service_id: \"$prompt\""
                    api_call "POST" "/api/v1/vllm/$service_id/prompt" "$payload"
                fi
                ;;
            "endpoint")
                local endpoint=$(get_server_endpoint)
                if [ -n "$endpoint" ]; then
                    echo "Current server endpoint: $endpoint"
                else
                    echo "No server endpoint found"
                fi
                ;;
            "help"|"h")
                echo "Available commands:"
                echo "  status              - Check if server is running"
                echo "  health              - Get server health"
                echo "  recipes             - List all recipes"
                echo "  recipe <path>       - Get specific recipe details"
                echo "  services            - List all services"
                echo "  create <recipe>     - Create a service"
                echo "  service <id>        - Get service status"
                echo "  logs <id>           - Get service logs"
                echo "  delete <id>         - Delete a service"
                echo "  vllm list           - List running VLLM services"
                echo "  vllm prompt <id> <prompt> - Send prompt to VLLM service"
                echo "  prompt <id> <prompt> - Shorthand for vllm prompt"
                echo "  endpoint            - Show current server endpoint"
                echo "  clear               - Clear screen and show status"
                echo "  help                - Show this help"
                echo "  exit                - Exit interactive mode"
                echo ""
                echo "Examples:"
                echo "  recipes"
                echo "  create inference/vllm_dummy"
                echo "  service abc123"
                echo "  vllm list"
                echo "  prompt 12345 'Tell me a joke'"
                ;;
            *)
                echo "Unknown command: $cmd"
                echo "Type 'help' for available commands"
                ;;
        esac
        echo
    done
}

# Command-line interface
if [ $# -eq 0 ]; then
    # No arguments provided - start interactive mode
    interactive_mode
    exit 0
fi

case "${1}" in
    "status")
        check_server
        ;;
    "health")
        api_call "GET" "/health"
        ;;
    "recipes")
        api_call "GET" "/api/v1/recipes"
        ;;
    "services")
        api_call "GET" "/api/v1/services"
        ;;
    "recipe")
        if [ -z "$2" ]; then
            echo "Usage: $0 recipe <recipe_path>"
            echo "Example: $0 recipe inference/vllm"
            exit 1
        fi
        api_call "GET" "/api/v1/recipes/$2"
        ;;
    "create")
        if [ -z "$2" ]; then
            echo "Usage: $0 create <recipe_name> [additional_params]"
            echo "Example: $0 create inference/vllm_dummy"
            exit 1
        fi
        recipe_name="$2"
        # Basic service creation payload
        payload="{\"recipe_name\": \"$recipe_name\", \"nodes\": 1, \"cpus\": 2, \"memory\": \"4G\", \"time\": \"00:30:00\"}"
        api_call "POST" "/api/v1/services" "$payload"
        ;;
    "service")
        if [ -z "$2" ]; then
            echo "Usage: $0 service <service_id>"
            exit 1
        fi
        api_call "GET" "/api/v1/services/$2"
        ;;
    "logs")
        if [ -z "$2" ]; then
            echo "Usage: $0 logs <service_id>"
            exit 1
        fi
        api_call "GET" "/api/v1/services/$2/logs"
        ;;
    "delete")
        if [ -z "$2" ]; then
            echo "Usage: $0 delete <service_id>"
            exit 1
        fi
        api_call "DELETE" "/api/v1/services/$2"
        ;;
    "vllm")
        case "${2}" in
            "list")
                api_call "GET" "/api/v1/vllm/services"
                ;;
            "prompt")
                if [ -z "$3" ] || [ -z "$4" ]; then
                    echo "Usage: $0 vllm prompt <service_id> <prompt>"
                    echo "Example: $0 vllm prompt 12345 'Hello, how are you?'"
                    exit 1
                fi
                service_id="$3"
                shift 3
                prompt="$*"
                payload="{\"prompt\": \"$prompt\"}"
                echo "Sending prompt to VLLM service $service_id: \"$prompt\""
                api_call "POST" "/api/v1/vllm/$service_id/prompt" "$payload"
                ;;
            *)
                echo "Usage: $0 vllm <subcommand>"
                echo "Available subcommands:"
                echo "  list                     - List running VLLM services"
                echo "  prompt <id> <prompt>     - Send prompt to VLLM service"
                exit 1
                ;;
        esac
        ;;
    "prompt")
        # Shorthand for vllm prompt
        if [ -z "$2" ] || [ -z "$3" ]; then
            echo "Usage: $0 prompt <service_id> <prompt>"
            echo "Example: $0 prompt 12345 'Hello, how are you?'"
            echo "Note: This is a shorthand for 'vllm prompt'"
            exit 1
        fi
        service_id="$2"
        shift 2
        prompt="$*"
        payload="{\"prompt\": \"$prompt\"}"
        echo "Sending prompt to VLLM service $service_id: \"$prompt\""
        api_call "POST" "/api/v1/vllm/$service_id/prompt" "$payload"
        ;;
    "endpoint")
        local endpoint=$(get_server_endpoint)
        if [ -n "$endpoint" ]; then
            echo "Current server endpoint: $endpoint"
        else
            echo "No server endpoint found"
        fi
        ;;
    "help"|"-h"|"--help")
        echo "AI Factory Client - Smart API wrapper"
        echo ""
        echo "Usage: $0 [command] [args]"
        echo ""
        echo "Interactive Mode:"
        echo "  $0                  - Start interactive client"
        echo ""
        echo "Direct Commands:"
        echo "  status              - Check if server is running"
        echo "  health              - Get server health"
        echo "  recipes             - List all recipes"
        echo "  recipe <path>       - Get specific recipe details"
        echo "  services            - List all services"
        echo "  create <recipe>     - Create a service"
        echo "  service <id>        - Get service status"
        echo "  logs <id>           - Get service logs"
        echo "  delete <id>         - Delete a service"
        echo "  vllm list           - List running VLLM services"
        echo "  vllm prompt <id> <prompt> - Send prompt to VLLM service"
        echo "  prompt <id> <prompt> - Shorthand for vllm prompt"
        echo "  endpoint            - Show current server endpoint"
        echo "  help                - Show this help"
        echo ""
        echo "Examples:"
        echo "  $0                  # Start interactive mode"
        echo "  $0 status"
        echo "  $0 recipes"
        echo "  $0 create inference/vllm_dummy"
        echo "  $0 service abc123"
        echo "  $0 vllm list"
        echo "  $0 prompt 12345 'Tell me a joke'"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac