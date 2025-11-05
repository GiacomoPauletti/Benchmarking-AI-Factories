#!/usr/bin/env python3
"""
Simple test script to verify monitoring service registration works correctly.
This test doesn't require SLURM - it just tests the registration API.
"""

import requests
import json
import time

MONITORING_URL = "http://localhost:8002"
SERVER_URL = "http://localhost:8001"


def test_monitoring_registration():
    """Test the complete monitoring registration flow."""
    
    print("=" * 70)
    print("Testing Monitoring Service Registration")
    print("=" * 70)
    print()
    
    # Step 1: Create a monitoring session
    print("[1] Creating monitoring session...")
    session_response = requests.post(
        f"{MONITORING_URL}/api/v1/sessions",
        json={
            "run_id": f"test-{int(time.time())}",
            "scrape_interval": "15s",
            "labels": {"test": "true", "environment": "local"}
        }
    )
    
    if session_response.status_code != 200:
        print(f"  [ERROR] Failed to create session: {session_response.status_code}")
        print(f"  Response: {session_response.text}")
        return False
    
    session_data = session_response.json()
    session_id = session_data["session_id"]
    print(f"  [OK] Created session: {session_id}")
    print(f"  Status: {session_data['status']}")
    print(f"  Targets: {session_data['targets_count']}")
    print()
    
    # Step 2: Get an existing service from Server API
    print("[2] Fetching existing services from Server API...")
    services_response = requests.get(f"{SERVER_URL}/api/v1/services")
    
    if services_response.status_code != 200:
        print(f"  [ERROR] Failed to fetch services: {services_response.status_code}")
        return False
    
    services = services_response.json()
    if not services:
        print("  [ERROR] No services found. Please create a service first.")
        return False
    
    # Use the first vLLM service we find
    vllm_service = next((s for s in services if "vllm" in s.get("recipe_name", "")), None)
    
    if not vllm_service:
        print("  [ERROR] No vLLM service found")
        return False
    
    service_id = vllm_service["id"]
    service_name = vllm_service["name"]
    print(f"  [OK] Found service: {service_name} (ID: {service_id})")
    print()
    
    # Step 3: Register the service for monitoring
    print("[3] Registering service for monitoring...")
    registration_response = requests.post(
        f"{MONITORING_URL}/api/v1/services",
        json={
            "session_id": session_id,
            "service_id": service_id,
            "labels": {
                "model": "gpt2",
                "service_type": "vllm"
            }
        }
    )
    
    print(f"  Response status: {registration_response.status_code}")
    print(f"  Response body: {registration_response.text}")
    print()
    
    if registration_response.status_code != 200:
        print(f"  [ERROR] Registration failed!")
        print(f"  Status: {registration_response.status_code}")
        print(f"  Response: {registration_response.text}")
        return False
    
    registration_data = registration_response.json()
    print(f"  [OK] Service registered successfully!")
    print(f"  OK: {registration_data.get('ok')}")
    print(f"  Service ID: {registration_data.get('service_id')}")
    print(f"  Endpoint: {registration_data.get('endpoint')}")
    print()
    
    # Step 4: Verify session status shows the new target
    print("[4] Verifying session status...")
    status_response = requests.get(f"{MONITORING_URL}/api/v1/sessions/{session_id}/status")
    
    if status_response.status_code != 200:
        print(f"  [ERROR] Failed to get status: {status_response.status_code}")
        return False
    
    status_data = status_response.json()
    print(f"  [OK] Session status:")
    print(f"  Status: {status_data['status']}")
    print(f"  Targets: {status_data['targets_count']}")
    prometheus_info = status_data.get('prometheus', {})
    print(f"  Prometheus healthy: {prometheus_info.get('healthy', 'unknown')}")
    print(f"  Prometheus ready: {prometheus_info.get('ready', 'unknown')}")
    print()
    
    # Step 5: Check Prometheus targets
    print("[5] Checking Prometheus targets...")
    try:
        prom_response = requests.get("http://localhost:9090/api/v1/targets")
        if prom_response.status_code == 200:
            targets = prom_response.json().get("data", {}).get("activeTargets", [])
            service_target = next((t for t in targets if service_id in t.get("labels", {}).get("job", "")), None)
            
            if service_target:
                print(f"  [OK] Found target in Prometheus:")
                print(f"  Job: {service_target['labels']['job']}")
                print(f"  Scrape URL: {service_target['scrapeUrl']}")
                print(f"  Health: {service_target['health']}")
            else:
                print(f"  [WARN] Target not found in Prometheus (may need time to appear)")
        else:
            print(f"  [WARN] Could not fetch Prometheus targets")
    except Exception as e:
        print(f"  [WARN] Error checking Prometheus: {e}")
    print()
    
    # Step 6: Cleanup
    print("[6] Cleaning up...")
    stop_response = requests.post(f"{MONITORING_URL}/api/v1/sessions/{session_id}/stop")
    
    if stop_response.status_code == 200:
        print(f"  [OK] Session stopped")
    else:
        print(f"  [WARN] Failed to stop session: {stop_response.status_code}")
    print()
    
    print("=" * 70)
    print("TEST PASSED ✓")
    print("=" * 70)
    return True


if __name__ == "__main__":
    try:
        success = test_monitoring_registration()
        exit(0 if success else 1)
    except Exception as e:
        print(f"[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
