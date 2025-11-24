#!/usr/bin/env python3
"""
Simple Client Service Example: Basic Benchmark Workflow

This script demonstrates the basic client service workflow:
1. Connect to the client service
2. Create a client group for benchmarking
3. Check the status until clients are ready
4. Trigger the benchmark execution
5. Monitor progress and retrieve metrics
6. Clean up resources

Prerequisites:
- Client service running: docker compose up -d client
- SSH access to HPC cluster configured (SSH agent with keys)
- Server service running with at least one active AI service
"""

import requests
import time
import os
import sys


def check_client_service(client_url: str) -> bool:
    """Check if the client service is running and healthy."""
    try:
        # Health endpoint is at root /health, not /api/v1/health
        response = requests.get(f"{client_url}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Some health endpoints return uptime, some just status
            uptime = data.get('uptime', 0.0)
            print(f"✓ Client Service is healthy (uptime: {uptime:.1f}s)")
            return True
        return False
    except requests.RequestException as e:
        print(f"✗ Client Service is not reachable: {e}")
        return False


from typing import Optional

def create_client_group(client_url: str, num_clients: int, time_limit: int) -> Optional[int]:
    """Create a new client group for benchmarking."""
    try:
        print(f"\n[1/5] Creating client group...")
        print(f"      - Number of clients: {num_clients}")
        print(f"      - Time limit: {time_limit} minutes")
        
        # Default configuration for the example
        payload = {
            "target_url": "http://localhost:8000/v1/completions",  # Default target
            "service_id": "example-service-1",  # Required field
            "num_clients": num_clients,
            "requests_per_second": 1.0,
            "duration_seconds": 60,
            "prompts": ["Hello, world!", "What is the capital of France?"],
            "max_tokens": 50,
            "time_limit": time_limit
        }
        
        response = requests.post(
            f"{client_url}/api/v1/client-groups",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 201:
            data = response.json()
            group_id = data.get("group_id")
            print(f"✓ Client group created with ID: {group_id}")
            return group_id
        else:
            print(f"✗ Failed to create client group: {response.status_code} - {response.text}")
            return None
    except requests.RequestException as e:
        print(f"✗ Request failed: {e}")
        return None


def wait_for_completion(client_url: str, benchmark_id: int, timeout: int = 300) -> bool:
    """Wait for the benchmark job to complete."""
    print(f"\n[2/4] Waiting for benchmark to complete (timeout: {timeout}s)...")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(
                f"{client_url}/api/v1/client-groups/{benchmark_id}",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                info = data.get("info", {})
                status = info.get("status", "pending")
                
                if status != last_status:
                    print(f"      Status: {status}")
                    last_status = status
                
                if status == "stopped":
                    print(f"✓ Benchmark completed")
                    return True
                
                if status == "running":
                    # Job is running, just wait
                    pass
            
            time.sleep(5)
            
        except requests.RequestException as e:
            print(f"      Warning: {e}")
            time.sleep(10)
    
    print(f"✗ Timeout: Benchmark did not complete within {timeout}s")
    return False

def fetch_results(client_url: str, benchmark_id: int):
    """Fetch and display benchmark results."""
    print(f"\n[3/4] Fetching results...")
    
    # Sync logs to get the results file
    try:
        response = requests.post(
            f"{client_url}/api/v1/client-groups/{benchmark_id}/logs/sync",
            timeout=60
        )
        
        if response.status_code == 200:
            print(f"✓ Logs synced")
            # In a real scenario, we would read the local file.
            # But here we are running the script potentially on a different machine than the client service (if remote).
            # However, the example assumes localhost access or shared FS?
            # The sync endpoint syncs to the CLIENT SERVICE's local dir.
            # If we want to see results here, we need an endpoint to GET the results JSON.
            # The API doesn't seem to have a direct "get results" endpoint, only "get logs".
            
            # Let's try to get logs, maybe the results are printed there too?
            log_response = requests.get(f"{client_url}/api/v1/client-groups/{benchmark_id}/logs")
            if log_response.status_code == 200:
                logs = log_response.json().get("logs", "")
                print(f"\n=== Benchmark Logs ===\n{logs}\n======================")
        else:
            print(f"✗ Failed to sync logs: {response.status_code}")
            
    except requests.RequestException as e:
        print(f"✗ Error fetching results: {e}")

def cleanup_client_group(client_url: str, benchmark_id: int):
    """Delete the client group and clean up resources."""
    try:
        print(f"\n[4/4] Cleaning up client group...")
        
        response = requests.delete(
            f"{client_url}/api/v1/client-groups/{benchmark_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✓ Client group deleted")
            print(f"      Note: SLURM job may still be running. Cancel manually if needed:")
            print(f"      ssh meluxina 'scancel <job_id>'")
        else:
            print(f"      Warning: Could not delete client group: {response.status_code}")
    except requests.RequestException as e:
        print(f"      Error: {e}")


def list_all_groups(client_url: str):
    """List all active client groups."""
    try:
        response = requests.get(
            f"{client_url}/api/v1/client-groups",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            groups = data.get("groups", [])
            if groups:
                print(f"\n[*] Active client groups: {groups}")
            else:
                print(f"\n[*] No active client groups")
        else:
            print(f"\n[*] Could not list groups: {response.status_code}")
    except requests.RequestException as e:
        print(f"\n[*] Error listing groups: {e}")

def main():
    """Run the simple client service example."""
    print("=" * 70)
    print("Client Service Example: Simple Benchmark Workflow")
    print("=" * 70)
    
    # Configuration
    client_url = os.getenv("CLIENT_URL", "http://localhost:8003")
    # benchmark_id is no longer needed for creation, but we'll use a variable to store the created ID
    num_clients = int(os.getenv("NUM_CLIENTS", "10"))
    time_limit = int(os.getenv("TIME_LIMIT", "10"))  # SLURM time limit in minutes
    
    print(f"\nConfiguration:")
    print(f"  - Client Service URL: {client_url}")
    print(f"  - Number of clients: {num_clients}")
    print(f"  - Time limit: {time_limit} minutes")
    print()
    
    # Step 0: Check if client service is running
    if not check_client_service(client_url):
        print("\n[!] Please start the client service first:")
        print("    docker compose up -d client")
        sys.exit(1)
    
    # List existing groups
    list_all_groups(client_url)
    
    benchmark_id = None
    
    try:
        # Step 1: Create client group
        benchmark_id = create_client_group(client_url, num_clients, time_limit)
        if benchmark_id is None:
            sys.exit(1)
        
        # Step 2: Wait for completion
        if wait_for_completion(client_url, benchmark_id, timeout=300):
            # Step 3: Fetch results
            fetch_results(client_url, benchmark_id)
        else:
            print("\n[!] Benchmark failed or timed out.")
            # Try to get logs anyway
            fetch_results(client_url, benchmark_id)
        
        # Step 4: Cleanup
        cleanup_client_group(client_url, benchmark_id)
        
        print("\n" + "=" * 70)
        print("✓ Example completed successfully!")
        print("=" * 70)
        print("\nNext steps:")
        print("  - Check OpenAPI docs: http://localhost:8003/docs")    
    except KeyboardInterrupt:
        print("\n\n[!] Interrupted by user")
        if benchmark_id:
            cleanup_client_group(client_url, benchmark_id)
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}")
        if benchmark_id:
            cleanup_client_group(client_url, benchmark_id)
        sys.exit(1)


if __name__ == "__main__":
    main()
