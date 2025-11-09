#!/usr/bin/env python3
"""
Multi-Node vLLM Example: Testing Multi-Node Tensor Parallelism

This script demonstrates:
1. Creating a multi-node vLLM service (2 nodes, 8 GPUs total)
2. Waiting for the distributed service to be ready
3. Sending a prompt and getting a response
4. Testing the extended timeout for multi-node coordination
"""

import requests
import time
import os
from utils.server_utils import wait_for_server, wait_for_service_ready


def main():
    """Run the multi-node vLLM example."""
    print("=" * 70)
    print("Multi-Node vLLM Example: 2 Nodes, 8 GPUs (Tensor Parallelism)")
    print("=" * 70)
    
    # Configuration
    server_url = os.getenv("SERVER_URL", "http://localhost:8001")
    api_base = f"{server_url}/api/v1"
    
    service_id = None
    
    try:
        # Step 1: Check server
        print("\n[1/5] Checking server connection...")
        if not wait_for_server(server_url):
            print("\n❌ Server is not running. Please start it first:")
            print("   docker compose up -d server")
            return
        print("✓ Server is ready")
        
        # Step 2: Create multi-node vLLM service
        print(f"\n[2/5] Creating multi-node vLLM service...")
        print("   Configuration:")
        print("   - Nodes: 2")
        print("   - GPUs per node: 4")
        print("   - Total GPUs (tensor parallel): 8")
        print("   - Model: Qwen/Qwen2.5-0.5B-Instruct")
        print("\n   Note: Multi-node setup may take 1-2 minutes to initialize...")
        
        response = requests.post(
            f"{api_base}/services",
            json={
                "recipe_name": "inference/vllm-multi-node"
            },
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to create service: {response.text}")
            return
        
        data = response.json()
        service_id = data["id"]
        print(f"✓ Service created with ID: {service_id}")
        
        # Step 3: Wait for service to be ready
        print(f"\n[3/5] Waiting for multi-node service to be ready...")
        print("   (This includes: SLURM allocation, container startup, model loading,")
        print("    and multi-node coordination via NCCL)")
        
        if not wait_for_service_ready(server_url, service_id):
            print(f"\n❌ Service failed to become ready")
            # Show status for debugging
            try:
                status_resp = requests.get(f"{api_base}/services/{service_id}/status", timeout=10)
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    print(f"   Current status: {status_data.get('status')}")
                    print(f"   Check logs: services/server/logs/vllm-multi-node_{service_id}.out")
            except:
                pass
            return
        
        print("✓ Multi-node service is ready!")
        
        # Step 4: Send a test prompt
        prompt = "Explain tensor parallelism in one sentence."
        print(f"\n[4/5] Sending test prompt...")
        print(f"   Prompt: '{prompt}'")
        print(f"   Note: Multi-node requests use extended timeout (60s)")
        
        start_time = time.time()
        response = requests.post(
            f"{api_base}/vllm/{service_id}/prompt",
            json={
                "prompt": prompt,
                "max_tokens": 100,
                "temperature": 0.7
            },
            timeout=120  # Client-side timeout
        )
        elapsed = time.time() - start_time
        
        if response.status_code != 200:
            print(f"❌ Failed to get response: {response.text}")
            print(f"   Request took: {elapsed:.2f}s")
            return
        
        data = response.json()
        
        if not data.get("success"):
            print(f"❌ Error: {data.get('error')}")
            print(f"   Request took: {elapsed:.2f}s")
            return
        
        # Step 5: Display response
        answer = data.get("response", "")
        usage = data.get("usage", {})
        
        print(f"✓ Got response in {elapsed:.2f}s")
        print(f"\n[5/5] Response:")
        print("-" * 70)
        print(answer)
        print("-" * 70)
        
        print(f"\nToken usage:")
        print(f"   Prompt tokens: {usage.get('prompt_tokens', 'N/A')}")
        print(f"   Completion tokens: {usage.get('completion_tokens', 'N/A')}")
        print(f"   Total tokens: {usage.get('total_tokens', 'N/A')}")
        
        print("\n" + "=" * 70)
        print("✓ Multi-node example completed successfully!")
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user")
    except requests.exceptions.Timeout as e:
        print(f"\n❌ Request timed out: {e}")
        print("   Multi-node inference may need more time or there may be an issue.")
        print(f"   Check logs: services/server/logs/vllm-multi-node_{service_id}.out")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if service_id:
            print(f"\n[Cleanup] Stopping service {service_id}...")
            try:
                response = requests.delete(
                    f"{api_base}/services/{service_id}",
                    timeout=10
                )
                if response.status_code == 200:
                    print("✓ Service stopped")
                else:
                    print(f"⚠ Failed to stop service: {response.text}")
            except Exception as e:
                print(f"⚠ Error stopping service: {e}")

        print("\nDone!")


if __name__ == "__main__":
    main()
