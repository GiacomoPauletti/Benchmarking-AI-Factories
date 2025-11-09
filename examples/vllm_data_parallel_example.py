#!/usr/bin/env python3
"""
Data-Parallel vLLM Example with Replicas

This script demonstrates the data-parallel replica system:
1. Create a service group with multiple vLLM replicas
2. Send multiple prompts that are automatically load-balanced
3. Show which replica handled each request
4. Demonstrate resilience to replica failures
"""

import requests
import time
import os
from utils.server_utils import wait_for_server, wait_for_service_group_ready


def main():
    """Run the data-parallel example."""
    print("=" * 70)
    print("Data-Parallel vLLM Example: Multiple Replicas with Load Balancing")
    print("=" * 70)
    
    # Configuration
    server_url = os.getenv("SERVER_URL", "http://localhost:8001")
    api_base = f"{server_url}/api/v1"
    
    # Number of replicas to create
    num_replicas = 2
    
    service_id = None
    
    try:
        # Step 1: Check server
        if not wait_for_server(server_url):
            print("\n[-] Server is not running. Please start it first:")
            print("   docker compose up -d server")
            return
        
        # Step 2: Create vLLM service group with replicas
        print(f"\n[*] Creating vLLM service group with {num_replicas} replicas...")
        print(f"    (Each replica gets 1 node with 4 GPUs)")
        
        response = requests.post(
            f"{api_base}/services",
            json={
                "recipe_name": "inference/vllm-data-parallel",
                "config": {
                    "replicas": num_replicas  # Override default if needed
                }
            },
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"[-] Failed to create service group: {response.text}")
            return
        
        data = response.json()
        service_id = data["id"]
        print(f"[+] Service group created with ID: {service_id}")
        print(f"  Type: {data.get('type')}")
        print(f"  Replicas:")
        for replica in data.get("replicas", []):
            print(f"    - {replica['id']} (status: {replica['status']})")
        
        # Step 3: Wait for at least 1 replica to be ready
        # Give the server a moment to register replicas before checking
        print(f"\n[*] Waiting for at least two replicas to be ready...")
        time.sleep(2)  # Small delay for server to register replicas
        if not wait_for_service_group_ready(server_url, service_id, min_healthy=2, timeout=600):
            print("[-] No replicas became ready in time")
            return
        
        # Step 4: Send multiple prompts to demonstrate load balancing
        prompts = [
            "What is the capital of France?",
            "Explain machine learning in one sentence.",
            "What is 2+2?",
            "Name a famous scientist.",
            "What is the speed of light?",
            "What color is the sky?",
        ]
        
        print(f"\n[*] Sending {len(prompts)} prompts to demonstrate load balancing...")
        print("=" * 70)
        
        results = []
        for i, prompt in enumerate(prompts, 1):
            print(f"\n[Prompt {i}/{len(prompts)}] {prompt}")
            
            response = requests.post(
                f"{api_base}/vllm/{service_id}/prompt",
                json={
                    "prompt": prompt,
                    "max_tokens": 50,
                    "temperature": 0.7
                },
                timeout=120
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    answer = data.get("response", "")
                    routed_to = data.get("routed_to", "unknown")
                    usage = data.get("usage", {})
                    
                    print(f"[+] Response from replica {routed_to}:")
                    print(f"  {answer}")
                    print(f"  Tokens: {usage.get('total_tokens', 'N/A')}")
                    
                    results.append({
                        "prompt": prompt,
                        "replica": routed_to,
                        "success": True
                    })
                else:
                    print(f"[-] Error: {data.get('error')}")
                    results.append({
                        "prompt": prompt,
                        "replica": None,
                        "success": False
                    })
            else:
                print(f"[-] HTTP Error {response.status_code}: {response.text}")
                results.append({
                    "prompt": prompt,
                    "replica": None,
                    "success": False
                })
            
            # Small delay between requests
            time.sleep(1)
        
        # Step 5: Show load balancing statistics
        print("\n" + "=" * 70)
        print("Load Balancing Summary:")
        print("=" * 70)
        
        successful = [r for r in results if r["success"]]
        replica_counts = {}
        for result in successful:
            replica = result["replica"]
            replica_counts[replica] = replica_counts.get(replica, 0) + 1
        
        print(f"\nTotal requests: {len(prompts)}")
        print(f"Successful: {len(successful)}")
        print(f"\nRequests per replica:")
        for replica, count in sorted(replica_counts.items()):
            print(f"  {replica}: {count} requests")
        
        # Check distribution
        if len(replica_counts) > 1:
            print(f"\n[+] Load balancing is working! Requests were distributed across {len(replica_counts)} replicas.")
        else:
            print(f"\n[!] All requests went to the same replica. This might be expected if only 1 replica is healthy.")
        
        print("\n[+] Example completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n[-] Interrupted by user")
    except Exception as e:
        print(f"\n[-] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if service_id:
            print(f"\n[*] Stopping service group {service_id} (and all replicas)...")
            try:
                response = requests.delete(
                    f"{api_base}/services/{service_id}",
                    timeout=10
                )
                if response.status_code == 200:
                    print(f"[+] Service group stopped")
                else:
                    print(f"[-] Failed to stop service group: {response.text}")
            except Exception as e:
                print(f"[-] Error stopping service group: {e}")

        print("\n" + "=" * 70)
        print("Done!")
        print("=" * 70)


if __name__ == "__main__":
    main()
