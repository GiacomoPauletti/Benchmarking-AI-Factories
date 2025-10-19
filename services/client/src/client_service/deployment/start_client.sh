#!/bin/bash -l
# =============================================================================
# Client Process Launcher (Minimal)
# =============================================================================
# Description: Launches individual AI Factory Client Process (Internal Use)
# Usage: ./start_client.sh <num_clients> <server_addr> <client_service_addr> <benchmark_id>
# Note: This is a minimal version for internal use - no interactive output
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
CLIENT_SERVICE_ADDR="$3"
BENCHMARK_ID="$4"


# Check if we're in the correct directory
[ -f "client/main.py" ] || exit 1

echo "In correct directory"

# Check if Python 3 is available (silent)
command -v python3 >/dev/null 2>&1 || exit 1
echo "Python3 found: $(python3 --version)"

# Check if required Python packages are available (silent)
if ! python3 -c "import fastapi, uvicorn, requests" >/dev/null 2>&1; then
    echo "Error: required Python packages (fastapi, uvicorn, requests) are missing or failed to import." >&2
    exit 1
fi
echo "Required Python packages are available"

# Start the client process (redirect stderr to avoid startup messages if needed)
exec python3 -m client.main "$NUM_CLIENTS" "$SERVER_ADDR" "$CLIENT_SERVICE_ADDR" "$BENCHMARK_ID"

echo "Client process started successfully."