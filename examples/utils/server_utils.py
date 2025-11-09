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


def wait_for_service_ready(server_url: str, service_id: str, max_wait: int = 300) -> bool:
    """
    Wait for service to be ready by polling the status endpoint.
    
    Args:
        server_url: Base URL of the server (e.g., "http://localhost:8001")
        service_id: Service ID (SLURM job ID)
        max_wait: Maximum time to wait in seconds
        
    Returns:
        True if service is ready, False otherwise
    """
    print(f"Waiting for service {service_id} to be ready...")
    api_base = f"{server_url}/api/v1"
    start = time.time()
    last_status = None
    
    while time.time() - start < max_wait:
        try:
            # Poll the status endpoint
            response = requests.get(
                f"{api_base}/services/{service_id}/status",
                timeout=10
            )
            
            if response.status_code == 200:
                status_data = response.json()
                current_status = status_data.get("status")
                
                # Print status changes
                if current_status != last_status:
                    elapsed = int(time.time() - start)
                    print(f"  Status: {current_status} (waited {elapsed}s)")
                    last_status = current_status
                
                # Service is ready when status is "running"
                if current_status == "running":
                    print(f"[+] Service is ready!")
                    return True
                
                # Service failed
                if current_status in ["failed", "cancelled"]:
                    print(f"[-] Service failed with status: {current_status}")
                    return False
        except requests.exceptions.RequestException:
            pass
    
    print(f"[-] Service did not become ready within {max_wait}s")
    return False
