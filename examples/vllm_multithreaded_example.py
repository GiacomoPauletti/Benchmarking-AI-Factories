#!/usr/bin/env python3
"""
Multi-threaded Example: Concurrent vLLM Service Usage

This script demonstrates concurrent request handling:
1. Connect to the server
2. Create a vLLM service
3. Send multiple prompts concurrently using "threads" (not really parallel because of GIL)
4. Collect and display all responses
"""

import requests
import time
import os
from threading import Thread
from queue import Queue
from utils.server_utils import wait_for_server, wait_for_service_ready


def send_prompt(thread_id, server_url, service_id, prompt, results_queue):
    """
    Send a prompt to the vLLM service and store the result.
    
    Args:
        thread_id: Identifier for this thread
        server_url: Base server URL
        service_id: ID of the vLLM service
        prompt: The prompt text to send
        results_queue: Queue to store results
    """
    api_base = f"{server_url}/api/v1"
    start_time = time.time()
    
    try:
        print(f"[Thread {thread_id}] Sending prompt: '{prompt[:50]}...'")
        
        response = requests.post(
            f"{api_base}/vllm/{service_id}/prompt",
            json={
                "prompt": prompt,
                "max_tokens": 100,
                "temperature": 0.7
            },
            timeout=120
        )
        
        elapsed_time = time.time() - start_time
        
        if response.status_code != 200:
            results_queue.put({
                "thread_id": thread_id,
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
                "elapsed_time": elapsed_time
            })
            return
        
        data = response.json()
        
        if not data.get("success"):
            results_queue.put({
                "thread_id": thread_id,
                "success": False,
                "error": data.get("error", "Unknown error"),
                "elapsed_time": elapsed_time
            })
            return
        
        results_queue.put({
            "thread_id": thread_id,
            "success": True,
            "prompt": prompt,
            "response": data.get("response", ""),
            "usage": data.get("usage", {}),
            "elapsed_time": elapsed_time
        })
        
        print(f"[Thread {thread_id}] Completed in {elapsed_time:.2f}s")
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        results_queue.put({
            "thread_id": thread_id,
            "success": False,
            "error": str(e),
            "elapsed_time": elapsed_time
        })
        print(f"[Thread {thread_id}] Error: {e}")


def main():
    """Run the multi-threaded example."""
    print("Multi-threaded Example: Concurrent vLLM Service Usage")
    
    # Configuration
    server_url = os.getenv("SERVER_URL", "http://localhost:8001")
    api_base = f"{server_url}/api/v1"
    model = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    num_threads = int(os.getenv("NUM_THREADS", "5"))  # Number of concurrent requests
    
    # Define prompts for each thread
    prompts = [
        "What is the capital of France? Answer in one sentence.",
        "Explain what machine learning is in simple terms.",
        "What is the tallest mountain in the world?",
        "Who wrote the play Romeo and Juliet?",
        "What is the speed of light in vacuum?",
        "Explain photosynthesis briefly.",
        "What is the largest planet in our solar system?",
        "Who painted the Mona Lisa?",
        "What is the chemical symbol for gold?",
        "What year did World War II end?"
    ]
    
    # Use only as many prompts as threads requested
    prompts = prompts[:num_threads]
    
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
                    "nodes": 2,  # Use 1 node for faster queue times
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
        
        # Step 4: Launch concurrent requests
        print(f"\n[*] Launching {num_threads} concurrent requests...")
        print("-" * 80)
        
        threads = []
        results_queue = Queue()
        overall_start = time.time()
        
        for i, prompt in enumerate(prompts):
            thread = Thread(
                target=send_prompt,
                args=(i + 1, server_url, service_id, prompt, results_queue)
            )
            threads.append(thread)
            thread.start()
            # Small stagger to simulate "almost same time" rather than exact same time
            time.sleep(0.1)
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        overall_elapsed = time.time() - overall_start
        
        # Step 5: Collect and display results
        results = []
        while not results_queue.empty():
            results.append(results_queue.get())
        
        # Sort results by thread ID
        results.sort(key=lambda x: x["thread_id"])
        
        print("\n" + "=" * 80)
        print("RESULTS SUMMARY")
        print("=" * 80)
        
        successful = 0
        failed = 0
        total_tokens = 0
        
        for result in results:
            thread_id = result["thread_id"]
            print(f"\n--- Thread {thread_id} ---")
            
            if result["success"]:
                successful += 1
                print(f"Status: SUCCESS")
                print(f"  Prompt: {result['prompt'][:60]}...")
                print(f"  Response: {result['response'][:100]}...")
                print(f"  Elapsed time: {result['elapsed_time']:.2f}s")
                usage = result.get("usage", {})
                thread_tokens = usage.get("total_tokens", 0)
                total_tokens += thread_tokens
                print(f"  Tokens used: {thread_tokens}")
            else:
                failed += 1
                print(f"Status: FAILED")
                print(f"  Error: {result['error']}")
                print(f"  Elapsed time: {result['elapsed_time']:.2f}s")
        
        print("\n" + "=" * 80)
        print("OVERALL STATISTICS")
        print("=" * 80)
        print(f"Total requests: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Total tokens used: {total_tokens}")
        print(f"Total elapsed time: {overall_elapsed:.2f}s")
        print(f"Average time per request: {sum(r['elapsed_time'] for r in results) / len(results):.2f}s")
        
        if successful > 0:
            print(f"\nMulti-threaded example completed successfully!")
        else:
            print(f"\nAll requests failed!")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
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
                    print(f"Service stopped")
                else:
                    print(f"Failed to stop service: {response.text}")
            except Exception as e:
                print(f"Error stopping service: {e}")

        print("\n" + "=" * 80)
        print("Done!")


if __name__ == "__main__":
    main()
