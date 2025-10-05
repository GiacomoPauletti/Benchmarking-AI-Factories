#!/bin/bash

# Smart API Testing using the AI Factory Client
# Automatically discovers the current server endpoint

CLIENT="./ai-factory-client.sh"

echo "=================================="
echo "AI Factory Server API Test"
echo "Using Smart Client Discovery"
echo "=================================="
echo

# 1. Check server status
echo "1. Checking Server Status..."
echo "-----------------------------"
$CLIENT status
echo

# 2. Test health endpoint
echo "2. Testing Health Endpoint..."
echo "------------------------------"
$CLIENT health
echo

# 3. List available recipes
echo "3. Listing Available Recipes..."
echo "-------------------------------"
$CLIENT recipes
echo

# 4. Get specific recipe details
echo "4. Getting vLLM Recipe Details..."
echo "--------------------------------"
$CLIENT recipe inference/vllm_dummy
echo

# 5. List current services
echo "5. Listing Current Services..."
echo "-----------------------------"
$CLIENT services
echo

# 6. Create a simple test service
echo "6. Creating Test Service (vLLM dummy)..."
echo "---------------------------------------"
response=$($CLIENT create inference/vllm_dummy)
echo "$response"

# Extract service ID if creation was successful
SERVICE_ID=$(echo "$response" | python3 -c "
import sys, json
try:
    for line in sys.stdin:
        if line.strip().startswith('{'):
            data = json.loads(line.strip())
            print(data.get('service_id', ''))
            break
except:
    pass
" 2>/dev/null)

echo
if [ -n "$SERVICE_ID" ]; then
    echo "Service created with ID: $SERVICE_ID"
    echo
    
    # 7. Check service status
    echo "7. Checking Service Status..."
    echo "----------------------------"
    $CLIENT service $SERVICE_ID
    echo
    
    # 8. Wait a bit and check logs
    echo "8. Getting Service Logs..."
    echo "-------------------------"
    sleep 5
    $CLIENT logs $SERVICE_ID
    echo
    
else
    echo "No service ID returned - service creation may have failed"
fi

echo "=================================="
echo "API Test Complete"
echo "Usage: ./ai-factory-client.sh help"
echo "=================================="