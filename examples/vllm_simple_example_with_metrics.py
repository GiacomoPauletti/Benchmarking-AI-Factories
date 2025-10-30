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
from typing import Dict, Optional
from datetime import datetime


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


def fetch_metrics(server_url: str, service_id: str) -> Optional[Dict]:
    """
    Fetch Prometheus metrics from the vLLM service.
    
    Returns:
        Dict with parsed metrics or None if fetch failed
    """
    print(f"\n[*] Fetching metrics from service {service_id}...")
    api_base = f"{server_url}/api/v1"
    
    try:
        response = requests.get(
            f"{api_base}/vllm/{service_id}/metrics",
            timeout=10
        )
        
        if response.status_code == 200:
            # Metrics are returned in Prometheus text format
            metrics_text = response.text
            return parse_prometheus_metrics(metrics_text)
        else:
            error_data = response.json()
            print(f"[-] Failed to fetch metrics: {error_data.get('error', 'Unknown error')}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"[-] Request error fetching metrics: {e}")
        return None
    except Exception as e:
        print(f"[-] Error fetching metrics: {e}")
        return None


def save_metrics_to_file(metrics: Dict, label: str, service_id: str) -> str:
    """
    Save raw metrics to a text file.
    
    Args:
        metrics: Dict containing raw metrics text
        label: Label for the filename (e.g., "before", "after")
        service_id: Service ID for naming
    
    Returns:
        Path to the saved file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"metrics_{label}_{service_id}_{timestamp}.txt"
    filepath = os.path.join(os.path.dirname(__file__), filename)
    
    raw_metrics = metrics.get("raw", "")
    
    try:
        with open(filepath, 'w') as f:
            f.write(f"vLLM Metrics - {label.upper()}\n")
            f.write(f"Service ID: {service_id}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write("=" * 80 + "\n\n")
            f.write(raw_metrics)
        
        print(f"[+] Metrics saved to: {filepath}")
        return filepath
    except Exception as e:
        print(f"[-] Error saving metrics to file: {e}")
        return ""


def parse_prometheus_metrics(metrics_text: str) -> Dict:
    """
    Parse Prometheus text format metrics and extract key vLLM metrics.
    
    vLLM uses metrics like:
    - vllm:num_requests_running
    - vllm:num_requests_waiting  
    - vllm:kv_cache_usage_perc
    - vllm:prompt_tokens_total
    - vllm:generation_tokens_total
    - vllm:time_to_first_token_seconds (histogram)
    - vllm:time_per_output_token_seconds (histogram)
    - vllm:e2e_request_latency_seconds (histogram)
    
    Returns:
        Dict with parsed metrics
    """
    metrics = {
        "raw": metrics_text,
        "num_requests_running": None,
        "num_requests_waiting": None,
        "kv_cache_usage_perc": None,
        "prompt_tokens_total": None,
        "generation_tokens_total": None,
        "request_latency_sum": None
    }
    
    lines = metrics_text.strip().split('\n')
    
    for line in lines:
        # Skip comments and empty lines
        if line.startswith('#') or not line.strip():
            continue
        
        line = line.strip()
        if not line:
            continue
        
        # Parse metric lines (format: metric_name{labels} value or metric_name value)
        # Split by space to get the last element as value
        parts = line.split()
        if len(parts) < 2:
            continue
        
        # Last part is the value
        try:
            value = float(parts[-1])
        except (ValueError, IndexError):
            continue
        
        # Get metric name (first part before { or space)
        metric_part = parts[0]
        metric_name = metric_part.split('{')[0].strip()
        
        # Extract key metrics - using vLLM's actual metric names
        if metric_name == "vllm:num_requests_running":
            metrics["num_requests_running"] = int(value)
        
        elif metric_name == "vllm:num_requests_waiting":
            metrics["num_requests_waiting"] = int(value)
        
        elif metric_name == "vllm:kv_cache_usage_perc":
            metrics["kv_cache_usage_perc"] = round(value, 4)
        
        elif metric_name == "vllm:prompt_tokens_total":
            metrics["prompt_tokens_total"] = int(value)
        
        elif metric_name == "vllm:generation_tokens_total":
            metrics["generation_tokens_total"] = int(value)
        
        elif metric_name == "vllm:e2e_request_latency_seconds_sum":
            metrics["request_latency_sum"] = round(value, 2)
    
    return metrics


def display_metrics(metrics: Dict) -> None:
    """Display parsed metrics in a readable format."""
    print("\nPrometheus Metrics (vLLM):")
    print("=" * 50)
    
    has_metrics = False
    
    if metrics.get("num_requests_running") is not None:
        print(f"  Running Requests: {metrics['num_requests_running']}")
        has_metrics = True
    
    if metrics.get("num_requests_waiting") is not None:
        print(f"  Waiting Requests: {metrics['num_requests_waiting']}")
        has_metrics = True
    
    if metrics.get("kv_cache_usage_perc") is not None:
        print(f"  KV Cache Usage: {metrics['kv_cache_usage_perc']:.2%}")
        has_metrics = True
    
    if metrics.get("prompt_tokens_total") is not None:
        print(f"  Total Prompt Tokens: {metrics['prompt_tokens_total']}")
        has_metrics = True
    
    if metrics.get("generation_tokens_total") is not None:
        print(f"  Total Generation Tokens: {metrics['generation_tokens_total']}")
        has_metrics = True
    
    if metrics.get("request_latency_sum") is not None:
        print(f"  Total Request Latency: {metrics['request_latency_sum']}s")
        has_metrics = True
    
    if not has_metrics:
        print("  (No vLLM-specific metrics available yet)")
        # Print raw metrics for debugging - look for vllm metrics
        raw = metrics.get("raw", "")
        if raw:
            print("\n  Looking for vLLM metrics in response...")
            vllm_lines = [line for line in raw.split('\n') if 'vllm' in line.lower()]
            if vllm_lines:
                print(f"  Found {len(vllm_lines)} vLLM metric lines:")
                for line in vllm_lines[:10]:
                    print(f"    {line}")
            else:
                print("  (No vLLM metrics found in response)")
                print("\n  First 300 chars of raw metrics:")
                print("  " + "\n  ".join(raw[:300].split('\n')))
    
    print("=" * 50)


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
        metrics_before = fetch_metrics(server_url, service_id)
        if metrics_before:
            print("[+] Initial metrics retrieved")
            save_metrics_to_file(metrics_before, "before", service_id)
        
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
        metrics_after = fetch_metrics(server_url, service_id)
        
        if metrics_after:
            save_metrics_to_file(metrics_after, "after", service_id)
            display_metrics(metrics_after)
            
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
