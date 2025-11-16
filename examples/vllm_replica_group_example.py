#!/usr/bin/env python3
"""
vLLM Replica Group Example

This script demonstrates replica group deployment:
1. Create a service group with multiple vLLM replicas on the same node
2. Each replica runs on a dedicated GPU with a unique port
3. Send multiple prompts that are automatically load-balanced
4. Show which replica (port) handled each request
5. Demonstrate resilience with multiple replicas per node

Architecture:
- Single SLURM job per node
- Multiple vLLM processes within each job
- Each process bound to specific GPU(s) via CUDA_VISIBLE_DEVICES
- Each process listens on unique port (base_port + index)
- Replica IDs use composite format: "job_id:port"
"""

import requests
import time
import os
from threading import Thread
from queue import Queue
from utils.utils import wait_for_server, wait_for_service_group_ready


def send_prompt(thread_id, server_url, service_id, prompt, results_queue):
    """
    Send a prompt to the vLLM service group and store the result.
    
    Args:
        thread_id: Identifier for this thread
        server_url: Base server URL
        service_id: ID of the vLLM service group
        prompt: The prompt text to send
        results_queue: Queue to store results
    """
    api_base = f"{server_url}/api/v1"
    start_time = time.time()
    
    try:
        print(f"[Thread {thread_id}] Sending: '{prompt[:40]}...'")
        
        response = requests.post(
            f"{api_base}/vllm/{service_id}/prompt",
            json={
                "prompt": prompt,
                "max_tokens": 50,
                "temperature": 0.7
            },
            timeout=120
        )
        
        elapsed_time = time.time() - start_time
        
        if response.status_code != 200:
            results_queue.put({
                "thread_id": thread_id,
                "prompt": prompt,
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
                "elapsed_time": elapsed_time
            })
            return
        
        data = response.json()
        
        if not data.get("success"):
            results_queue.put({
                "thread_id": thread_id,
                "prompt": prompt,
                "success": False,
                "error": data.get("error", "Unknown error"),
                "elapsed_time": elapsed_time
            })
            return
        
        routed_to = data.get("routed_to", "unknown")
        results_queue.put({
            "thread_id": thread_id,
            "prompt": prompt,
            "success": True,
            "response": data.get("response", ""),
            "routed_to": routed_to,
            "usage": data.get("usage", {}),
            "elapsed_time": elapsed_time
        })
        
        print(f"[Thread {thread_id}] ✓ Completed in {elapsed_time:.2f}s -> replica {routed_to}")
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        results_queue.put({
            "thread_id": thread_id,
            "prompt": prompt,
            "success": False,
            "error": str(e),
            "elapsed_time": elapsed_time
        })
        print(f"[Thread {thread_id}] ✗ Error: {e}")


def main():
    """Run the replica group example."""
    print("=" * 80)
    print("vLLM Replica Group Example: Multiple Replicas with Shared Resources")
    print("=" * 80)
    
    # Configuration
    server_url = os.getenv("SERVER_URL", "http://localhost:8001")
    api_base = f"{server_url}/api/v1"
    
    service_id = None
    
    try:
        # Step 1: Check server
        if not wait_for_server(server_url):
            print("\n[-] Server is not running. Please start it first:")
            print("   docker compose up -d server")
            return
        
        # Step 2: Create vLLM service group with replicas
        print(f"\n[*] Creating vLLM replica group service...")
        print(f"    Configuration:")
        print(f"    - 1 node with 4 GPUs")
        print(f"    - 1 GPU per replica")
        print(f"    - 4 replicas total (all on same node)")
        print(f"    - Base port: 8001")
        print(f"    - Ports: 8001, 8002, 8003, 8004")
        
        response = requests.post(
            f"{api_base}/services",
            json={
                "recipe_name": "inference/vllm-replicas"
            },
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"[-] Failed to create service: {response.text}")
            return
        
        data = response.json()
        service_id = data["id"]
        print(f"\n[+] Service group created with ID: {service_id}")
        print(f"  Type: {data.get('type')}")
        print(f"  Nodes: {data.get('num_nodes', 'N/A')}")
        print(f"  Replicas per node: {data.get('replicas_per_node', 'N/A')}")
        print(f"  Total replicas: {data.get('total_replicas', 'N/A')}")
        
        # Show node jobs structure
        node_jobs = data.get("node_jobs", [])
        if node_jobs:
            print(f"\n  Node Jobs:")
            for nj in node_jobs:
                job_id = nj.get("job_id")
                node_idx = nj.get("node_index")
                replicas = nj.get("replicas", [])
                print(f"    - Job {job_id} (node {node_idx}):")
                for replica in replicas:
                    replica_id = replica.get("id")
                    port = replica.get("port")
                    gpu_id = replica.get("gpu_id")
                    status = replica.get("status")
                    print(f"      * Replica {replica_id} - GPU {gpu_id}, Port {port} ({status})")
        
        # Step 3: Wait for at least 2 replicas to be ready
        print(f"\n[*] Waiting for at least 2 replicas to be ready...")
        print(f"    (This may take several minutes as the model loads on each GPU)")
        time.sleep(2)  # Small delay for server to register replicas
        
        if not wait_for_service_group_ready(server_url, service_id, min_healthy=2, timeout=900):
            print("\n[-] Not enough replicas became ready in time")
            print("    You can still continue - the script will work with however many are healthy")
            # Don't return - continue with whatever replicas are available
        
        # Step 4: Send multiple prompts concurrently to demonstrate load balancing
        prompts = [
            "What is the capital of France?",
            "Explain machine learning in one sentence.",
            "What is 2+2?",
            "Name a famous scientist.",
            "What is the speed of light?",
            "What color is the sky?",
            "Who wrote Romeo and Juliet?",
            "What is the largest planet?",
        ]
        
        print(f"\n[*] Sending {len(prompts)} prompts CONCURRENTLY to demonstrate load balancing...")
        print("    Each replica handles requests on its dedicated GPU")
        print("    All requests sent at nearly the same time (like multiple clients)")
        print("=" * 80)
        
        # Launch all requests concurrently
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
            # Very small stagger to simulate "almost same time"
            time.sleep(0.05)
        
        # Wait for all threads to complete
        print(f"\n[*] Waiting for all {len(prompts)} requests to complete...")
        for thread in threads:
            thread.join()
        
        overall_elapsed = time.time() - overall_start
        print(f"\n[+] All requests completed in {overall_elapsed:.2f}s")
        
        # Collect results
        results = []
        while not results_queue.empty():
            results.append(results_queue.get())
        
        # Sort by thread ID for display
        results.sort(key=lambda x: x["thread_id"])
        
        # Step 5: Display detailed results
        print("\n" + "=" * 80)
        print("Detailed Results:")
        print("=" * 80)
        
        for result in results:
            thread_id = result["thread_id"]
            prompt = result["prompt"]
            
            if result["success"]:
                routed_to = result["routed_to"]
                response = result["response"]
                elapsed = result["elapsed_time"]
                usage = result.get("usage", {})
                
                # Parse composite replica ID to show port
                if ":" in routed_to:
                    job_id, port = routed_to.split(":", 1)
                    replica_label = f"port {port}"
                else:
                    replica_label = routed_to
                
                print(f"\n[Request {thread_id}] {prompt}")
                print(f"  → Routed to: {routed_to} ({replica_label})")
                print(f"  → Response: {response[:80]}...")
                print(f"  → Time: {elapsed:.2f}s | Tokens: {usage.get('total_tokens', 'N/A')}")
            else:
                print(f"\n[Request {thread_id}] {prompt}")
                print(f"  → FAILED: {result['error']}")
                print(f"  → Time: {result['elapsed_time']:.2f}s")
        
        # Step 6: Show load balancing statistics
        print("\n" + "=" * 80)
        print("Load Balancing Summary:")
        print("=" * 80)
        
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        
        print(f"\nTotal requests: {len(prompts)}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")
        print(f"Overall time: {overall_elapsed:.2f}s")
        
        if successful:
            avg_time = sum(r["elapsed_time"] for r in successful) / len(successful)
            print(f"Average response time: {avg_time:.2f}s")
            
            # Count requests per replica
            replica_counts = {}
            for result in successful:
                replica = result["routed_to"]
                replica_counts[replica] = replica_counts.get(replica, 0) + 1
            
            print(f"\nRequests per replica:")
            for replica, count in sorted(replica_counts.items()):
                # Parse to show port more clearly
                if ":" in replica:
                    job_id, port = replica.split(":", 1)
                    percentage = (count / len(successful)) * 100
                    print(f"  Replica {replica} (port {port}): {count} requests ({percentage:.1f}%)")
                else:
                    print(f"  Replica {replica}: {count} requests")
            
            # Check distribution
            if len(replica_counts) > 1:
                print(f"\n[+] Load balancing is working! Requests were distributed across {len(replica_counts)} replicas.")
                print(f"    All replicas are running on the same node but using different GPUs and ports.")
                print(f"    Concurrent requests were automatically routed to available replicas.")
            else:
                print(f"\n[!] All requests went to the same replica.")
                print(f"    This might happen if only 1 replica is healthy.")
        
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

        print("\n" + "=" * 80)
        print("Done!")
        print("=" * 80)


if __name__ == "__main__":
    main()
