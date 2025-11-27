"""
Integration Tests for Client Service - vLLM Load Testing Workflows

These tests mirror the workflows from examples/simple_vllm_load_test.py
and validate the full end-to-end functionality of:
1. Creating a vLLM service via Server API
2. Waiting for the service to be ready
3. Creating a client group that generates load
4. Monitoring the client group
5. Cleanup

These tests require:
- Server service running and accessible
- Client service running and accessible
- SLURM access for job submission
- Network connectivity

Mark: @pytest.mark.integration
Run with: pytest tests/integration/ -v -m integration
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional

import pytest
import requests

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration

# Configuration from environment
SERVER_WAIT_TIMEOUT = int(os.getenv("INTEGRATION_SERVER_WAIT", "60"))
CLIENT_WAIT_TIMEOUT = int(os.getenv("INTEGRATION_CLIENT_WAIT", "60"))
SERVICE_READY_TIMEOUT = int(os.getenv("INTEGRATION_SERVICE_TIMEOUT", "600"))
CLIENT_GROUP_MONITOR_TIMEOUT = int(os.getenv("INTEGRATION_CLIENT_MONITOR_TIMEOUT", "300"))


# ============================================================================
# Helper Functions (inline copies from examples/utils/utils.py)
# ============================================================================

def wait_for_server(server_url: str, max_wait: int = 30) -> bool:
    """Wait for server to be ready by polling the health endpoint."""
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
    """Wait for client service to be ready by polling the health endpoint."""
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
    """Wait for service to be ready and return its endpoint."""
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
            response = requests.get(
                f"{api_base}/services/{service_id}/status",
                timeout=10
            )
            
            if response.status_code == 200:
                status_data = response.json()
                current_status = status_data.get("status")
                
                if current_status != last_status:
                    print(f"  [{attempts}] Status: {current_status} | Elapsed: {elapsed:.1f}s")
                    last_status = current_status
                
                if current_status in ["failed", "cancelled", "timeout"]:
                    print(f"[-] Service failed with status: {current_status}")
                    return None
                
                if current_status == "running" and not endpoint_found:
                    try:
                        models_response = requests.get(
                            f"{api_base}/vllm/{service_id}/models",
                            timeout=10
                        )
                        if models_response.status_code == 200:
                            models_data = models_response.json()
                            if models_data.get("success") is True:
                                endpoint_found = True
                                print(f"[+] Service is ready! (took {elapsed:.1f}s, {attempts} checks)")
                                print(f"[+] Service accessible via: /api/v1/vllm/{service_id}")
                                return f"/api/v1/vllm/{service_id}"
                            else:
                                error_msg = models_data.get("error", "loading")
                                if attempts % 3 == 0:
                                    print(f"  [{attempts}] vLLM {error_msg}...")
                        else:
                            if attempts % 3 == 0:
                                print(f"  [{attempts}] vLLM loading... (status: {models_response.status_code})")
                    except requests.exceptions.RequestException:
                        if attempts % 3 == 0:
                            print(f"  [{attempts}] Waiting for vLLM to start...")
                            
        except requests.exceptions.RequestException:
            pass
        time.sleep(poll_interval)
    
    print(f"[-] Service did not become ready within {max_wait}s")
    return None


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def server_base_url() -> str:
    """Discover and validate the base URL for the running server service."""
    url = _discover_server_url()
    if not wait_for_server(url, max_wait=SERVER_WAIT_TIMEOUT):
        pytest.skip(f"Server not reachable at {url}")
    return url.rstrip("/")


@pytest.fixture(scope="module")
def client_base_url() -> str:
    """Discover and validate the base URL for the running client service."""
    url = _discover_client_url()
    if not wait_for_client(url, max_wait=CLIENT_WAIT_TIMEOUT):
        pytest.skip(f"Client service not reachable at {url}")
    return url.rstrip("/")


@pytest.fixture(scope="module")
def server_api_base(server_base_url: str) -> str:
    """Convenience fixture for the Server API v1 base path."""
    return f"{server_base_url}/api/v1"


@pytest.fixture(scope="module")
def client_api_base(client_base_url: str) -> str:
    """Convenience fixture for the Client API v1 base path."""
    return f"{client_base_url}/api/v1"


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.integration
def test_simple_vllm_load_test(server_base_url: str, server_api_base: str, 
                                client_api_base: str):
    """
    Test the complete vLLM load testing workflow.
    
    This test mirrors examples/simple_vllm_load_test.py:
    1. Create a vLLM service
    2. Wait for it to be ready
    3. Create a client group to generate load
    4. Monitor the client group briefly
    5. Clean up both service and client group
    """
    service_id: Optional[str] = None
    group_id: Optional[int] = None
    
    try:
        # Step 1: Create vLLM service
        print("\n" + "="*80)
        print("STEP 1: Creating vLLM Service")
        print("="*80)
        
        payload = {
            "recipe_name": "inference/vllm-single-node"
        }
        
        response = requests.post(f"{server_api_base}/services", json=payload, timeout=120)
        response.raise_for_status()
        
        service = response.json()
        service_id = service["id"]
        
        print(f"Service created with ID: {service_id}")
        print(f"  Status: {service['status']}")
        print(f"  Recipe: {service['recipe_name']}")
        
        # Step 2: Wait for service to be ready
        print("\n" + "="*80)
        print("STEP 2: Waiting for vLLM Service to be Ready")
        print("="*80)
        
        endpoint = wait_for_service_ready(server_base_url, service_id, 
                                         max_wait=SERVICE_READY_TIMEOUT)
        
        assert endpoint is not None, "Service did not become ready in time"
        print(f"Service endpoint: {endpoint}")
        
        # Step 3: Create client group for load testing
        print("\n" + "="*80)
        print("STEP 3: Creating Client Group for Load Testing")
        print("="*80)
        
        load_config = {
            "service_id": service_id,
            "num_clients": 10,
            "requests_per_second": 0.2,
            "duration_seconds": 60,
            "prompts": [
                "Write a short poem about AI.",
                "Explain what machine learning is.",
                "Tell me a fun fact about computers.",
                "What is Python programming?"
            ],
            "max_tokens": 50,
            "temperature": 0.7,
            "time_limit": 10
        }
        
        print(f"Load test configuration:")
        print(f"  Service ID: {service_id}")
        print(f"  Clients: {load_config['num_clients']}")
        print(f"  RPS: {load_config['requests_per_second']}")
        print(f"  Duration: {load_config['duration_seconds']}s")
        
        response = requests.post(f"{client_api_base}/client-groups", 
                               json=load_config, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        group_id = result.get('group_id')
        
        assert group_id is not None, "Client group creation did not return group_id"
        print(f"Client group {group_id} created successfully")
        
        # Step 4: Monitor client group briefly
        print("\n" + "="*80)
        print("STEP 4: Monitoring Client Group (brief)")
        print("="*80)
        
        _monitor_client_group_brief(client_api_base, group_id, duration=30)
        
        print("\n" + "="*80)
        print("SUCCESS: Load test workflow completed successfully!")
        print("="*80)
        print(f"Service ID: {service_id}")
        print(f"Client Group ID: {group_id}")
        print(f"Endpoint: {endpoint}")
        
    finally:
        # Cleanup: Stop service and client group
        print("\n" + "="*80)
        print("CLEANUP: Stopping services")
        print("="*80)
        
        if service_id:
            _cleanup_service(server_api_base, service_id)
        
        # Client groups are typically cleaned up automatically when the SLURM job completes
        # but we can verify it's in a terminal state
        if group_id:
            print(f"Client group {group_id} will complete based on SLURM job lifecycle")


# ============================================================================
# Helper Functions
# ============================================================================

def _discover_server_url() -> str:
    """Resolve the server base URL using env vars or discovery file."""
    env_url = os.getenv("SERVER_URL")
    if env_url:
        return env_url.rstrip("/")
    
    # Try to find discovery file
    repo_root = Path(__file__).parent.parent.parent.parent.parent
    endpoint_file = repo_root / "services" / "server" / ".server-endpoint"
    if endpoint_file.exists():
        content = endpoint_file.read_text(encoding="utf-8").strip()
        if content:
            url = content.rstrip("/")
            # When running in test container, rewrite localhost -> server
            if os.getenv("TESTING") and "localhost" in url:
                return url.replace("localhost", "server")
            return url
    
    return "http://localhost:8001"


def _discover_client_url() -> str:
    """Resolve the client base URL using env vars or default."""
    env_url = os.getenv("CLIENT_URL")
    if env_url:
        return env_url.rstrip("/")
    
    # When running in test container, use service name
    if os.getenv("TESTING"):
        return "http://client:8003"
    
    return "http://localhost:8003"


def _monitor_client_group_brief(client_api_base: str, group_id: int, duration: int = 30):
    """Monitor client group for a brief period to verify it's running."""
    print(f"Monitoring client group {group_id} for {duration}s...")
    
    start_time = time.time()
    while time.time() - start_time < duration:
        try:
            response = requests.get(f"{client_api_base}/client-groups/{group_id}", timeout=10)
            
            if response.status_code == 200:
                group_info = response.json()
                status = group_info.get('info', {}).get('status', 'unknown')
                job_id = group_info.get('info', {}).get('job_id', 'N/A')
                elapsed = int(time.time() - start_time)
                
                print(f"  [{elapsed}s] Status: {status}, Job ID: {job_id}")
                
                if status == 'stopped':
                    print(f"Client group completed after {elapsed}s")
                    return
        except requests.RequestException as e:
            print(f"  Error querying group: {e}")
        
        time.sleep(5)
    
    print(f"Monitoring period complete ({duration}s)")


def _cleanup_service(server_api_base: str, service_id: str):
    """Stop a running vLLM service."""
    print(f"Stopping service {service_id}...")
    try:
        response = requests.post(
            f"{server_api_base}/services/{service_id}/status",
            json={"status": "cancelled"},
            timeout=30
        )
        response.raise_for_status()
        print(f"Service {service_id} stopped successfully")
    except requests.RequestException as e:
        print(f"Warning: Failed to stop service {service_id}: {e}")
