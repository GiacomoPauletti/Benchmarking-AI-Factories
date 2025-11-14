#!/usr/bin/env python3
"""
Simple Client Service Example: Basic Benchmark Workflow

This script demonstrates the basic client service workflow:
1. Connect to the client service
2. Create a client group for benchmarking
3. Check the status until clients are ready
4. Trigger the benchmark execution
5. Monitor progress and retrieve metrics
6. Clean up resources

Prerequisites:
- Client service running: docker compose up -d client
- SSH access to HPC cluster configured (SSH agent with keys)
- Server service running with at least one active AI service
"""

import requests
import time
import os
import sys


def check_client_service(client_url: str) -> bool:
    """Check if the client service is running and healthy."""
    try:
        response = requests.get(f"{client_url}/api/v1/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Client Service is healthy (uptime: {data['uptime']:.1f}s)")
            return True
        return False
    except requests.RequestException as e:
        print(f"✗ Client Service is not reachable: {e}")
        return False


def create_client_group(client_url: str, benchmark_id: int, num_clients: int, time_limit: int) -> bool:
    """Create a new client group for benchmarking."""
    try:
        print(f"\n[1/5] Creating client group {benchmark_id}...")
        print(f"      - Number of clients: {num_clients}")
        print(f"      - Time limit: {time_limit} minutes")
        
        response = requests.post(
            f"{client_url}/api/v1/client-groups/{benchmark_id}",
            json={
                "num_clients": num_clients,
                "time_limit": time_limit
            },
            timeout=30
        )
        
        if response.status_code == 201:
            data = response.json()
            print(f"✓ Client group created: {data['message']}")
            return True
        elif response.status_code == 409:
            print(f"✗ Client group {benchmark_id} already exists. Choose a different ID.")
            return False
        else:
            print(f"✗ Failed to create client group: {response.status_code} - {response.text}")
            return False
    except requests.RequestException as e:
        print(f"✗ Request failed: {e}")
        return False


def wait_for_clients_ready(client_url: str, benchmark_id: int, timeout: int = 300) -> bool:
    """Wait for the client processes to register with the client service."""
    print(f"\n[2/5] Waiting for client processes to register (timeout: {timeout}s)...")
    print("      This may take a few minutes as the SLURM job starts...")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(
                f"{client_url}/api/v1/client-groups/{benchmark_id}",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                info = data.get("info", {})
                client_address = info.get("client_address")
                status = info.get("status", "pending")
                
                if status != last_status:
                    print(f"      Status: {status}")
                    last_status = status
                
                if client_address:
                    print(f"✓ Clients registered at: {client_address}")
                    return True
            
            time.sleep(10)  # Check every 10 seconds
            
        except requests.RequestException as e:
            print(f"      Warning: {e}")
            time.sleep(10)
    
    print(f"✗ Timeout: Clients did not register within {timeout}s")
    return False


def run_benchmark(client_url: str, benchmark_id: int) -> bool:
    """Trigger the benchmark execution."""
    try:
        print(f"\n[3/5] Triggering benchmark execution...")
        
        response = requests.post(
            f"{client_url}/api/v1/client-groups/{benchmark_id}/run",
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Benchmark started")
            print(f"      Results: {data.get('results', [])}")
            return True
        elif response.status_code == 404:
            print(f"✗ Client group not ready or not found")
            return False
        else:
            print(f"✗ Failed to run benchmark: {response.status_code} - {response.text}")
            return False
    except requests.RequestException as e:
        print(f"✗ Request failed: {e}")
        return False


def monitor_metrics(client_url: str, benchmark_id: int, duration: int = 60):
    """Monitor the benchmark metrics."""
    print(f"\n[4/5] Monitoring metrics for {duration} seconds...")
    print("      Press Ctrl+C to stop monitoring early\n")
    
    start_time = time.time()
    
    try:
        while time.time() - start_time < duration:
            try:
                response = requests.get(
                    f"{client_url}/api/v1/client-groups/{benchmark_id}/metrics",
                    timeout=10
                )
                
                if response.status_code == 200:
                    # Parse Prometheus metrics for display
                    metrics_text = response.text
                    
                    # Extract key metrics (simple parsing)
                    lines = metrics_text.split('\n')
                    metrics = {}
                    for line in lines:
                        if line and not line.startswith('#'):
                            parts = line.split()
                            if len(parts) >= 2:
                                metric_name = parts[0].split('{')[0]
                                try:
                                    metric_value = float(parts[-1])
                                    metrics[metric_name] = metric_value
                                except ValueError:
                                    pass
                    
                    # Display key metrics
                    elapsed = time.time() - start_time
                    print(f"\r      Elapsed: {elapsed:.0f}s | Metrics: {len(metrics)} total", end='', flush=True)
                    
                    time.sleep(5)  # Update every 5 seconds
                else:
                    print(f"\n      Warning: Could not fetch metrics ({response.status_code})")
                    time.sleep(10)
                    
            except requests.RequestException as e:
                print(f"\n      Warning: {e}")
                time.sleep(10)
    
    except KeyboardInterrupt:
        print("\n      Monitoring stopped by user")
    
    print(f"\n✓ Monitoring complete")


def get_prometheus_targets(client_url: str):
    """Get the Prometheus targets for all client groups."""
    try:
        print(f"\n[*] Prometheus targets:")
        response = requests.get(
            f"{client_url}/api/v1/client-groups/targets",
            timeout=10
        )
        
        if response.status_code == 200:
            targets = response.json()
            if targets:
                for target in targets:
                    labels = target.get("labels", {})
                    print(f"      - Benchmark {labels.get('benchmark_id')}: {target.get('targets', [])[0]} ({labels.get('num_clients')} clients)")
            else:
                print("      No active targets")
        else:
            print(f"      Could not fetch targets: {response.status_code}")
    except requests.RequestException as e:
        print(f"      Error: {e}")


def cleanup_client_group(client_url: str, benchmark_id: int):
    """Delete the client group and clean up resources."""
    try:
        print(f"\n[5/5] Cleaning up client group...")
        
        response = requests.delete(
            f"{client_url}/api/v1/client-groups/{benchmark_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✓ Client group deleted")
            print(f"      Note: SLURM job may still be running. Cancel manually if needed:")
            print(f"      ssh meluxina 'scancel <job_id>'")
        else:
            print(f"      Warning: Could not delete client group: {response.status_code}")
    except requests.RequestException as e:
        print(f"      Error: {e}")


def list_all_groups(client_url: str):
    """List all active client groups."""
    try:
        response = requests.get(
            f"{client_url}/api/v1/client-groups",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            groups = data.get("groups", [])
            if groups:
                print(f"\n[*] Active client groups: {groups}")
            else:
                print(f"\n[*] No active client groups")
        else:
            print(f"\n[*] Could not list groups: {response.status_code}")
    except requests.RequestException as e:
        print(f"\n[*] Error listing groups: {e}")


def main():
    """Run the simple client service example."""
    print("=" * 70)
    print("Client Service Example: Simple Benchmark Workflow")
    print("=" * 70)
    
    # Configuration
    client_url = os.getenv("CLIENT_URL", "http://localhost:8002")
    benchmark_id = int(os.getenv("BENCHMARK_ID", str(int(time.time()))))  # Use timestamp as default
    num_clients = int(os.getenv("NUM_CLIENTS", "10"))
    time_limit = int(os.getenv("TIME_LIMIT", "10"))  # SLURM time limit in minutes
    monitor_duration = int(os.getenv("MONITOR_DURATION", "60"))  # Monitor for 60 seconds
    
    print(f"\nConfiguration:")
    print(f"  - Client Service URL: {client_url}")
    print(f"  - Benchmark ID: {benchmark_id}")
    print(f"  - Number of clients: {num_clients}")
    print(f"  - Time limit: {time_limit} minutes")
    print(f"  - Monitor duration: {monitor_duration} seconds")
    print()
    
    # Step 0: Check if client service is running
    if not check_client_service(client_url):
        print("\n[!] Please start the client service first:")
        print("    docker compose up -d client")
        sys.exit(1)
    
    # List existing groups
    list_all_groups(client_url)
    
    try:
        # Step 1: Create client group
        if not create_client_group(client_url, benchmark_id, num_clients, time_limit):
            sys.exit(1)
        
        # Step 2: Wait for clients to be ready
        if not wait_for_clients_ready(client_url, benchmark_id, timeout=300):
            print("\n[!] Clients failed to register. Check SLURM logs:")
            print(f"    ssh meluxina 'squeue -u $USER'")
            print(f"    ssh meluxina 'cat ~/slurm-*.out'")
            cleanup_client_group(client_url, benchmark_id)
            sys.exit(1)
        
        # Step 3: Run the benchmark
        if not run_benchmark(client_url, benchmark_id):
            cleanup_client_group(client_url, benchmark_id)
            sys.exit(1)
        
        # Step 4: Monitor metrics
        monitor_metrics(client_url, benchmark_id, duration=monitor_duration)
        
        # Show Prometheus targets
        get_prometheus_targets(client_url)
        
        # Step 5: Cleanup
        cleanup_client_group(client_url, benchmark_id)
        
        print("\n" + "=" * 70)
        print("✓ Example completed successfully!")
        print("=" * 70)
        print("\nNext steps:")
        print("  - View metrics in Grafana: http://localhost:3000")
        print("  - Query Prometheus: http://localhost:9090")
        print("  - Check OpenAPI docs: http://localhost:8002/docs")
        
    except KeyboardInterrupt:
        print("\n\n[!] Interrupted by user")
        cleanup_client_group(client_url, benchmark_id)
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}")
        cleanup_client_group(client_url, benchmark_id)
        sys.exit(1)


if __name__ == "__main__":
    main()
