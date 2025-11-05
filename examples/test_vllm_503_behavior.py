#!/usr/bin/env python3
"""
Test script to verify 503 behavior when services aren't ready yet.
"""

import requests
import time

SERVER_URL = "http://localhost:8001"

def test_vllm_503():
    """Test that metrics endpoint returns 503 for non-running services."""
    
    print("=" * 70)
    print("Testing vLLM Service - 503 Behavior for Pending Services")
    print("=" * 70)
    print()
    
    # Step 1: Create vLLM service
    print("[1] Creating vLLM service...")
    response = requests.post(
        f"{SERVER_URL}/api/v1/services",
        json={
            "recipe_name": "inference/vllm",
            "config": {
                "environment": {
                    "VLLM_MODEL": "gpt2"
                },
                "resources": {
                    "cpu": "4",
                    "memory": "8G",
                    "time_limit": 60
                }
            }
        }
    )
    response.raise_for_status()
    service = response.json()
    service_id = service["id"]
    
    print(f"  [OK] Created service: {service_id}")
    print(f"  Status: {service['status']}")
    print()
    
    # Step 2: Immediately try to get metrics (should be 503)
    print("[2] Testing metrics endpoint while service is pending...")
    response = requests.get(f"{SERVER_URL}/api/v1/services/{service_id}/metrics")
    
    print(f"  HTTP Status: {response.status_code}")
    if response.status_code == 503:
        print(f"  [OK] Got 503 Service Unavailable (as expected)")
        print(f"  Message: {response.json()['detail']}")
    elif response.status_code == 200:
        print(f"  [INFO] Got 200 OK (service started very quickly!)")
        print(f"  Metrics length: {len(response.text)} bytes")
    else:
        print(f"  [UNEXPECTED] Got {response.status_code}")
        print(f"  Response: {response.text}")
    print()
    
    # Step 3: Check service status
    print("[3] Checking service status...")
    response = requests.get(f"{SERVER_URL}/api/v1/services/{service_id}")
    response.raise_for_status()
    service = response.json()
    status = service["status"]
    print(f"  Status: {status}")
    print()
    
    # Step 4: Poll status until running or timeout
    print("[4] Waiting for service to start (max 5 minutes)...")
    start_time = time.time()
    timeout = 300  # 5 minutes
    poll_interval = 10  # 10 seconds
    
    while True:
        elapsed = time.time() - start_time
        
        # Check service status
        response = requests.get(f"{SERVER_URL}/api/v1/services/{service_id}")
        response.raise_for_status()
        service = response.json()
        status = service["status"]
        
        # Try metrics endpoint
        metrics_response = requests.get(f"{SERVER_URL}/api/v1/services/{service_id}/metrics")
        
        print(f"  [{elapsed:.0f}s] Service status: {status:12s} | Metrics: {metrics_response.status_code}")
        
        if status == "running":
            print(f"\n  [OK] Service is now RUNNING!")
            print(f"  Time taken: {elapsed:.1f}s")
            
            if metrics_response.status_code == 200:
                print(f"  [OK] Metrics endpoint now returns 200")
                # Show first few lines of metrics
                lines = metrics_response.text.split('\n')[:10]
                print(f"\n  Sample metrics:")
                for line in lines:
                    if line and not line.startswith('#'):
                        print(f"    {line}")
            break
        elif status in ["failed", "cancelled", "timeout"]:
            print(f"\n  [ERROR] Service entered terminal state: {status}")
            break
        
        if elapsed >= timeout:
            print(f"\n  [TIMEOUT] Service did not start within {timeout}s")
            break
        
        time.sleep(poll_interval)
    
    print()
    
    # Step 5: Cleanup
    print("[5] Cleaning up...")
    try:
        response = requests.post(
            f"{SERVER_URL}/api/v1/services/{service_id}/status",
            json={"status": "cancelled"}
        )
        if response.status_code == 200:
            print(f"  [OK] Service {service_id} stopped")
        else:
            print(f"  [WARNING] Failed to stop service: {response.status_code}")
    except Exception as e:
        print(f"  [WARNING] Could not stop service: {e}")
    
    print()
    print("=" * 70)
    print("Test Complete")
    print("=" * 70)


if __name__ == "__main__":
    try:
        test_vllm_503()
    except KeyboardInterrupt:
        print("\n\n[!] Interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
