#!/usr/bin/env python3
"""
Simple Example: Basic Server Usage

This script demonstrates the basic workflow:
1. Connect to the server
2. Create a vLLM service
3. Send a simple prompt
4. Get a response
"""

import requests
import time
import os
from utils.utils import wait_for_server, wait_for_service_ready


def main():
    """Run the simple example."""
    print("Simple Example: Basic vLLM Service Usage")
    
    # Configuration
    server_url = os.getenv("SERVER_URL", "http://localhost:8001")
    api_base = f"{server_url}/api/v1"
    
    service_id = None
    
    try:
        # Step 1: Check server
        if not wait_for_server(server_url):
            print("\nServer is not running. Please start it first:")
            print("   docker compose up -d server")
            return
        
        # Step 2: Create vLLM service
        print(f"\n[*] Creating vLLM service...")
        response = requests.post(
            f"{api_base}/services",
            json={
                "recipe_name": "inference/vllm-single-node"
            },
            timeout=60
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
        
        # Step 4: Prepare and send a prompt
        prompt = "What is the capital of France? Answer in one sentence."
        print(f"\n Sending prompt: '{prompt}'")
        
        response = requests.post(
            f"{api_base}/vllm/{service_id}/prompt",
            json={
                "prompt": prompt,
                "max_tokens": 100,
                "temperature": 0.7
            },
            timeout=120
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
        
        print(f"\nResponse:\n{answer}")
        print(f"\nToken usage:")
        print(f"   Prompt: {usage.get('prompt_tokens', 'N/A')}")
        print(f"   Completion: {usage.get('completion_tokens', 'N/A')}")
        print(f"   Total: {usage.get('total_tokens', 'N/A')}")
        
        print("\n Example completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n Interrupted by user")
    except Exception as e:
        print(f"\n Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if service_id:
            print(f"\n Stopping service {service_id}...")
            try:
                response = requests.delete(
                    f"{api_base}/services/{service_id}",
                    timeout=10
                )
                if response.status_code == 200:
                    print(f" Service stopped")
                else:
                    print(f"  Failed to stop service: {response.text}")
            except Exception as e:
                print(f" Error stopping service: {e}")

        print("Done!")


if __name__ == "__main__":
    main()
