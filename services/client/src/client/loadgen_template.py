"""
Load generator template for SLURM jobs.
This script is configured via environment variables and runs load tests.
"""
import asyncio
import aiohttp
import time
import json
import random
import os
import sys
from dataclasses import dataclass

@dataclass
class RequestMetrics:
    timestamp: float
    latency_ms: float
    status_code: int
    success: bool
    error: str = None

async def send_request(session, prompt, config):
    """Send request to load balancer or vLLM endpoint.

    Endpoint selection order:
    - `prompt_url` (orchestrator data-plane)
    - `direct_url` (direct vLLM endpoint)
    - `target_url` (legacy)
    """
    start = time.time()
    try:
        endpoint = config.get("prompt_url") or config.get("direct_url") or config.get("target_url")
        if not endpoint:
            return RequestMetrics(start, 0.0, 0, False, "No endpoint configured (prompt_url/direct_url/target_url)")

        # vLLM /v1/completions or orchestrator proxy payload
        payload = {
            "prompt": prompt,
            "max_tokens": config.get("max_tokens", 100),
            "temperature": config.get("temperature", 0.7)
        }

        async with session.post(endpoint, json=payload, timeout=60) as resp:
            latency = (time.time() - start) * 1000
            if resp.status == 200:
                # Try to parse JSON but tolerate plain text responses
                try:
                    data = await resp.json()
                except Exception:
                    data = None

                # If using direct_url assume standard OpenAI-style success
                if config.get("direct_url"):
                    return RequestMetrics(start, latency, resp.status, True)

                # For orchestrator/proxy, look for success flag if present
                if data and isinstance(data, dict):
                    success = data.get("success", True)
                    if not success:
                        return RequestMetrics(start, latency, resp.status, False, data.get("error", "Unknown error"))
                    return RequestMetrics(start, latency, resp.status, True)

                # Default to success if we got HTTP 200 and can't parse body
                return RequestMetrics(start, latency, resp.status, True)
            else:
                text = await resp.text()
                return RequestMetrics(start, latency, resp.status, False, f"HTTP {resp.status}: {text[:100]}")
    except Exception as e:
        latency = (time.time() - start) * 1000
        error_msg = str(e) or repr(e)
        return RequestMetrics(start, latency, 0, False, error_msg)

async def worker(worker_id, session, config, end_time, results, semaphore):
    prompts = config.get("prompts", ["Hello"])
    consecutive_errors = 0

    while time.time() < end_time:
        async with semaphore:
            prompt = random.choice(prompts)
            metric = await send_request(session, prompt, config)
            results.append(metric)

            if not metric.success:
                consecutive_errors += 1
                if consecutive_errors <= 5:  # Print first few errors
                    print(f"Request failed: {metric.error}", flush=True)
            else:
                consecutive_errors = 0

            if len(results) and len(results) % 50 == 0:
                print(f"Sent {len(results)} requests", flush=True)

async def rate_limiter_task(semaphore, rps, end_time):
    interval = 1.0 / rps
    while time.time() < end_time:
        semaphore.release()
        await asyncio.sleep(interval)

async def run_load_test(config_dict=None):
    # Load configuration from environment, file, or argument
    if config_dict:
        config = config_dict
    else:
        config_file = os.environ.get("LOADGEN_CONFIG", "/app/config.json")
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            print(f"Error: Config file not found: {config_file}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in config file: {e}")
            sys.exit(1)
    
    print(f"Starting load test with {config['num_clients']} clients")
    print(f"Target: {config['prompt_url']}")
    print(f"Service ID: {config['service_id']}")
    print(f"Target RPS: {config['requests_per_second']}")
    
    start_time = time.time()
    end_time = start_time + config["duration_seconds"]
    results = []
    semaphore = asyncio.Semaphore(0)
    
    connector = aiohttp.TCPConnector(limit=config["num_clients"])
    async with aiohttp.ClientSession(connector=connector) as session:
        rate_task = asyncio.create_task(rate_limiter_task(semaphore, config["requests_per_second"], end_time))
        workers = [
            asyncio.create_task(worker(i, session, config, end_time, results, semaphore))
            for i in range(config["num_clients"])
        ]
        await asyncio.gather(*workers, return_exceptions=True)
        rate_task.cancel()
        try:
            await rate_task
        except asyncio.CancelledError:
            pass
    
    # Calculate results
    total = len(results)
    successful = sum(1 for r in results if r.success)
    latencies = sorted([r.latency_ms for r in results])
    
    # Analyze errors
    errors = {}
    for r in results:
        if not r.success and r.error:
            err_msg = str(r.error)
            # Group similar errors (e.g. connection errors often have random ports/timestamps)
            if "ConnectorError" in err_msg or "Connection refused" in err_msg:
                err_key = "Connection Error"
            else:
                err_key = err_msg[:100] # Truncate long errors
            errors[err_key] = errors.get(err_key, 0) + 1
    
    print("\n" + "="*80)
    print("LOAD TEST RESULTS")
    print("="*80)
    print(f"Total Requests: {total}")
    print(f"Successful: {successful}")
    print(f"Failed: {total - successful}")
    if latencies:
        print(f"Avg Latency: {sum(latencies)/len(latencies):.2f}ms")
        print(f"P50 Latency: {latencies[len(latencies)//2]:.2f}ms")
        print(f"P95 Latency: {latencies[int(len(latencies)*0.95)]:.2f}ms")
        print(f"P99 Latency: {latencies[int(len(latencies)*0.99)]:.2f}ms")
    print(f"Actual RPS: {total/(time.time()-start_time):.2f}")
    
    if errors:
        print("\nTop Errors:")
        for err, count in list(errors.items())[:5]:
            print(f"  {count}x: {err}")
            
    print("="*80)
    
    # Save detailed results
    results_file = config.get("results_file", "/app/logs/loadgen-results.json")
    try:
        with open(results_file, 'w') as f:
            json.dump({
                "total_requests": total,
                "successful": successful,
                "failed": total - successful,
                "latencies": latencies,
                "errors": errors,
                "config": config
            }, f, indent=2)
        print(f"Results saved to: {results_file}")
    except Exception as e:
        print(f"Error saving results: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_load_test())
