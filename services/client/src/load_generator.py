"""
Load Generator for vLLM Services

Async HTTP client that generates load against vLLM endpoints.
Supports configurable request rates, prompt datasets, and metrics collection.
"""

import asyncio
import aiohttp
import time
import logging
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import random

logger = logging.getLogger(__name__)


@dataclass
class LoadTestConfig:
    """Configuration for a load test run."""
    target_url: str
    num_clients: int
    requests_per_second: float
    duration_seconds: int
    prompts: List[str]
    max_tokens: int = 100
    temperature: float = 0.7
    model: str = "meta-llama/Llama-2-7b-hf"  # Default, can be overridden


@dataclass
class RequestMetrics:
    """Metrics for a single request."""
    timestamp: float
    latency_ms: float
    status_code: int
    success: bool
    error: Optional[str] = None
    tokens_generated: Optional[int] = None


@dataclass
class LoadTestResults:
    """Aggregated results from a load test."""
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    requests_per_second: float
    total_duration_seconds: float
    error_rate: float
    errors_by_type: Dict[str, int]


class LoadGenerator:
    """Async load generator for vLLM services."""
    
    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.metrics: List[RequestMetrics] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        
    async def send_request(self, session: aiohttp.ClientSession, prompt: str) -> RequestMetrics:
        """Send a single request to the vLLM endpoint."""
        request_start = time.time()
        
        # Prepare vLLM API request
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        
        try:
            async with session.post(
                f"{self.config.target_url}/v1/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                latency = (time.time() - request_start) * 1000  # Convert to ms
                
                if response.status == 200:
                    data = await response.json()
                    tokens = len(data.get("choices", [{}])[0].get("text", "").split())
                    
                    return RequestMetrics(
                        timestamp=request_start,
                        latency_ms=latency,
                        status_code=response.status,
                        success=True,
                        tokens_generated=tokens
                    )
                else:
                    error_text = await response.text()
                    return RequestMetrics(
                        timestamp=request_start,
                        latency_ms=latency,
                        status_code=response.status,
                        success=False,
                        error=f"HTTP {response.status}: {error_text[:100]}"
                    )
                    
        except asyncio.TimeoutError:
            latency = (time.time() - request_start) * 1000
            return RequestMetrics(
                timestamp=request_start,
                latency_ms=latency,
                status_code=0,
                success=False,
                error="Request timeout"
            )
        except Exception as e:
            latency = (time.time() - request_start) * 1000
            return RequestMetrics(
                timestamp=request_start,
                latency_ms=latency,
                status_code=0,
                success=False,
                error=str(e)
            )
    
    async def worker(self, worker_id: int, session: aiohttp.ClientSession, rate_limiter: asyncio.Semaphore):
        """Worker that sends requests at the configured rate."""
        logger.info(f"Worker {worker_id} started")
        
        while time.time() < self.end_time:
            # Wait for rate limiter
            async with rate_limiter:
                # Select random prompt
                prompt = random.choice(self.config.prompts)
                
                # Send request
                metric = await self.send_request(session, prompt)
                self.metrics.append(metric)
                
                # Log progress periodically
                if len(self.metrics) % 100 == 0:
                    logger.debug(f"Sent {len(self.metrics)} requests")
    
    async def rate_limiter_task(self, semaphore: asyncio.Semaphore):
        """Release semaphore at the configured rate."""
        interval = 1.0 / self.config.requests_per_second
        
        while time.time() < self.end_time:
            semaphore.release()
            await asyncio.sleep(interval)
    
    async def run(self) -> LoadTestResults:
        """Execute the load test."""
        logger.info(f"Starting load test: {self.config.num_clients} clients, "
                   f"{self.config.requests_per_second} RPS, "
                   f"{self.config.duration_seconds}s duration")
        
        self.start_time = time.time()
        self.end_time = self.start_time + self.config.duration_seconds
        
        # Create semaphore for rate limiting (start with available slots)
        rate_limiter = asyncio.Semaphore(0)
        
        # Create aiohttp session with connection pooling
        connector = aiohttp.TCPConnector(limit=self.config.num_clients)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Start rate limiter task
            rate_task = asyncio.create_task(self.rate_limiter_task(rate_limiter))
            
            # Start worker tasks
            workers = [
                asyncio.create_task(self.worker(i, session, rate_limiter))
                for i in range(self.config.num_clients)
            ]
            
            # Wait for all workers to complete
            await asyncio.gather(*workers, return_exceptions=True)
            rate_task.cancel()
            
            try:
                await rate_task
            except asyncio.CancelledError:
                pass
        
        # Calculate results
        results = self._calculate_results()
        logger.info(f"Load test completed: {results.total_requests} requests, "
                   f"{results.avg_latency_ms:.2f}ms avg latency, "
                   f"{results.error_rate:.2%} error rate")
        
        return results
    
    def _calculate_results(self) -> LoadTestResults:
        """Calculate aggregated metrics from collected data."""
        if not self.metrics:
            return LoadTestResults(
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                avg_latency_ms=0,
                p50_latency_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                min_latency_ms=0,
                max_latency_ms=0,
                requests_per_second=0,
                total_duration_seconds=0,
                error_rate=0,
                errors_by_type={}
            )
        
        total_requests = len(self.metrics)
        successful = [m for m in self.metrics if m.success]
        failed = [m for m in self.metrics if not m.success]
        
        latencies = sorted([m.latency_ms for m in self.metrics])
        
        # Calculate percentiles
        def percentile(data, p):
            if not data:
                return 0
            k = (len(data) - 1) * p
            f = int(k)
            c = int(k) + 1
            if c >= len(data):
                return data[-1]
            return data[f] + (k - f) * (data[c] - data[f])
        
        # Count errors by type
        errors_by_type = defaultdict(int)
        for m in failed:
            error_key = m.error if m.error else f"HTTP {m.status_code}"
            errors_by_type[error_key] += 1
        
        total_duration = self.end_time - self.start_time if self.end_time and self.start_time else 0
        
        return LoadTestResults(
            total_requests=total_requests,
            successful_requests=len(successful),
            failed_requests=len(failed),
            avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0,
            p50_latency_ms=percentile(latencies, 0.50),
            p95_latency_ms=percentile(latencies, 0.95),
            p99_latency_ms=percentile(latencies, 0.99),
            min_latency_ms=min(latencies) if latencies else 0,
            max_latency_ms=max(latencies) if latencies else 0,
            requests_per_second=total_requests / total_duration if total_duration > 0 else 0,
            total_duration_seconds=total_duration,
            error_rate=len(failed) / total_requests if total_requests > 0 else 0,
            errors_by_type=dict(errors_by_type)
        )
    
    def get_results_json(self) -> str:
        """Get results as JSON string."""
        results = self._calculate_results()
        return json.dumps(asdict(results), indent=2)


async def run_load_test_from_config(config_dict: Dict[str, Any]) -> LoadTestResults:
    """Run a load test from a configuration dictionary."""
    config = LoadTestConfig(**config_dict)
    generator = LoadGenerator(config)
    return await generator.run()


def main():
    """CLI entry point for running load tests."""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Run vLLM load test")
    parser.add_argument("--target-url", required=True, help="vLLM endpoint URL")
    parser.add_argument("--num-clients", type=int, default=10, help="Number of concurrent clients")
    parser.add_argument("--rps", type=float, default=10.0, help="Requests per second")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--prompts", nargs="+", default=["Tell me a story about AI."], help="Prompts to use")
    parser.add_argument("--max-tokens", type=int, default=100, help="Max tokens per request")
    parser.add_argument("--model", default="meta-llama/Llama-2-7b-hf", help="Model name")
    parser.add_argument("--output", help="Output file for results JSON")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create config
    config = LoadTestConfig(
        target_url=args.target_url,
        num_clients=args.num_clients,
        requests_per_second=args.rps,
        duration_seconds=args.duration,
        prompts=args.prompts,
        max_tokens=args.max_tokens,
        model=args.model
    )
    
    # Run test
    logger.info("Starting load test...")
    generator = LoadGenerator(config)
    results = asyncio.run(generator.run())
    
    # Print results
    print("\n" + "="*80)
    print("LOAD TEST RESULTS")
    print("="*80)
    print(generator.get_results_json())
    print("="*80)
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            f.write(generator.get_results_json())
        logger.info(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
