#!/usr/bin/env python3
"""
Simple end-to-end example demonstrating vLLM replica load testing via the Server API proxy.

This script:
1. Starts a vLLM replica service group through the Server API.
2. Waits for the service group to expose a routable endpoint.
3. Creates a client group whose traffic flows through the Server API proxy into the replicas.
4. Cleans up the client group and replica service group.

Usage:
    python examples/simple_vllm_replica_load_test.py
"""

import requests
import time
import json
from typing import Optional
from utils.utils import (
    wait_for_server,
    wait_for_client,
    wait_for_service_group_ready,
)

# API endpoints
SERVER_API = "http://localhost:8001/api/v1"
SERVER_BASE = "http://localhost:8001"
CLIENT_API = "http://localhost:8003/api/v1"
CLIENT_BASE = "http://localhost:8003"

def create_vllm_service_group() -> str:
    """Create a vLLM replica service group and return its group_id."""
    print("Creating vLLM Replica Group")

    payload = {
        "recipe_name": "inference/vllm-replicas"
    }

    print("Requesting vLLM replicas with config:")
    print(json.dumps(payload, indent=2))

    response = requests.post(f"{SERVER_API}/services", json=payload)
    response.raise_for_status()

    group_info = response.json()
    group_id = group_info.get("group_id") or group_info["id"]

    total_replicas = group_info.get("total_replicas")
    status = group_info.get("status")

    print(f"\nService group created with ID: {group_id}")
    if total_replicas is not None:
        print(f"  Replicas: {total_replicas}")
    if status:
        print(f"  Status: {status}")
    print(f"  Recipe: {group_info.get('recipe_name')}")

    return group_id


def create_load_test_group(service_group_id: str, direct_url: str = None) -> Optional[int]:
    """Create a client group that generates load against a vLLM service.
    
    Args:
        service_group_id: The vLLM service group ID from the server
        direct_url: Optional direct URL to the vLLM service (bypasses server proxy)
        
    Returns:
        The group ID if created successfully, None otherwise
    """
    print("Creating Load Test Client Group")
    
    # Configure a gentle load test
    payload = {
        "service_id": service_group_id,  # Target service group
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
    print(f"  Service Group ID: {service_group_id}")
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
        client_group_id = result.get('group_id')
        
        print(f"\nClient group {client_group_id} created successfully")
        print(f"  Message: {result.get('message', 'Load generator job submitted')}")
        return client_group_id
        
    except requests.RequestException as e:
        print(f"\nFailed to create client group: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  Response: {e.response.text}")
        return None


def monitor_client_group(client_group_id: int, duration: int = 120):
    """Monitor the client group progress.
    
    Args:
        client_group_id: The client group ID
        duration: Maximum time to monitor in seconds (stops early if job completes)
    """
    print("Monitoring Load Test Progress")
    print(f"Monitoring client group {client_group_id} for up to {duration}s")
    print("Note: Results will be written to remote logs directory")
    
    start_time = time.time()
    
    while time.time() - start_time < duration:
        try:
            response = requests.get(f"{CLIENT_API}/client-groups/{client_group_id}")
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
    
    print(f"\nCheck logs for detailed results (loadgen-{client_group_id}).")


def cleanup_service_group(group_id: str):
    """Stop a running vLLM service group and its replicas."""
    print(f"\nStopping service group {group_id}...")
    try:
        response = requests.delete(f"{SERVER_API}/service-groups/{group_id}")
        response.raise_for_status()
        print(f"Service group {group_id} stopped successfully")
    except requests.RequestException as e:
        print(f"Failed to stop service group: {e}")


def main():
    """Run the complete end-to-end example."""
    print("vLLM Load Testing Example")
    print("This example demonstrates:")
    print("  1. Starting a vLLM inference service")
    print("  2. Waiting for the service to be ready")
    print("  3. Running a load test against the service")
    print()
    
    service_group_id = None
    client_group_id = None
    prompt_url = None
    
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
        
        # Step 1: Create vLLM replica service group
        print("STEP 1: Creating vLLM Replica Group")
        service_group_id = create_vllm_service_group()
        print()
        
        # Step 2: Wait for replicas to become healthy
        print("STEP 2: Waiting for vLLM Replicas")
        ready = wait_for_service_group_ready(
            SERVER_BASE,
            service_group_id,
            min_healthy=1,
            timeout=600,
        )

        if not ready:
            print("\nFailed to detect healthy replicas. Aborting.")
            return

        prompt_url = f"{SERVER_API}/vllm/{service_group_id}/prompt"
        print(f"Replica prompt URL: {prompt_url}")
        
        print()
        
        # Step 3: Create load test group (returns auto-generated group ID)
        print("STEP 3: Creating Load Test Group")
        client_group_id = create_load_test_group(service_group_id)
        
        if not client_group_id:
            print("\nFailed to create load test group. Aborting.")
            return
        
        print()
        
        # Step 4: Monitor progress
        print("STEP 4: Monitoring Load Test")
        monitor_client_group(client_group_id, duration=300)
        
        print()
        print("SUCCESS: Load Test Complete!")
        print(f"Service Group ID: {service_group_id}")
        print(f"Client Group ID: {client_group_id}")
        print(f"Prompt URL: {prompt_url}")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if service_group_id:
            response = input(f"\nStop service group {service_group_id}? [y/N]: ")
            if response.lower() == 'y':
                cleanup_service_group(service_group_id)
            else:
                print(f"Service group {service_group_id} left running. Stop it manually when done:")
                print(f"  curl -X DELETE {SERVER_API}/service-groups/{service_group_id}")


if __name__ == "__main__":
    main()
