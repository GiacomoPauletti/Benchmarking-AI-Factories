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
from utils.server_utils import wait_for_server, wait_for_service_group_ready


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
        
        # Step 4: Send multiple prompts to demonstrate load balancing
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
        
        print(f"\n[*] Sending {len(prompts)} prompts to demonstrate load balancing...")
        print("    Each replica handles requests on its dedicated GPU")
        print("=" * 80)
        
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
                    
                    # Parse composite replica ID to show port
                    if ":" in routed_to:
                        job_id, port = routed_to.split(":", 1)
                        replica_label = f"{routed_to} (port {port})"
                    else:
                        replica_label = routed_to
                    
                    print(f"[+] Response from replica {replica_label}:")
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
        print("\n" + "=" * 80)
        print("Load Balancing Summary:")
        print("=" * 80)
        
        successful = [r for r in results if r["success"]]
        replica_counts = {}
        for result in successful:
            replica = result["replica"]
            replica_counts[replica] = replica_counts.get(replica, 0) + 1
        
        print(f"\nTotal requests: {len(prompts)}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(prompts) - len(successful)}")
        
        if successful:
            print(f"\nRequests per replica (by port):")
            for replica, count in sorted(replica_counts.items()):
                # Parse to show port more clearly
                if ":" in replica:
                    job_id, port = replica.split(":", 1)
                    print(f"  {replica} (port {port}): {count} requests")
                else:
                    print(f"  {replica}: {count} requests")
            
            # Check distribution
            if len(replica_counts) > 1:
                print(f"\n[+] Load balancing is working! Requests were distributed across {len(replica_counts)} replicas.")
                print(f"    All replicas are running on the same node but using different GPUs and ports.")
            else:
                print(f"\n[!] All requests went to the same replica.")
                print(f"    This might happen if only 1 replica is healthy.")
        
        # Step 6: Show replica group benefits
        print("\n" + "=" * 80)
        print("Replica Group Benefits:")
        print("=" * 80)
        print("✓ Resource efficiency: Single SLURM job manages multiple replicas")
        print("✓ Better GPU utilization: One replica per GPU (4 GPUs = 4 replicas)")
        print("✓ Reduced overhead: No need for separate SLURM jobs per replica")
        print("✓ Fault tolerance: If one replica fails, others continue running")
        print("✓ Load balancing: Requests automatically distributed across replicas")
        
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
