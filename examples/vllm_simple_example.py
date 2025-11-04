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


def wait_for_server(server_url: str, max_wait: int = 30) -> bool:
    """Wait for server to be ready."""
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
        
        time.sleep(3)
    
    print(f"[-] Service did not become ready within {max_wait}s")
    return False


def main():
    """Run the simple example."""
    print("Simple Example: Basic vLLM Service Usage")
    
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
                    "nodes": 2,  
                    "model": model
                }
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
