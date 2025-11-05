#!/usr/bin/env python3
"""
Query Metrics Example
=====================

This example demonstrates how to query metrics from Prometheus for analysis.

Query patterns:
1. Real-time queries (instant values)
2. Range queries (time series data)
3. Aggregations and calculations
4. Service-specific metrics (vLLM, Qdrant)
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
import pandas as pd


class MetricsQuery:
    """Helper class for querying Prometheus metrics."""
    
    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        self.prometheus_url = prometheus_url.rstrip('/')
    
    def query_instant(self, query: str) -> Dict[str, Any]:
        """
        Query current metric value (instant query).
        
        Args:
            query: PromQL query string
            
        Returns:
            Query results
            
        Example:
            query_instant("up{job='3700737'}")
        """
        response = requests.post(
            f"{self.prometheus_url}/api/v1/query",
            data={"query": query}
        )
        response.raise_for_status()
        return response.json()
    
    def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s"
    ) -> Dict[str, Any]:
        """
        Query metric over a time range.
        
        Args:
            query: PromQL query string
            start: Start time
            end: End time
            step: Resolution (e.g., "15s", "1m", "5m")
            
        Returns:
            Time series data
            
        Example:
            query_range(
                "rate(vllm:request_success_total[1m])",
                datetime.now() - timedelta(minutes=10),
                datetime.now()
            )
        """
        response = requests.post(
            f"{self.prometheus_url}/api/v1/query_range",
            data={
                "query": query,
                "start": start.timestamp(),
                "end": end.timestamp(),
                "step": step
            }
        )
        response.raise_for_status()
        return response.json()
    
    def get_service_health(self, service_id: str) -> bool:
        """Check if a service is up."""
        result = self.query_instant(f'up{{job="{service_id}"}}')
        
        if result["data"]["result"]:
            value = float(result["data"]["result"][0]["value"][1])
            return value == 1.0
        return False
    
    def get_vllm_request_rate(self, service_id: str, window: str = "5m") -> float:
        """Get vLLM request rate (requests per second)."""
        result = self.query_instant(
            f'rate(vllm:request_success_total{{job="{service_id}"}}[{window}])'
        )
        
        if result["data"]["result"]:
            return float(result["data"]["result"][0]["value"][1])
        return 0.0
    
    def get_vllm_latency_percentile(
        self,
        service_id: str,
        percentile: float = 0.95
    ) -> float:
        """
        Get vLLM latency percentile (P50, P95, P99).
        
        Args:
            service_id: Service/job ID
            percentile: 0.5 for P50, 0.95 for P95, 0.99 for P99
        """
        result = self.query_instant(
            f'histogram_quantile({percentile}, '
            f'rate(vllm:e2e_request_latency_seconds_bucket{{job="{service_id}"}}[5m]))'
        )
        
        if result["data"]["result"]:
            return float(result["data"]["result"][0]["value"][1])
        return 0.0
    
    def get_vllm_gpu_utilization(self, service_id: str) -> float:
        """Get vLLM GPU cache utilization percentage."""
        result = self.query_instant(
            f'vllm:gpu_cache_usage_perc{{job="{service_id}"}}'
        )
        
        if result["data"]["result"]:
            return float(result["data"]["result"][0]["value"][1])
        return 0.0
    
    def get_qdrant_collection_size(self, service_id: str, collection: str) -> int:
        """Get Qdrant collection vector count."""
        result = self.query_instant(
            f'app_info{{service="qdrant",job="{service_id}",collection="{collection}"}}'
        )
        
        if result["data"]["result"]:
            return int(result["data"]["result"][0]["value"][1])
        return 0
    
    def export_time_series_to_csv(
        self,
        query: str,
        start: datetime,
        end: datetime,
        output_file: str,
        step: str = "15s"
    ):
        """
        Export time series data to CSV for analysis.
        
        Args:
            query: PromQL query
            start: Start time
            end: End time
            output_file: Output CSV file path
            step: Time resolution
        """
        result = self.query_range(query, start, end, step)
        
        # Convert to pandas DataFrame
        rows = []
        for series in result["data"]["result"]:
            metric_labels = series["metric"]
            for timestamp, value in series["values"]:
                row = {
                    "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                    "value": float(value),
                    **metric_labels
                }
                rows.append(row)
        
        df = pd.DataFrame(rows)
        df.to_csv(output_file, index=False)
        print(f"Exported {len(rows)} data points to {output_file}")
        return df


def example_queries():
    """Run example queries against Prometheus."""
    metrics = MetricsQuery()
    
    print("=" * 70)
    print("Prometheus Metrics Query Examples")
    print("=" * 70)
    print()
    
    # Example 1: Check all targets
    print("[1] All monitored targets:")
    result = metrics.query_instant("up")
    for item in result["data"]["result"]:
        job = item["metric"].get("job", "unknown")
        instance = item["metric"].get("instance", "unknown")
        status = "UP" if float(item["value"][1]) == 1.0 else "DOWN"
        print(f"  {job} @ {instance}: {status}")
    print()
    
    # Example 2: Service-specific health
    service_id = input("Enter service ID to query (or press Enter to skip): ").strip()
    if service_id:
        print(f"\n[2] Service {service_id} metrics:")
        
        is_up = metrics.get_service_health(service_id)
        print(f"  Health: {'UP' if is_up else 'DOWN'}")
        
        if is_up:
            # vLLM metrics (if it's a vLLM service)
            try:
                request_rate = metrics.get_vllm_request_rate(service_id)
                print(f"  Request rate: {request_rate:.2f} req/s")
                
                p50 = metrics.get_vllm_latency_percentile(service_id, 0.50)
                p95 = metrics.get_vllm_latency_percentile(service_id, 0.95)
                p99 = metrics.get_vllm_latency_percentile(service_id, 0.99)
                print(f"  Latency P50: {p50*1000:.2f}ms")
                print(f"  Latency P95: {p95*1000:.2f}ms")
                print(f"  Latency P99: {p99*1000:.2f}ms")
                
                gpu_util = metrics.get_vllm_gpu_utilization(service_id)
                print(f"  GPU utilization: {gpu_util:.1f}%")
            except Exception as e:
                print(f"  (vLLM metrics not available: {e})")
        print()
    
    # Example 3: Time series export
    print("[3] Export time series data:")
    print("  Example: Export last 5 minutes of request rates to CSV")
    
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=5)
    
    if service_id:
        try:
            metrics.export_time_series_to_csv(
                query=f'rate(vllm:request_success_total{{job="{service_id}"}}[1m])',
                start=start_time,
                end=end_time,
                output_file="./metrics_output/request_rate_time_series.csv",
                step="15s"
            )
        except Exception as e:
            print(f"  Could not export: {e}")
    print()
    
    # Example 4: Custom queries
    print("[4] Custom PromQL queries:")
    print("  Examples:")
    print("    - up")
    print("    - vllm:request_success_total")
    print(f'    - rate(vllm:request_success_total{{job="{service_id or "JOB_ID"}"}}[5m])')
    print("    - sum(rate(vllm:request_success_total[5m])) by (job)")
    print()
    
    custom_query = input("Enter custom PromQL query (or press Enter to skip): ").strip()
    if custom_query:
        try:
            result = metrics.query_instant(custom_query)
            print(f"\n  Results:")
            print(json.dumps(result["data"]["result"], indent=2))
        except Exception as e:
            print(f"  Error: {e}")
    print()
    
    print("=" * 70)
    print("Tip: Access Prometheus UI at http://localhost:9090 for interactive queries")
    print("=" * 70)


if __name__ == "__main__":
    try:
        example_queries()
    except Exception as e:
        print(f"Error: {e}")
