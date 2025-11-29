#!/usr/bin/env python3
"""
Simple end-to-end example demonstrating vLLM load testing.

This script:
1. Starts a vLLM inference service via the server API
2. Waits for the service to be ready
3. Creates a client group that generates load through the Server API proxy.

The client sends requests to the Server API, which proxies them to the vLLM service.

Usage:
    python examples/simple_vllm_load_test.py
"""

import os
import sys

# Ensure the repository's `examples` directory is on `sys.path` so
# `from utils.utils import ...` resolves when running this script
# directly from `examples/basic`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests
import time
import json
from typing import Optional, Dict, Any
from utils.utils import wait_for_server, wait_for_client, wait_for_service_ready

# API endpoints
SERVER_API = "http://localhost:8001/api/v1"
SERVER_BASE = "http://localhost:8001"
CLIENT_API = "http://localhost:8002/api/v1"
CLIENT_BASE = "http://localhost:8002"

def create_vllm_service() -> str:
    """Create a vLLM inference service and return its service_id."""
    print("Creating vLLM Service")
    
    # Use a small model for quick startup
    payload = {
        "recipe_name": "inference/vllm-single-node"
    }
    
    print(f"Requesting vLLM service with config:")
    print(json.dumps(payload, indent=2))
    
    response = requests.post(f"{SERVER_API}/services", json=payload)
    response.raise_for_status()
    
    service = response.json()
    service_id = service["id"]
    
    print(f"\nService created with ID: {service_id}")
    print(f"  Status: {service['status']}")
    print(f"  Recipe: {service['recipe_name']}")
    
    return service_id


def create_load_test_group(service_id: str, direct_url: str = None) -> Optional[int]:
    """Create a client group that generates load against a vLLM service.
    
    Args:
        service_id: The vLLM service ID from the server
        direct_url: Optional direct URL to the vLLM service (bypasses server proxy)
        
    Returns:
        The group ID if created successfully, None otherwise
    """
    print("Creating Load Test Client Group")
    
    # Configure a gentle load test
    payload = {
        "service_id": service_id,    # Service to test
        "num_clients": 10,  # 10 concurrent clients
        "requests_per_second": 0.2,  # Low rate: 1 request every 5 seconds
        "duration_seconds": 60,  # 1 minute test
        "prompts": [
            "Write a short poem about AI.",
            "Explain what machine learning is.",
            "Tell me a fun fact about computers.",
            "What is Python programming?"
        ],
        "max_tokens": 50,  # Short responses
        "temperature": 0.7,
        "time_limit": 10  # SLURM job time limit in minutes
    }
    
    print(f"Load test configuration:")
    print(f"  Server API: {SERVER_BASE}")
    print(f"  Service ID: {service_id}")
    print(f"  Clients: {payload['num_clients']}")
    print(f"  RPS: {payload['requests_per_second']}")
    print(f"  Duration: {payload['duration_seconds']}s")
    print(f"  Prompts: {len(payload['prompts'])} variations")
    
    try:
        response = requests.post(
            f"{CLIENT_API}/client-groups",
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        group_id = result.get('group_id')
        
        print(f"\nClient group {group_id} created successfully")
        print(f"  Message: {result.get('message', 'Load generator job submitted')}")
        return group_id
        
    except requests.RequestException as e:
        print(f"\nFailed to create client group: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  Response: {e.response.text}")
        return None


def monitor_client_group(group_id: int, duration: int = 120):
    """Monitor the client group progress.
    
    Args:
        group_id: The client group ID
        duration: Maximum time to monitor in seconds (stops early if job completes)
    """
    print("Monitoring Load Test Progress")
    print(f"Monitoring client group {group_id} for up to {duration}s")
    print("Note: Results will be written to remote logs directory")
    
    start_time = time.time()
    
    while time.time() - start_time < duration:
        try:
            response = requests.get(f"{CLIENT_API}/client-groups/{group_id}")
            response.raise_for_status()
            
            group_info = response.json()
            status = group_info.get('info', {}).get('status', 'unknown')
            job_id = group_info.get('info', {}).get('job_id', 'N/A')
            elapsed = int(time.time() - start_time)
            
            print(f"  [{elapsed}s] Status: {status}, Job ID: {job_id}")
            
            # Stop monitoring if the job has completed
            if status == 'stopped':
                print(f"\nLoad test completed after {elapsed}s")
                break
            
        except requests.RequestException as e:
            print(f"  Error querying group: {e}")
        
        time.sleep(15)
    else:
        # Timeout reached without completion
        print(f"\nMonitoring timeout reached after {duration}s")
    
    print(f"\nCheck logs for detailed results (loadgen-{group_id}).")


def cleanup_service(service_id: str):
    """Stop a running vLLM service.
    
    Args:
        service_id: The service ID to stop
    """
    print(f"\nStopping service {service_id}...")
    try:
        response = requests.post(
            f"{SERVER_API}/services/{service_id}/status",
            json={"status": "cancelled"}
        )
        response.raise_for_status()
        print(f"Service {service_id} stopped successfully")
    except requests.RequestException as e:
        print(f"Failed to stop service: {e}")


def main():
    """Run the complete end-to-end example."""
    print("vLLM Load Testing Example")
    print("This example demonstrates:")
    print("  1. Starting a vLLM inference service")
    print("  2. Waiting for the service to be ready")
    print("  3. Running a load test against the service")
    print()
    
    service_id = None
    group_id = None
    
    try:
        # Step 0: Wait for services to be ready
        print("=" * 80)
        print("Checking service availability...")
        print("=" * 80)
        
        if not wait_for_server(SERVER_BASE, max_wait=30):
            print("Server service not available. Is it running?")
            print("  Start with: docker compose up server")
            return
        
        if not wait_for_client(CLIENT_BASE, max_wait=30):
            print("Client service not available. Is it running?")
            print("  Start with: docker compose up client")
            return
        
        print()
        
        # Step 1: Create vLLM service
        print("STEP 1: Creating vLLM Service")
        service_id = create_vllm_service()
        print()
        
        # Step 2: Wait for service to be ready
        print("STEP 2: Waiting for vLLM Service")
        endpoint = wait_for_service_ready(SERVER_BASE, service_id, max_wait=3000)
        
        if not endpoint:
            print("\nFailed to get service endpoint. Aborting.")
            return
        
        print()
        
        # Step 3: Create load test group (returns auto-generated group_id)
        print("STEP 3: Creating Load Test Group")
        # Pass the direct endpoint to the load generator
        group_id = create_load_test_group(service_id, direct_url=endpoint)
        
        if not group_id:
            print("\nFailed to create load test group. Aborting.")
            return
        
        print()
        
        # Step 4: Monitor progress
        print("STEP 4: Monitoring Load Test")
        monitor_client_group(group_id, duration=300)
        
        print()
        print("SUCCESS: Load Test Complete!")
        print(f"Service ID: {service_id}")
        print(f"Client Group ID: {group_id}")
        print(f"Endpoint: {endpoint}")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if service_id:
            response = input(f"\nStop service {service_id}? [y/N]: ")
            if response.lower() == 'y':
                cleanup_service(service_id)
            else:
                print(f"Service {service_id} left running. Stop it manually when done:")
                print(f"  curl -X POST {SERVER_API}/services/{service_id}/status -H 'Content-Type: application/json' -d '{{\"status\": \"cancelled\"}}'")


if __name__ == "__main__":
    main()