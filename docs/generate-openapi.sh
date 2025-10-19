#!/bin/bash
# Generate OpenAPI schemas for all microservices using Docker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS_DIR="$SCRIPT_DIR"
API_DIR="$DOCS_DIR/api"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$API_DIR"

echo "Generating OpenAPI schemas..."

# Server service - launch with docker compose and fetch from API
echo "  - Server service..."
cd "$PROJECT_ROOT"

# Check if server is already running
if docker compose ps server 2>/dev/null | grep -q "Up"; then
    echo "    Server already running"
    SERVER_WAS_RUNNING=true
else
    echo "    Starting server with docker compose..."
    docker compose up -d server
    SERVER_WAS_RUNNING=false
    
    # Wait for server to be ready
    echo "    Waiting for server to be ready..."
    MAX_ATTEMPTS=30
    ATTEMPT=0
    while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
        if curl -s http://localhost:8001/health > /dev/null 2>&1; then
            echo "    Server is ready"
            break
        fi
        ATTEMPT=$((ATTEMPT + 1))
        sleep 1
    done
    
    if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
        echo "    Warning: Server did not become ready in time"
        exit 1
    fi
fi

# Fetch OpenAPI schema
echo "    Fetching OpenAPI schema..."
if curl -s http://localhost:8001/openapi.json > "$API_DIR/server-openapi.json"; then
    echo "    Successfully generated server-openapi.json"
else
    echo "    Warning: Could not fetch OpenAPI schema"
fi

# Stop server if we started it
if [ "$SERVER_WAS_RUNNING" = false ]; then
    echo "    Stopping server..."
    docker compose down server
fi

# Client service (TODO)
echo "  - Client service... (TODO)"
echo '{"info": {"title": "Client Service", "version": "1.0.0"}, "paths": {}}' > "$API_DIR/client-openapi.json"

# Monitoring service (TODO)
echo "  - Monitoring service... (TODO)"
echo '{"info": {"title": "Monitoring Service", "version": "1.0.0"}, "paths": {}}' > "$API_DIR/monitor-openapi.json"

# Logs service (TODO)
echo "  - Logs service... (TODO)"
echo '{"info": {"title": "Logs Service", "version": "1.0.0"}, "paths": {}}' > "$API_DIR/logs-openapi.json"

cd "$DOCS_DIR"
echo "Done! OpenAPI schemas generated in $API_DIR"

