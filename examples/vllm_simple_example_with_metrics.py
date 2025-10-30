#!/usr/bin/env python3
"""
Simple Example with Metrics: vLLM Service Usage + Prometheus Metrics

This script demonstrates the extended workflow:
1. Connect to the server
2. Create a vLLM service
3. Send a simple prompt
4. Get a response
5. Query Prometheus metrics from the vLLM service
6. Display key metrics
"""

import requests
import time
import os

# Import utilities
from utils import (
    wait_for_server,
    wait_for_service_ready,
    fetch_metrics,
    save_metrics_to_file,
    display_vllm_metrics
)


def main():
    """Run the simple example with metrics."""
    print("Simple Example: vLLM Service Usage with Metrics")
    
    # Configuration
    server_url = os.getenv("SERVER_URL", "http://localhost:8001")
    api_base = f"{server_url}/api/v1"
    model = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    
    service_id = None
    
    try:
        # Step 1: Check server
        if not wait_for_server(server_url):
            print("\nServer is not running. Please start it first:")
            print("   docker compose up -d server")
            return
        
        # Step 2: Create vLLM service
        print(f"\n[*] Creating vLLM service with model: {model}...")
        response = requests.post(
            f"{api_base}/services",
            json={
                "recipe_name": "inference/vllm",
                "config": {
                    "nodes": 1,
                    "model": model
                }
            },
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"Failed to create service: {response.text}")
            return
        
        data = response.json()
        service_id = data["id"]
        print(f"Service created with ID: {service_id}")
        
        # Step 3: Wait for service to be ready
        if not wait_for_service_ready(server_url, service_id):
            return
        
        # Step 3a: Fetch initial metrics
        print("\n[*] Fetching initial metrics...")
        metrics_before = fetch_metrics(server_url, service_id, service_type="vllm")
        if metrics_before:
            print("[+] Initial metrics retrieved")
            save_metrics_to_file(metrics_before, "before", service_id, service_type="vllm")
        
        # Step 4: Prepare and send a prompt
        prompt = "What is the capital of France? Answer in one sentence."
        print(f"\n[*] Sending prompt: '{prompt}'")
        
        response = requests.post(
            f"{api_base}/vllm/{service_id}/prompt",
            json={
                "prompt": prompt,
                "max_tokens": 100,
                "temperature": 0.7
            },
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"Failed to get response: {response.text}")
            return
        
        data = response.json()
        
        if not data.get("success"):
            print(f"Error: {data.get('error')}")
            return
        
        # Step 5: Display response
        answer = data.get("response", "")
        usage = data.get("usage", {})
        
        print(f"\n[+] Response received:")
        print(f"    {answer}")
        print(f"\nToken usage:")
        print(f"   Prompt: {usage.get('prompt_tokens', 'N/A')}")
        print(f"   Completion: {usage.get('completion_tokens', 'N/A')}")
        print(f"   Total: {usage.get('total_tokens', 'N/A')}")
        
        # Step 6: Fetch updated metrics after prompt
        print("\n[*] Fetching updated metrics after prompt...")
        time.sleep(1)  # Give service a moment to update metrics
        metrics_after = fetch_metrics(server_url, service_id, service_type="vllm")
        
        if metrics_after:
            save_metrics_to_file(metrics_after, "after", service_id, service_type="vllm")
            display_vllm_metrics(metrics_after)
            
            # Show differences if we have before/after metrics
            if metrics_before and metrics_before.get("prompt_tokens_total") is not None:
                print("\nMetrics Delta (after - before):")
                print("=" * 50)
                if metrics_after.get("prompt_tokens_total") is not None:
                    delta_prompt = (metrics_after["prompt_tokens_total"] or 0) - \
                                 (metrics_before["prompt_tokens_total"] or 0)
                    print(f"  Prompt Tokens Delta: {delta_prompt:+d}")
                
                if metrics_after.get("generation_tokens_total") is not None:
                    delta_gen = (metrics_after["generation_tokens_total"] or 0) - \
                              (metrics_before["generation_tokens_total"] or 0)
                    print(f"  Generation Tokens Delta: {delta_gen:+d}")
                print("=" * 50)
        
        print("\n[+] Example completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n[!] Interrupted by user")
    except Exception as e:
        print(f"\n[-] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if service_id:
            print(f"\n[*] Stopping service {service_id}...")
            try:
                response = requests.delete(
                    f"{api_base}/services/{service_id}",
                    timeout=10
                )
                if response.status_code == 200:
                    print(f"[+] Service stopped")
                else:
                    print(f"[-] Failed to stop service: {response.text}")
            except Exception as e:
                print(f"[-] Error stopping service: {e}")

        print("Done!")


if __name__ == "__main__":
    main()
