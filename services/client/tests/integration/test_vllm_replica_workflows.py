"""
Integration Tests for Client Service - vLLM Replica Load Testing Workflows

These tests mirror the workflows from examples/simple_vllm_replica_load_test.py
and validate the full end-to-end functionality of:
1. Creating a vLLM replica service group via Server API
2. Waiting for replicas to be ready
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
SERVICE_GROUP_READY_TIMEOUT = int(os.getenv("INTEGRATION_GROUP_TIMEOUT", "600"))
CLIENT_GROUP_MONITOR_TIMEOUT = int(os.getenv("INTEGRATION_CLIENT_MONITOR_TIMEOUT", "300"))
MIN_HEALTHY_REPLICAS = int(os.getenv("INTEGRATION_MIN_HEALTHY_REPLICAS", "1"))


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


def wait_for_service_group_ready(
    server_url: str, 
    group_id: str, 
    min_healthy: int = 1, 
    timeout: int = 600, 
    check_interval: int = 5
) -> bool:
    """Wait for at least min_healthy replicas in a service group to be ready."""
    api_base = f"{server_url}/api/v1"
    start_time = time.time()
    
    print(f"Waiting for service group {group_id} (need {min_healthy} healthy replicas)...")
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{api_base}/service-groups/{group_id}", timeout=10)
            
            if response.status_code == 200:
                group_data = response.json()
                
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
                elapsed = int(time.time() - start_time)
                print(f"  Waiting for replicas to be registered... ({elapsed}s elapsed)     ", end="\r")
        except requests.exceptions.RequestException as e:
            print(f"\n  Connection error: {e}")
        
        time.sleep(check_interval)
    
    print(f"\n[-] Timeout waiting for service group after {timeout}s")
    return False


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
def test_simple_vllm_replica_load_test(server_base_url: str, server_api_base: str,
                                       client_api_base: str):
    """
    Test the complete vLLM replica load testing workflow.
    
    This test mirrors examples/simple_vllm_replica_load_test.py:
    1. Create a vLLM replica service group
    2. Wait for replicas to be ready
    3. Create a client group to generate load
    4. Monitor the client group briefly
    5. Clean up both service group and client group
    """
    service_group_id: Optional[str] = None
    client_group_id: Optional[int] = None
    
    try:
        # Step 1: Create vLLM replica service group
        print("\n" + "="*80)
        print("STEP 1: Creating vLLM Replica Service Group")
        print("="*80)
        
        payload = {
            "recipe_name": "inference/vllm-replicas"
        }
        
        response = requests.post(f"{server_api_base}/services", json=payload, timeout=120)
        response.raise_for_status()
        
        group_info = response.json()
        service_group_id = group_info.get("group_id") or group_info.get("id")
        
        assert service_group_id is not None, "Service group creation did not return group_id"
        
        total_replicas = group_info.get("total_replicas")
        status = group_info.get("status")
        
        print(f"Service group created with ID: {service_group_id}")
        if total_replicas is not None:
            print(f"  Replicas: {total_replicas}")
        if status:
            print(f"  Status: {status}")
        print(f"  Recipe: {group_info.get('recipe_name')}")
        
        # Step 2: Wait for replicas to be ready
        print("\n" + "="*80)
        print("STEP 2: Waiting for vLLM Replicas to be Ready")
        print("="*80)
        
        ready = wait_for_service_group_ready(
            server_base_url,
            service_group_id,
            min_healthy=MIN_HEALTHY_REPLICAS,
            timeout=SERVICE_GROUP_READY_TIMEOUT,
        )
        
        assert ready, f"Service group did not reach {MIN_HEALTHY_REPLICAS} healthy replicas in time"
        
        prompt_url = f"{server_api_base}/vllm/{service_group_id}/prompt"
        print(f"Replica prompt URL: {prompt_url}")
        
        # Step 3: Create client group for load testing
        print("\n" + "="*80)
        print("STEP 3: Creating Client Group for Load Testing")
        print("="*80)
        
        load_config = {
            "service_id": service_group_id,
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
        print(f"  Service Group ID: {service_group_id}")
        print(f"  Clients: {load_config['num_clients']}")
        print(f"  RPS: {load_config['requests_per_second']}")
        print(f"  Duration: {load_config['duration_seconds']}s")
        
        response = requests.post(f"{client_api_base}/client-groups",
                               json=load_config, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        client_group_id = result.get('group_id')
        
        assert client_group_id is not None, "Client group creation did not return group_id"
        print(f"Client group {client_group_id} created successfully")
        
        # Step 4: Monitor client group briefly
        print("\n" + "="*80)
        print("STEP 4: Monitoring Client Group (brief)")
        print("="*80)
        
        _monitor_client_group_brief(client_api_base, client_group_id, duration=30)
        
        print("\n" + "="*80)
        print("SUCCESS: Replica load test workflow completed successfully!")
        print("="*80)
        print(f"Service Group ID: {service_group_id}")
        print(f"Client Group ID: {client_group_id}")
        print(f"Prompt URL: {prompt_url}")
        
    finally:
        # Cleanup: Stop service group and client group
        print("\n" + "="*80)
        print("CLEANUP: Stopping services")
        print("="*80)
        
        if service_group_id:
            _cleanup_service_group(server_api_base, service_group_id)
        
        # Client groups are typically cleaned up automatically when the SLURM job completes
        if client_group_id:
            print(f"Client group {client_group_id} will complete based on SLURM job lifecycle")


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


def _cleanup_service_group(server_api_base: str, group_id: str):
    """Stop a running vLLM service group and its replicas."""
    print(f"Stopping service group {group_id}...")
    try:
        response = requests.delete(f"{server_api_base}/service-groups/{group_id}", timeout=60)
        response.raise_for_status()
        print(f"Service group {group_id} stopped successfully")
    except requests.RequestException as e:
        print(f"Warning: Failed to stop service group {group_id}: {e}")
