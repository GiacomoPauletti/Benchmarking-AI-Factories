import asyncio
import aiohttp
import time
import json
import random
from dataclasses import dataclass, asdict

# Embedded load generator (simplified version)
@dataclass
class RequestMetrics:
    timestamp: float
    latency_ms: float
    status_code: int
    success: bool
    error: str = None

async def send_request(session, url, prompt, config):
    start = time.time()
    try:
        payload = {{
            "prompt": prompt,
            "max_tokens": config["max_tokens"],
            "temperature": config.get("temperature", 0.7)
        }}
        if config.get("model"):
            payload["model"] = config["model"]
            
        async with session.post(f"{{url}}/v1/completions", json=payload, timeout=60) as resp:
            latency = (time.time() - start) * 1000
            if resp.status == 200:
                await resp.json()
                return RequestMetrics(start, latency, resp.status, True)
            else:
                text = await resp.text()
                return RequestMetrics(start, latency, resp.status, False, text[:100])
    except Exception as e:
        latency = (time.time() - start) * 1000
        return RequestMetrics(start, latency, 0, False, str(e))

async def worker(worker_id, session, config, end_time, results, semaphore):
    prompts = config["prompts"]
    url = config["target_url"]
    while time.time() < end_time:
        async with semaphore:
            prompt = random.choice(prompts)
            metric = await send_request(session, url, prompt, config)
            results.append(metric)
            if len(results) % 50 == 0:
                print(f"Sent {{len(results)}} requests", flush=True)

async def rate_limiter_task(semaphore, rps, end_time):
    interval = 1.0 / rps
    while time.time() < end_time:
        semaphore.release()
        await asyncio.sleep(interval)

async def run_load_test():
    config = {{
        "target_url": "{self._load_config['target_url']}",
        "num_clients": {self._load_config['num_clients']},
        "requests_per_second": {self._load_config['requests_per_second']},
        "duration_seconds": {self._load_config['duration_seconds']},
        "prompts": {prompts_json},
        "max_tokens": {self._load_config.get('max_tokens', 100)},
        "temperature": {self._load_config.get('temperature', 0.7)},
        "model": {json.dumps(self._load_config.get('model'))}
    }}
    
    print(f"Starting load test with {{config['num_clients']}} clients")
    print(f"Target RPS: {{config['requests_per_second']}}")
    
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
    
    print("\\n" + "="*80)
    print("LOAD TEST RESULTS")
    print("="*80)
    print(f"Total Requests: {{total}}")
    print(f"Successful: {{successful}}")
    print(f"Failed: {{total - successful}}")
    if latencies:
        print(f"Avg Latency: {{sum(latencies)/len(latencies):.2f}}ms")
        print(f"P50 Latency: {{latencies[len(latencies)//2]:.2f}}ms")
        print(f"P95 Latency: {{latencies[int(len(latencies)*0.95)]:.2f}}ms")
        print(f"P99 Latency: {{latencies[int(len(latencies)*0.99)]:.2f}}ms")
    print(f"Actual RPS: {{total/(time.time()-start_time):.2f}}")
    print("="*80)
    
    # Save detailed results
    results_file = "{self._remote_logs_dir}/loadgen-results-{group_id}.json"
    with open(results_file, 'w') as f:
        json.dump({{
            "total_requests": total,
            "successful": successful,
            "failed": total - successful,
            "latencies": latencies,
            "config": config
        }}, f, indent=2)
    print(f"Results saved to: {{results_file}}")

asyncio.run(run_load_test())