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


def wait_for_client(client_url: str, max_wait: int = 30) -> bool:
    """
    Wait for client to be ready by polling the health endpoint.
    
    Args:
        client_url: Base URL of the client service (e.g., "http://localhost:8002")
        max_wait: Maximum time to wait in seconds
        
    Returns:
        True if client service is ready, False otherwise
    """
    print(f"Waiting for client service at {client_url}...")
    start = time.time()
    
    while time.time() - start < max_wait:
        try:
            response = requests.get(f"{client_url}/health", timeout=5)
            if response.status_code == 200:
                print("Client service is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    
    print("Client not available")
    return False


def wait_for_service_ready(
    server_url: str, 
    service_id: str, 
    max_wait: int = 300,
    poll_interval: int = 5
) -> Optional[str]:
    """
    Wait for service to be ready and return its endpoint.
    
    Args:
        server_url: Base URL of the server (e.g., "http://localhost:8001")
        service_id: Service ID (SLURM job ID)
        max_wait: Maximum time to wait in seconds
        poll_interval: How often to check status in seconds (default: 5)
        
    Returns:
        Service endpoint URL if ready, None otherwise
    """
    print(f"Waiting for service {service_id} to be ready...")
    print(f"  Max wait: {max_wait}s | Poll interval: {poll_interval}s")
    api_base = f"{server_url}/api/v1"
    start = time.time()
    last_status = None
    attempts = 0
    endpoint_found = False

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
                
                # Service failed - give up immediately
                if current_status in ["failed", "cancelled", "timeout"]:
                    print(f"[-] Service failed with status: {current_status}")
                    return None
                
                # Service is running - try to get endpoint but keep waiting if not found yet
                if current_status == "running" and not endpoint_found:
                    # Try to get the endpoint - it may take time for vLLM to start
                    try:
                        # Try direct endpoint construction (job_id and known port)
                        endpoint_response = requests.get(
                            f"{api_base}/services/{service_id}",
                            timeout=10
                        )
                        if endpoint_response.status_code == 200:
                            service_data = endpoint_response.json()
                            # The server should resolve the endpoint for us
                            # For now, we know vLLM runs on port 8001
                            # Try to query it via the orchestrator proxy
                            try:
                                # Test if we can reach vLLM through the proxy
                                models_response = requests.get(
                                    f"{api_base}/vllm/{service_id}/models",
                                    timeout=10
                                )
                                if models_response.status_code == 200:
                                    # Check if the response indicates success (vLLM is truly ready)
                                    models_data = models_response.json()
                                    if models_data.get("success") is True:
                                        endpoint_found = True
                                        print(f"[+] Service is ready! (took {elapsed:.1f}s, {attempts} checks)")
                                        print(f"[+] Service accessible via: /api/v1/vllm/{service_id}")
                                        return f"/api/v1/vllm/{service_id}"
                                    else:
                                        # vLLM server not ready yet (still starting/loading model)
                                        error_msg = models_data.get("error", "loading")
                                        if attempts % 3 == 0:  # Print every 3rd attempt
                                            print(f"  [{attempts}] vLLM {error_msg}...")
                                else:
                                    # vLLM server not responding yet, keep waiting
                                    if attempts % 3 == 0:  # Print every 3rd attempt
                                        print(f"  [{attempts}] vLLM loading... (status: {models_response.status_code})")
                            except requests.exceptions.RequestException:
                                # vLLM not reachable yet, keep waiting
                                if attempts % 3 == 0:
                                    print(f"  [{attempts}] Waiting for vLLM to start...")
                    except requests.exceptions.RequestException as e:
                        if attempts % 3 == 0:
                            print(f"  [{attempts}] Checking endpoint...")
                            
        except requests.exceptions.RequestException:
            pass
        time.sleep(poll_interval)
    
    print(f"[-] Service did not become ready within {max_wait}s")
    return None


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
                
                # Count replicas by status from node_jobs structure
                node_jobs = group_data.get("node_jobs", [])
                healthy_count = 0
                starting_count = 0
                pending_count = 0
                failed_count = 0
                
                for node_job in node_jobs:
                    for replica in node_job.get("replicas", []):
                        status = replica.get("status", "unknown")
                        if status in ["ready", "running", "healthy"]:
                            healthy_count += 1
                        elif status == "starting":
                            starting_count += 1
                        elif status == "pending":
                            pending_count += 1
                        elif status in ["failed", "error"]:
                            failed_count += 1
                
                total_count = group_data.get("total_replicas", 0)
                
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

def cleanup_service(service_id: str, server_url: str = "http://localhost:8001"):
    """Stop the vLLM service to free resources."""
    print("\n" + "=" * 80)
    print("STEP 5: Cleaning Up")
    print("=" * 80)
    
    api_base = f"{server_url}/api/v1"
    
    try:
        response = requests.post(
            f"{api_base}/services/{service_id}/status",
            json={"status": "cancelled"}
        )
        response.raise_for_status()
        print(f"✓ Service {service_id} stopped successfully")
    except requests.RequestException as e:
        print(f"✗ Failed to stop service: {e}")