"""
Prometheus metrics utilities for fetching, parsing, and displaying metrics.
"""

import requests
import os
from typing import Dict, Optional
from datetime import datetime


def fetch_metrics(server_url: str, service_id: str, service_type: str = "vllm", timeout: int = 10) -> Optional[Dict]:
    """
    Fetch Prometheus metrics from a service.
    
    Args:
        server_url: Base URL of the server (e.g., "http://localhost:8001")
        service_id: Service ID (SLURM job ID)
        service_type: Type of service - "vllm" or "qdrant"
        timeout: Request timeout in seconds
        
    Returns:
        Dict with parsed metrics or None if fetch failed
    """
    print(f"\n[*] Fetching metrics from service {service_id}...")
    api_base = f"{server_url}/api/v1"
    
    # Use general service metrics endpoint
    endpoint = f"{api_base}/services/{service_id}/metrics"
    
    # Service-specific endpoints (commented out for testing):
    # if service_type.lower() == "vllm":
    #     endpoint = f"{api_base}/vllm/{service_id}/metrics"
    #     parser = parse_vllm_metrics
    # elif service_type.lower() in ["qdrant", "vector-db"]:
    #     endpoint = f"{api_base}/vector-db/{service_id}/metrics"
    #     parser = parse_qdrant_metrics
    # else:
    #     print(f"[-] Unknown service type: {service_type}")
    #     return None
    
    # Determine parser based on service type
    if service_type.lower() == "vllm":
        parser = parse_vllm_metrics
    elif service_type.lower() in ["qdrant", "vector-db"]:
        parser = parse_qdrant_metrics
    else:
        print(f"[-] Unknown service type: {service_type}")
        return None
    
    try:
        response = requests.get(endpoint, timeout=timeout)
        
        if response.status_code == 200:
            # Metrics are returned in Prometheus text format
            metrics_text = response.text
            return parser(metrics_text)
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


def save_metrics_to_file(metrics: Dict, label: str, service_id: str, service_type: str = "vllm") -> str:
    """
    Save raw metrics to a text file.
    
    Args:
        metrics: Dict containing raw metrics text
        label: Label for the filename (e.g., "before", "after")
        service_id: Service ID for naming
        service_type: Type of service - "vllm" or "qdrant"
    
    Returns:
        Path to the saved file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{service_type}_metrics_{label}_{service_id}_{timestamp}.txt"
    
    # Save to examples directory (parent of utils)
    examples_dir = os.path.dirname(os.path.dirname(__file__))
    filepath = os.path.join(examples_dir, filename)
    
    raw_metrics = metrics.get("raw", "")
    
    try:
        with open(filepath, 'w') as f:
            f.write(f"{service_type.upper()} Metrics - {label.upper()}\n")
            f.write(f"Service ID: {service_id}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write("=" * 80 + "\n\n")
            f.write(raw_metrics)
        
        print(f"[+] Metrics saved to: {filepath}")
        return filepath
    except Exception as e:
        print(f"[-] Error saving metrics to file: {e}")
        return ""


def parse_vllm_metrics(metrics_text: str) -> Dict:
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
    
    Args:
        metrics_text: Raw Prometheus text format metrics
        
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


def parse_qdrant_metrics(metrics_text: str) -> Dict:
    """
    Parse Prometheus text format metrics and extract key Qdrant metrics.
    
    Qdrant exposes metrics like:
    - app_info - Application information
    - collections_total - Total number of collections
    - collections_vector_total - Total number of vectors
    - rest_responses_total - Total REST API responses
    - rest_responses_duration_seconds - Response time metrics
    
    Args:
        metrics_text: Raw Prometheus text format metrics
        
    Returns:
        Dict with parsed metrics
    """
    metrics = {
        "raw": metrics_text,
        "collections_total": None,
        "collections_vector_total": None,
        "rest_responses_total": None,
        "rest_responses_ok": None,
        "rest_responses_duration_sum": None,
        "app_version": None
    }
    
    lines = metrics_text.strip().split('\n')
    
    for line in lines:
        # Skip comments and empty lines
        if line.startswith('#') or not line.strip():
            continue
        
        line = line.strip()
        if not line:
            continue
        
        # Parse metric lines
        parts = line.split()
        if len(parts) < 2:
            continue
        
        # Last part is the value
        try:
            value = float(parts[-1])
        except (ValueError, IndexError):
            continue
        
        # Get metric name
        metric_part = parts[0]
        metric_name = metric_part.split('{')[0].strip()
        
        # Extract key metrics
        if metric_name == "collections_total":
            metrics["collections_total"] = int(value)
        elif metric_name == "collections_vector_total":
            metrics["collections_vector_total"] = int(value)
        elif metric_name == "rest_responses_total":
            # Try to extract status from labels
            if 'status="ok"' in line or 'status="200"' in line:
                metrics["rest_responses_ok"] = int(value)
            # Sum all responses
            if metrics["rest_responses_total"] is None:
                metrics["rest_responses_total"] = 0
            metrics["rest_responses_total"] += int(value)
        elif metric_name == "rest_responses_duration_seconds_sum":
            metrics["rest_responses_duration_sum"] = round(value, 2)
        elif metric_name == "app_info":
            # Try to extract version from labels
            if 'version=' in line:
                version_start = line.find('version="') + 9
                version_end = line.find('"', version_start)
                if version_end > version_start:
                    metrics["app_version"] = line[version_start:version_end]
    
    return metrics


def display_vllm_metrics(metrics: Dict) -> None:
    """
    Display parsed vLLM metrics in a readable format.
    
    Args:
        metrics: Parsed metrics dict from parse_vllm_metrics()
    """
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
        _display_debug_metrics(metrics.get("raw", ""), "vllm")
    
    print("=" * 50)


def display_qdrant_metrics(metrics: Dict) -> None:
    """
    Display parsed Qdrant metrics in a readable format.
    
    Args:
        metrics: Parsed metrics dict from parse_qdrant_metrics()
    """
    print("\nPrometheus Metrics (Qdrant):")
    print("=" * 50)
    
    has_metrics = False
    
    if metrics.get("app_version") is not None:
        print(f"  Qdrant Version: {metrics['app_version']}")
        has_metrics = True
    
    if metrics.get("collections_total") is not None:
        print(f"  Total Collections: {metrics['collections_total']}")
        has_metrics = True
    
    if metrics.get("collections_vector_total") is not None:
        print(f"  Total Vectors: {metrics['collections_vector_total']}")
        has_metrics = True
    
    if metrics.get("rest_responses_total") is not None:
        print(f"  Total REST Responses: {metrics['rest_responses_total']}")
        has_metrics = True
    
    if metrics.get("rest_responses_ok") is not None:
        print(f"  Successful Responses: {metrics['rest_responses_ok']}")
        has_metrics = True
    
    if metrics.get("rest_responses_duration_sum") is not None:
        print(f"  Total Response Time: {metrics['rest_responses_duration_sum']}s")
        has_metrics = True
    
    if not has_metrics:
        print("  (No Qdrant-specific metrics available yet)")
        _display_debug_metrics(metrics.get("raw", ""), "qdrant")
    
    print("=" * 50)


def _display_debug_metrics(raw_metrics: str, service_type: str) -> None:
    """
    Display debug information when no metrics are found.
    
    Args:
        raw_metrics: Raw Prometheus text
        service_type: Type of service for filtering
    """
    if not raw_metrics:
        return
    
    print(f"\n  Looking for {service_type} metrics in response...")
    
    # Filter for relevant lines
    if service_type == "vllm":
        relevant_lines = [line for line in raw_metrics.split('\n') if 'vllm' in line.lower()]
    else:
        relevant_lines = [line for line in raw_metrics.split('\n') 
                         if any(k in line for k in ['collection', 'app_info', 'rest_response'])]
    
    if relevant_lines:
        print(f"  Found {len(relevant_lines)} {service_type} metric lines:")
        for line in relevant_lines[:10]:
            print(f"    {line}")
    else:
        print(f"  (No {service_type} metrics found in response)")
        print("\n  First 300 chars of raw metrics:")
        print("  " + "\n  ".join(raw_metrics[:300].split('\n')))
