#!/bin/bash -l
# =============================================================================
# Client Process Launcher (Minimal)
# =============================================================================
# Description: Launches individual AI Factory Client Process (Internal Use)
# Usage: ./start_client.sh <num_clients> <server_addr> <benchmark_id> [--container] [--signal-file path]
# Note: This is a minimal version for internal use - no interactive output
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_MODE=false
CONTAINER_IMAGE="client_container.sif"
SIGNAL_FILE=""

# Parse optional flags
shift 3  # Skip the first 3 required arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --container)
            CONTAINER_MODE=true
            echo "Container mode enabled"
            shift
            ;;
        --signal-file)
            SIGNAL_FILE="$2"
            echo "Signal file: $SIGNAL_FILE"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            shift
            ;;
    esac
done

# Basic validation function (silent)
# validate_args() {
#     # Check argument count
#     [ $# -eq 4 ] || return 1
#     echo "Args count ok"
#     # Check if num_clients is a positive integer
#     [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -gt 0 ] || return 1
#     echo "Num clients ok"
#     # Check URL formats
#     [[ "$2" =~ ^https?:// ]] || return 1
#     [[ "$3" =~ ^https?:// ]] || return 1
#     echo "URLs ok"
#     # Check if benchmark_id is a positive integer
#     [[ "$4" =~ ^[0-9]+$ ]] && [ "$4" -gt 0 ] || return 1
#     echo "Benchmark ID ok"
#     return 0
# }

# Validate arguments (exit silently on error)
#validate_args "$@" || echo "Error... now exiting 0" && exit 1

NUM_CLIENTS="$1"
SERVER_ADDR="$2"
BENCHMARK_ID="$3"


# Check if we're in the correct directory or if container image exists
if [ "$CONTAINER_MODE" = "true" ]; then
    # Check if container image exists in client directory
    CLIENT_DIR="$SCRIPT_DIR/../../client"
    if [ ! -f "$CLIENT_DIR/$CONTAINER_IMAGE" ]; then
        echo "Error: Container image '$CONTAINER_IMAGE' not found in $CLIENT_DIR" >&2
        echo "Please build the container first with: cd $CLIENT_DIR && ./build_client_container.sh" >&2
        exit 1
    fi
    echo "Container mode: using $CLIENT_DIR/$CONTAINER_IMAGE"
else
    # Check if we're in the correct directory for native execution
    [ -f "client/main.py" ] || exit 1
    echo "Native mode: found client/main.py"
fi

# Check Python dependencies based on execution mode
if [ "$CONTAINER_MODE" = "false" ]; then
    # Check if Python 3 is available (silent)
    command -v python3 >/dev/null 2>&1 || exit 1
    echo "Python3 found: $(python3 --version)"

    # Check if required Python packages are available (silent)
    if ! python3 -c "import fastapi, uvicorn, requests" >/dev/null 2>&1; then
        echo "Error: required Python packages (fastapi, uvicorn, requests) are missing or failed to import." >&2
        exit 1
    fi
    echo "Required Python packages are available"
else
    # Check if Apptainer is available (load modules if needed)
    if command -v module >/dev/null 2>&1; then
        module load env/release/2023.1 >/dev/null 2>&1
        module load Apptainer/1.2.4-GCCcore-12.3.0 >/dev/null 2>&1 || {
            echo "Error: Apptainer module not available" >&2
            exit 1
        }
    fi
    
    if ! command -v apptainer >/dev/null 2>&1; then
        echo "Error: Apptainer not found in PATH" >&2
        exit 1
    fi
    echo "Container mode: Apptainer available"
fi

# Start the client process
export CLIENT_SIGNAL_FILE="$SIGNAL_FILE"  # Export for client process to use

if [ "$CONTAINER_MODE" = "true" ]; then
    # Start with container
    CLIENT_DIR="$SCRIPT_DIR/../../client"
    echo "Starting client container with: $NUM_CLIENTS $SERVER_ADDR $BENCHMARK_ID"
    exec apptainer run \
        --bind /home/users/${USER}:/home/users/${USER} \
        --env CLIENT_SIGNAL_FILE="$SIGNAL_FILE" \
        --env REMOTE_BASE_PATH="${REMOTE_BASE_PATH}" \
        "$CLIENT_DIR/$CONTAINER_IMAGE" "$NUM_CLIENTS" "$SERVER_ADDR" "$BENCHMARK_ID"
else
    # Start native process (redirect stderr to avoid startup messages if needed)
    echo "Starting native client with: $NUM_CLIENTS $SERVER_ADDR $BENCHMARK_ID"
    exec python3 -m client.main "$NUM_CLIENTS" "$SERVER_ADDR" "$BENCHMARK_ID"
fi