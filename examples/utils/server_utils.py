"""
Server and service utilities for waiting and checking readiness.
"""

import requests
import time
from typing import Optional


def wait_for_server(server_url: str, max_wait: int = 30) -> bool:
    """
    Wait for server to be ready by polling the health endpoint.
    
    Args:
        server_url: Base URL of the server (e.g., "http://localhost:8001")
        max_wait: Maximum time to wait in seconds
        
    Returns:
        True if server is ready, False otherwise
    """
    print(f"Waiting for server at {server_url}...")
    start = time.time()
    
    while time.time() - start < max_wait:
        try:
            response = requests.get(f"{server_url}/health", timeout=2)
            if response.status_code == 200:
                print("Server is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    
    print("Server not available")
    return False


def wait_for_service_ready(
    server_url: str, 
    service_id: str, 
    max_wait: int = 300,
    poll_interval: int = 5
) -> bool:
    """
    Wait for service to be ready by polling the status endpoint.
    
    Args:
        server_url: Base URL of the server (e.g., "http://localhost:8001")
        service_id: Service ID (SLURM job ID)
        max_wait: Maximum time to wait in seconds
        poll_interval: How often to check status in seconds (default: 5)
        
    Returns:
        True if service is ready, False otherwise
    """
    print(f"Waiting for service {service_id} to be ready...")
    print(f"  Max wait: {max_wait}s | Poll interval: {poll_interval}s")
    api_base = f"{server_url}/api/v1"
    start = time.time()
    last_status = None
    attempts = 0

    time.sleep(2)  # Initial delay before first check
    while time.time() - start < max_wait:
        attempts += 1
        elapsed = time.time() - start
        
        try:
            # Poll the status endpoint
            response = requests.get(
                f"{api_base}/services/{service_id}/status",
                timeout=10
            )
            
            if response.status_code == 200:
                status_data = response.json()
                current_status = status_data.get("status")
                
                # Print status updates
                if current_status != last_status:
                    print(f"  [{attempts}] Status: {current_status} | Elapsed: {elapsed:.1f}s")
                    last_status = current_status
                
                # Service is ready when status is "running"
                if current_status == "running":
                    print(f"[+] Service is ready! (took {elapsed:.1f}s, {attempts} checks)")
                    return True
                
                # Service failed
                if current_status in ["failed", "cancelled", "timeout"]:
                    print(f"[-] Service failed with status: {current_status}")
                    return False
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    
    print(f"[-] Service did not become ready within {max_wait}s")
    return False


def wait_for_service_group_ready(server_url: str, group_id: str, min_healthy: int = 1, 
                                  timeout: int = 600, check_interval: int = 3) -> bool:
    """Wait for at least min_healthy replicas in a service group to be ready.
    
    Uses the /service-groups/{group_id} endpoint to check group status.
    
    Args:
        server_url: Base URL of the server (e.g., "http://localhost:8001")
        group_id: The service group ID (e.g., "sg-...")
        min_healthy: Minimum number of healthy replicas needed
        timeout: Maximum time to wait in seconds
        check_interval: How often to check status in seconds
        
    Returns:
        True if enough replicas are ready, False if timeout
    """
    api_base = f"{server_url}/api/v1"
    start_time = time.time()
    
    print(f"Waiting for service group {group_id} (need {min_healthy} healthy replicas)...")
    
    while time.time() - start_time < timeout:
        try:
            # Get service group info
            response = requests.get(f"{api_base}/service-groups/{group_id}", timeout=10)
            
            if response.status_code == 200:
                group_data = response.json()
                
                # Extract replica counts from group data
                healthy_count = group_data.get("healthy_replicas", 0)
                total_count = group_data.get("total_replicas", 0)
                starting_count = group_data.get("starting_replicas", 0)
                pending_count = group_data.get("pending_replicas", 0)
                failed_count = group_data.get("failed_replicas", 0)
                
                print(f"  Status: {healthy_count}/{total_count} running, {starting_count} starting, {pending_count} pending, {failed_count} failed     ", end="\r")
                
                if healthy_count >= min_healthy:
                    print(f"\n[+] Service group is ready with {healthy_count} healthy replicas!")
                    return True
            elif response.status_code == 404:
                # Service group not found yet - replicas may not be registered
                elapsed = int(time.time() - start_time)
                print(f"  Waiting for replicas to be registered... ({elapsed}s elapsed)     ", end="\r")
        except requests.exceptions.RequestException as e:
            print(f"\n  Connection error: {e}")
        
        time.sleep(check_interval)
    
    print(f"\n[-] Timeout waiting for service group after {timeout}s")
    return False
