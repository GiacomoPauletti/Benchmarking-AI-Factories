#!/bin/bash

# AI Factory Client Wrapper
# Automatically discovers the current server endpoint and makes API calls

# Compute endpoint file relative to this script location and fallback to HOME layout
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENDPOINT_FILE="$SCRIPT_DIR/.server-endpoint"
if [ ! -f "$ENDPOINT_FILE" ]; then
    # Fallback to common HOME-based location for legacy setups
    if [ -f "$HOME/Benchmarking-AI-Factories/services/server/.server-endpoint" ]; then
        ENDPOINT_FILE="$HOME/Benchmarking-AI-Factories/services/server/.server-endpoint"
    fi
fi

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
            "stop")
                if [ -z "$1" ]; then
                    echo "Usage: stop <service_id>"
                else
                    echo "Stopping service $1..."
                    api_call "DELETE" "/api/v1/services/$1"
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
            "vectordb"|"vector-db")
                if [ -z "$1" ]; then
                    echo "Vector DB Commands:"
                    echo "  vectordb list                                    - List running vector database services"
                    echo "  vectordb collections <service_id>                - List collections in a service"
                    echo "  vectordb info <service_id> <collection>          - Get collection info"
                    echo "  vectordb create <service_id> <collection> <size> [distance] - Create collection"
                    echo "  vectordb delete <service_id> <collection>        - Delete collection"
                    echo "  vectordb upsert <service_id> <collection> <json> - Upsert points (JSON array)"
                    echo "  vectordb search <service_id> <collection> <json> [limit] - Search similar vectors"
                    echo "Usage: vectordb <subcommand>"
                else
                    case "$1" in
                        "list")
                            api_call "GET" "/api/v1/vector-db/services"
                            ;;
                        "collections")
                            if [ -z "$2" ]; then
                                echo "Usage: vectordb collections <service_id>"
                            else
                                api_call "GET" "/api/v1/vector-db/$2/collections"
                            fi
                            ;;
                        "info")
                            if [ -z "$2" ] || [ -z "$3" ]; then
                                echo "Usage: vectordb info <service_id> <collection_name>"
                            else
                                api_call "GET" "/api/v1/vector-db/$2/collections/$3"
                            fi
                            ;;
                        "create")
                            if [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]; then
                                echo "Usage: vectordb create <service_id> <collection_name> <vector_size> [distance]"
                                echo "Example: vectordb create 12345 my_docs 384 Cosine"
                            else
                                distance="${5:-Cosine}"
                                payload="{\"vector_size\": $4, \"distance\": \"$distance\"}"
                                api_call "PUT" "/api/v1/vector-db/$2/collections/$3" "$payload"
                            fi
                            ;;
                        "delete")
                            if [ -z "$2" ] || [ -z "$3" ]; then
                                echo "Usage: vectordb delete <service_id> <collection_name>"
                            else
                                echo "Deleting collection $3 from service $2..."
                                api_call "DELETE" "/api/v1/vector-db/$2/collections/$3"
                            fi
                            ;;
                        "upsert")
                            if [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]; then
                                echo "Usage: vectordb upsert <service_id> <collection_name> <points_json>"
                                echo "Example: vectordb upsert 12345 my_docs '[{\"id\":1,\"vector\":[0.1,0.2],\"payload\":{\"text\":\"hello\"}}]'"
                            else
                                service_id="$2"
                                collection="$3"
                                # Reconstruct JSON from all remaining arguments (handles space-split JSON)
                                shift 3  # Remove first 3 args (vectordb, upsert, service_id)
                                json_data=""
                                for arg in "$@"; do
                                    json_data="$json_data$arg"
                                done
                                # Remove surrounding single quotes if present
                                json_data="${json_data#\'}"
                                json_data="${json_data%\'}"
                                # Build the payload JSON (json_data is already a JSON array, don't quote it)
                                payload='{"points": '"$json_data"'}'
                                api_call "PUT" "/api/v1/vector-db/$service_id/collections/$collection/points" "$payload"
                            fi
                            ;;
                        "search")
                            if [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]; then
                                echo "Usage: vectordb search <service_id> <collection_name> <query_vector_json> [limit]"
                                echo "Example: vectordb search 12345 my_docs '[0.1,0.2,0.3]' 5"
                            else
                                service_id="$2"
                                collection="$3"
                                # Reconstruct query vector from potentially split arguments
                                shift 3  # Remove first 3 args
                                json_data=""
                                for arg in "$@"; do
                                    if [[ "$arg" =~ ^[0-9]+$ ]]; then
                                        # This is the limit parameter
                                        limit="$arg"
                                        break
                                    else
                                        json_data="$json_data$arg"
                                    fi
                                done
                                # Remove surrounding single quotes if present
                                json_data="${json_data#\'}"
                                json_data="${json_data%\'}"
                                limit="${limit:-10}"
                                # Build the payload JSON (json_data is already a JSON array, don't quote it)
                                payload='{"query_vector": '"$json_data"', "limit": '"$limit"'}'
                                api_call "POST" "/api/v1/vector-db/$service_id/collections/$collection/points/search" "$payload"
                            fi
                            ;;
                        *)
                            echo "Unknown Vector DB command: $1"
                            echo "Available: list, collections, info, create, delete, upsert, search"
                            ;;
                    esac
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
                        "available-models")
                            # Query server for vLLM architecture info / examples
                            api_call "GET" "/api/v1/vllm/available-models"
                            ;;
                        "search-models")
                            # Usage: vllm search-models [query] [architecture] [limit]
                            # Build URL with optional query parameters (skip empty strings)
                            url="/api/v1/vllm/search-models"
                            params=""
                            if [ -n "$2" ] && [ "$2" != '""' ] && [ "$2" != "''" ]; then
                                params="${params}query=$2"
                            fi
                            if [ -n "$3" ] && [ "$3" != '""' ] && [ "$3" != "''" ]; then
                                [ -n "$params" ] && params="${params}&"
                                params="${params}architecture=$3"
                            fi
                            if [ -n "$4" ] && [ "$4" != '""' ] && [ "$4" != "''" ]; then
                                [ -n "$params" ] && params="${params}&"
                                params="${params}limit=$4"
                            fi
                            if [ -n "$params" ]; then
                                url="${url}?${params}"
                            fi
                            api_call "GET" "$url"
                            ;;
                        "model-info")
                            if [ -z "$2" ]; then
                                echo "Usage: vllm model-info <model_id>"
                            else
                                # model id may contain slashes, pass as path
                                api_call "GET" "/api/v1/vllm/model-info/$2"
                            fi
                            ;;
                        "models")
                            if [ -z "$2" ]; then
                                echo "Usage: vllm models <service_id>"
                                echo "Example: vllm models 12345"
                            else
                                service_id="$2"
                                api_call "GET" "/api/v1/vllm/$service_id/models"
                            fi
                            ;;
                        "prompt")
                            # Support optional --model=<model> flag before service id or after
                            model_arg=""
                            # If first arg looks like --model=..., consume it
                            if [[ "$2" == --model=* ]]; then
                                model_arg="${2#--model=}"
                                shift
                            fi
                            if [ -z "$2" ] || [ -z "$3" ]; then
                                echo "Usage: vllm prompt [--model=<model>] <service_id> <prompt>"
                                echo "Example: vllm prompt --model=gpt2 12345 'Hello'"
                            else
                                service_id="$2"
                                shift 2
                                prompt="$*"
                                if [ -n "$model_arg" ]; then
                                    payload="{\"prompt\": \"$prompt\", \"model\": \"$model_arg\"}"
                                else
                                    payload="{\"prompt\": \"$prompt\"}"
                                fi
                                echo "Sending prompt to VLLM service $service_id: \"$prompt\""$( [ -n "$model_arg" ] && echo " (model=$model_arg)")
                                api_call "POST" "/api/v1/vllm/$service_id/prompt" "$payload"
                            fi
                            ;;
                        *)
                            echo "Unknown VLLM command: $1"
                            echo "Available: list, models, prompt"
                            ;;
                    esac
                fi
                ;;
            "prompt")
                # Shorthand for vllm prompt. Supports optional --model=<model> before or after service id.
                model_arg=""
                # If first arg is --model=..., consume it
                if [[ "$1" == --model=* ]]; then
                    model_arg="${1#--model=}"
                    shift
                fi
                if [ -z "$1" ] || [ -z "$2" ]; then
                    echo "Usage: prompt [--model=<model>] <service_id> <prompt>"
                    echo "Example: prompt --model=gpt2 12345 'Hello, how are you?'"
                    echo "Note: This is a shorthand for 'vllm prompt'"
                else
                    service_id="$1"
                    shift
                    # If now-first arg is --model=... (user placed it after service id), consume it
                    if [[ "$1" == --model=* ]]; then
                        model_arg="${1#--model=}"
                        shift
                    fi
                    prompt="$*"
                    if [ -n "$model_arg" ]; then
                        payload="{\"prompt\": \"$prompt\", \"model\": \"$model_arg\"}"
                    else
                        payload="{\"prompt\": \"$prompt\"}"
                    fi
                    echo "Sending prompt to VLLM service $service_id: \"$prompt\""$( [ -n "$model_arg" ] && echo " (model=$model_arg)")
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
                echo "  stop <id>           - Stop a running service"
                echo "  delete <id>         - Delete a service (with confirmation)"
                echo "  vllm list           - List running VLLM services"
                echo "  vllm prompt <id> <prompt> - Send prompt to VLLM service"
                echo "  prompt <id> <prompt> - Shorthand for vllm prompt"
                echo ""
                echo "Vector DB commands:"
                echo "  vectordb list                           - List running vector DB services"
                echo "  vectordb collections <id>               - List collections in service"
                echo "  vectordb info <id> <collection>         - Get collection info"
                echo "  vectordb create <id> <coll> <size> [dist] - Create collection"
                echo "  vectordb delete <id> <collection>       - Delete collection"
                echo "  vectordb upsert <id> <coll> <json>      - Insert/update points"
                echo "  vectordb search <id> <coll> <json> [lim] - Search similar vectors"
                echo ""
                echo "  endpoint            - Show current server endpoint"
                echo "  clear               - Clear screen and show status"
                echo "  help                - Show this help"
                echo "  exit                - Exit interactive mode"
                echo ""
                echo "Examples:"
                echo "  recipes"
                echo "  create inference/vllm_dummy"
                echo "  create vector-db/qdrant"
                echo "  service abc123"
                echo "  vllm list"
                echo "  vectordb list"
                echo "  vectordb collections 12345"
                echo "  vectordb create 12345 my_docs 384 Cosine"
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
    "stop")
        if [ -z "$2" ]; then
            echo "Usage: $0 stop <service_id>"
            exit 1
        fi
        echo "Stopping service $2..."
        api_call "DELETE" "/api/v1/services/$2"
        ;;
    "delete")
        if [ -z "$2" ]; then
            echo "Usage: $0 delete <service_id>"
            exit 1
        fi
        api_call "DELETE" "/api/v1/services/$2"
        ;;
    "vectordb"|"vector-db")
        case "${2}" in
            "list")
                api_call "GET" "/api/v1/vector-db/services"
                ;;
            "collections")
                if [ -z "${3}" ]; then
                    echo "Usage: $0 vectordb collections <service_id>"
                    exit 1
                fi
                api_call "GET" "/api/v1/vector-db/${3}/collections"
                ;;
            "info")
                if [ -z "${3}" ] || [ -z "${4}" ]; then
                    echo "Usage: $0 vectordb info <service_id> <collection_name>"
                    exit 1
                fi
                api_call "GET" "/api/v1/vector-db/${3}/collections/${4}"
                ;;
            "create")
                if [ -z "${3}" ] || [ -z "${4}" ] || [ -z "${5}" ]; then
                    echo "Usage: $0 vectordb create <service_id> <collection_name> <vector_size> [distance]"
                    echo "Example: $0 vectordb create 12345 my_docs 384 Cosine"
                    exit 1
                fi
                distance="${6:-Cosine}"
                payload="{\"vector_size\": ${5}, \"distance\": \"$distance\"}"
                api_call "PUT" "/api/v1/vector-db/${3}/collections/${4}" "$payload"
                ;;
            "delete")
                if [ -z "${3}" ] || [ -z "${4}" ]; then
                    echo "Usage: $0 vectordb delete <service_id> <collection_name>"
                    exit 1
                fi
                echo "Deleting collection ${4} from service ${3}..."
                api_call "DELETE" "/api/v1/vector-db/${3}/collections/${4}"
                ;;
            "upsert")
                if [ -z "${3}" ] || [ -z "${4}" ] || [ -z "${5}" ]; then
                    echo "Usage: $0 vectordb upsert <service_id> <collection_name> <points_json>"
                    echo "Example: $0 vectordb upsert 12345 my_docs '[{\"id\":1,\"vector\":[0.1,0.2],\"payload\":{\"text\":\"hello\"}}]'"
                    exit 1
                fi
                # Build the payload JSON - ${5} is already a JSON array string
                payload='{"points": '"${5}"'}'
                api_call "PUT" "/api/v1/vector-db/${3}/collections/${4}/points" "$payload"
                ;;
            "search")
                if [ -z "${3}" ] || [ -z "${4}" ] || [ -z "${5}" ]; then
                    echo "Usage: $0 vectordb search <service_id> <collection_name> <query_vector_json> [limit]"
                    echo "Example: $0 vectordb search 12345 my_docs '[0.1,0.2,0.3]' 5"
                    exit 1
                fi
                limit="${6:-10}"
                # Build the payload JSON - ${5} is already a JSON array string
                payload='{"query_vector": '"${5}"', "limit": '"$limit"'}'
                api_call "POST" "/api/v1/vector-db/${3}/collections/${4}/points/search" "$payload"
                ;;
            *)
                echo "Usage: $0 vectordb <subcommand>"
                echo "Available subcommands:"
                echo "  list                                         - List running vector database services"
                echo "  collections <service_id>                     - List collections in a service"
                echo "  info <service_id> <collection>               - Get collection info"
                echo "  create <service_id> <collection> <size> [distance] - Create collection"
                echo "  delete <service_id> <collection>             - Delete collection"
                echo "  upsert <service_id> <collection> <json>      - Upsert points (JSON array)"
                echo "  search <service_id> <collection> <json> [limit] - Search similar vectors"
                exit 1
                ;;
        esac
        ;;
    "vllm")
        case "${2}" in
            "list")
                api_call "GET" "/api/v1/vllm/services"
                ;;
            "available-models")
                api_call "GET" "/api/v1/vllm/available-models"
                ;;
            "search-models")
                # Direct usage: server-shell.sh vllm search-models "qwen" "LlamaForCausalLM" 10
                # Skip empty string parameters
                url="/api/v1/vllm/search-models"
                params=""
                if [ -n "${3}" ] && [ "${3}" != '""' ] && [ "${3}" != "''" ]; then
                    params="${params}query=${3}"
                fi
                if [ -n "${4}" ] && [ "${4}" != '""' ] && [ "${4}" != "''" ]; then
                    [ -n "$params" ] && params="${params}&"
                    params="${params}architecture=${4}"
                fi
                if [ -n "${5}" ] && [ "${5}" != '""' ] && [ "${5}" != "''" ]; then
                    [ -n "$params" ] && params="${params}&"
                    params="${params}limit=${5}"
                fi
                if [ -n "$params" ]; then
                    url="${url}?${params}"
                fi
                api_call "GET" "$url"
                ;;
            "model-info")
                if [ -z "${3}" ]; then
                    echo "Usage: $0 vllm model-info <model_id>"
                    exit 1
                fi
                api_call "GET" "/api/v1/vllm/model-info/${3}"
                ;;
            "models")
                if [ -z "${3}" ]; then
                    echo "Usage: $0 vllm models <service_id>"
                    echo "Example: $0 vllm models 12345"
                    exit 1
                fi
                service_id="${3}"
                api_call "GET" "/api/v1/vllm/$service_id/models"
                ;;
            "prompt")
                # Support optional --model= before the service id
                model_arg=""
                arg_index=3
                if [[ "${!arg_index}" == --model=* ]]; then
                    model_arg="${!arg_index#--model=}"
                    arg_index=$((arg_index+1))
                fi
                if [ -z "${!arg_index}" ] || [ -z "${!arg_index+1}" ]; then
                    echo "Usage: $0 vllm prompt [--model=<model>] <service_id> <prompt>"
                    echo "Example: $0 vllm prompt --model=gpt2 12345 'Hello'"
                    exit 1
                fi
                service_id="${!arg_index}"
                # shift to the position of prompt
                shift $((arg_index))
                prompt="$*"
                if [ -n "$model_arg" ]; then
                    payload="{\"prompt\": \"$prompt\", \"model\": \"$model_arg\"}"
                else
                    payload="{\"prompt\": \"$prompt\"}"
                fi
                echo "Sending prompt to VLLM service $service_id: \"$prompt\""$( [ -n "$model_arg" ] && echo " (model=$model_arg)")
                api_call "POST" "/api/v1/vllm/$service_id/prompt" "$payload"
                ;;
            *)
                echo "Usage: $0 vllm <subcommand>"
                echo "Available subcommands:"
                echo "  list                     - List running VLLM services"
                echo "  models <id>              - List models served by a VLLM service"
                echo "  prompt [--model=<m>] <id> <prompt> - Send prompt to VLLM service"
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
        echo "  stop <id>           - Stop a running service"
        echo "  delete <id>         - Delete a service"
        echo "  vllm list           - List running VLLM services"
        echo "  vllm prompt <id> <prompt> - Send prompt to VLLM service"
        echo "  prompt <id> <prompt> - Shorthand for vllm prompt"
        echo ""
        echo "Vector DB Commands:"
        echo "  vectordb list                               - List running vector DB services"
        echo "  vectordb collections <id>                   - List collections in service"
        echo "  vectordb info <id> <collection>             - Get collection info"
        echo "  vectordb create <id> <coll> <size> [dist]   - Create collection"
        echo "  vectordb delete <id> <collection>           - Delete collection"
        echo "  vectordb upsert <id> <coll> <json>          - Insert/update points"
        echo "  vectordb search <id> <coll> <json> [limit]  - Search similar vectors"
        echo ""
        echo "  endpoint            - Show current server endpoint"
        echo "  help                - Show this help"
        echo ""
        echo "Examples:"
        echo "  $0                  # Start interactive mode"
        echo "  $0 status"
        echo "  $0 recipes"
        echo "  $0 create inference/vllm_dummy"
        echo "  $0 create vector-db/qdrant"
        echo "  $0 service abc123"
        echo "  $0 vllm list"
        echo "  $0 vectordb list"
        echo "  $0 vectordb collections 12345"
        echo "  $0 vectordb create 12345 my_docs 384 Cosine"
        echo "  $0 vectordb upsert 12345 my_docs '[{\"id\":1,\"vector\":[0.1,0.2]}]'"
        echo "  $0 vectordb search 12345 my_docs '[0.1,0.2]' 5"
        echo "  $0 prompt 12345 'Tell me a joke'"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac