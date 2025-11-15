import requests
import json
import os
import logging
from pathlib import Path

from ssh_manager import SSHManager

# Use the logger configured by main.py instead of basic config
logger = logging.getLogger(__name__)

class AbstractClientDispatcher:
    def dispatch(self, group_id: int, time_limit: int):
        pass

class SlurmClientDispatcher(AbstractClientDispatcher):
    """
    SLURM client dispatcher for MeluXina HPC cluster.
    Deploys load generator jobs to test vLLM services.
    """

    def __init__(self, load_config: dict, account: str = "p200981", use_container: bool = False):
        """Initialize SLURM client dispatcher.
        
        Args:
            load_config: Dictionary with load test configuration
            account: SLURM account for job submission (default: p200981)
            use_container: Whether to use containerized client execution
        """
        self._load_config = load_config
        self._use_container = use_container
        self._account = account
        
        # Initialize SSH manager for all remote operations
        self._ssh_manager = SSHManager()
        self._username = self._ssh_manager.ssh_user
        
        # Set up remote base path from environment or use default
        # IMPORTANT: SLURM REST API daemon runs as root and cannot handle ~ paths
        # Must expand ~ to absolute path that SLURM daemon can write to
        remote_base_path_template = os.environ.get(
            'REMOTE_BASE_PATH', 
            '~/ai-factory-benchmarks'
        )
        
        # Expand ~ to /home/users/$USER (NOT tier2 - SLURM daemon can't write there)
        if remote_base_path_template.startswith('~'):
            # Use standard home path /home/users/$USER
            self._remote_base_path = remote_base_path_template.replace('~', f'/home/users/{self._username}', 1)
            logger.info(f"Expanded remote path: {remote_base_path_template} -> {self._remote_base_path}")
        else:
            self._remote_base_path = remote_base_path_template
            logger.info(f"Remote base path: {self._remote_base_path}")
        
        self._remote_logs_dir = str(Path(self._remote_base_path) / "logs")
        
        # Use shared SSH tunnel for SLURM REST API (created at service startup on port 6821)
        # Server uses 6820, client uses 6821 to avoid conflicts
        self._rest_api_port = 6821
        self._base_url = f"http://localhost:{self._rest_api_port}/slurm/v0.0.40"
        
        logger.info(f"SLURM REST API available at: {self._base_url}")
        logger.info(f"Authenticating as user: {self._username}, account: {self._account}")
        logger.info(f"Remote base path: {self._remote_base_path}")
        
        # Ensure remote directories exist
        self._ensure_remote_directories()


    def _ensure_remote_directories(self):
        """Create remote base path and logs directory if they don't exist."""
        logger.info("Ensuring remote directories exist...")
        
        # Create base path and logs directory
        cmd = f"mkdir -p {self._remote_base_path} {self._remote_logs_dir}"
        success, stdout, stderr = self._ssh_manager.execute_remote_command(cmd, timeout=10)
        
        if success:
            logger.info(f"Remote directories ready: {self._remote_base_path}")
        else:
            logger.warning(f"Failed to create remote directories: {stderr}")
            # Don't fail - directories might already exist or permissions might be OK


    def sync_logs_from_remote(self, local_logs_dir: str = "./logs", pattern: str = "slurm-*.out"):
        """Sync SLURM logs from remote MeluXina to local directory.
        
        Args:
            local_logs_dir: Local directory to sync logs to
            pattern: Glob pattern for log files to sync (default: slurm-*.out)
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        logger.info(f"Syncing logs from {self._remote_logs_dir} to {local_logs_dir}...")
        
        # Ensure local logs directory exists
        os.makedirs(local_logs_dir, exist_ok=True)
        
        # Use rsync via SSH to sync logs
        # -a: archive mode (preserves permissions, timestamps, etc.)
        # -v: verbose
        # -z: compress during transfer
        # --include: only sync matching files
        # --exclude: exclude everything else
        rsync_cmd = [
            "rsync", "-avz",
            "--include", pattern,
            "--include", "*/",  # Include directories for recursive search
            "--exclude", "*",   # Exclude everything else
            f"{self._ssh_manager.ssh_user}@{self._ssh_manager.ssh_host}:{self._remote_logs_dir}/",
            f"{local_logs_dir}/"
        ]
        
        # Add SSH port option
        rsync_cmd.insert(2, "-e")
        rsync_cmd.insert(3, f"ssh -p {self._ssh_manager.ssh_port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null")
        
        try:
            import subprocess
            result = subprocess.run(
                rsync_cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env=os.environ.copy()
            )
            
            if result.returncode == 0:
                logger.info(f"Logs synced successfully")
                logger.debug(f"Rsync output: {result.stdout}")
                return True, "Logs synced successfully"
            else:
                logger.error(f"Rsync failed: {result.stderr}")
                return False, f"Rsync failed: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            logger.error("Rsync timeout")
            return False, "Rsync timeout after 60 seconds"
        except Exception as e:
            logger.exception(f"Error syncing logs: {e}")
            return False, f"Error: {str(e)}"



    def dispatch(self, group_id: int, time_limit: int):
        """
        Dispatch load generator job using SLURM.
        Runs via SSH from local client_service to MeluXina.
        
        Args:
            group_id: Group ID to associate with the job
            time_limit: Time limit for the SLURM job in minutes
        """
        logger.info(f"Dispatching load generator for group {group_id}")
        logger.info(f"Config: {json.dumps(self._load_config, indent=2)}")
        
        # Build the load generator command
        # The load generator will be run as a Python module on the compute node
        load_gen_cmd = self._build_load_generator_command(group_id)
        
        # Prepare job configuration matching server pattern and MeluXina requirements
        # Per https://docs.lxp.lu/web_services/slurmrestd/: these fields are mandatory:
        # - qos, time_limit, account, environment, current_working_directory
        job_config = {
            'account': self._account,
            'qos': 'short', 
            'time_limit': {
                'number': time_limit,
                'set': True
            },
            'name': f'ai-factory-loadgen-{group_id}',
            'partition': 'cpu',
            'nodes': '1',
            'tasks': 1,
            'cpus_per_task': self._load_config.get('num_clients', 10),  # One CPU per client for parallelism
            'current_working_directory': self._remote_logs_dir,
            'standard_output': f'{self._remote_logs_dir}/loadgen-{group_id}-%j.out',
            'standard_error': f'{self._remote_logs_dir}/loadgen-{group_id}-%j.err',
            'environment': [f'USER={self._username}'],  # Mandatory per MeluXina docs
        }
        
        script_content = f"""#!/bin/bash -l
# Load Generator Job for Group {group_id}
module load Python/3.11.3-GCCcore-12.3.0  # Load Python module on MeluXina

echo "Starting load test at $(date)"
echo "Configuration:"
echo "  Target: {self._load_config['target_url']}"
echo "  Clients: {self._load_config['num_clients']}"
echo "  RPS: {self._load_config['requests_per_second']}"
echo "  Duration: {self._load_config['duration_seconds']}s"
echo ""

# Run the load generator
{load_gen_cmd}

echo ""
echo "Load test completed at $(date)"
"""
        
        # Submit job via SSH
        success, response_data = self._submit_slurm_job_via_ssh(
            script_content=script_content,
            job_config=job_config
        )

        if success:
            logger.info("Load generator job submitted successfully!")
            logger.debug(json.dumps(response_data, indent=2))
        else:
            logger.error(f"Job submission failed: {response_data}")

        print(json.dumps(response_data, indent=2))
    
    def _build_load_generator_command(self, group_id: int) -> str:
        """Build the command to run the load generator on the compute node."""
        # First, we need to copy the load_generator.py to the remote
        # For now, we'll embed it inline or assume it's in the repo
        
        # Build Python command with inline script
        prompts_json = json.dumps(self._load_config['prompts'])
        
        cmd = f"""python3 << 'LOAD_GENERATOR_EOF'
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
LOAD_GENERATOR_EOF
"""
        return cmd

    def _submit_slurm_job_via_ssh(self, script_content: str, job_config: dict, 
                                  slurm_rest_host: str = "slurmrestd.meluxina.lxp.lu",
                                  slurm_rest_port: int = 6820):
        """Submit a SLURM job via SSH using the REST API.
        
        Args:
            script_content: The bash script content to execute
            job_config: Job configuration dictionary
            slurm_rest_host: SLURM REST API hostname (unused, kept for compatibility)
            slurm_rest_port: SLURM REST API port (unused, kept for compatibility)
            
        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        try:
            # Get fresh SLURM token on each submission (tokens are cheap via SSH)
            logger.debug("Fetching fresh SLURM token...")
            token = self._ssh_manager.get_slurm_token()
            
            # Prepare the job submission payload
            payload = {
                'script': script_content,
                'job': job_config
            }
            
            # Build headers with fresh token
            headers = {
                'X-SLURM-USER-NAME': self._username,
                'X-SLURM-USER-TOKEN': token,
                'Content-Type': 'application/json'
            }
            
            # Submit via local tunnel (already set up in __init__)
            logger.info(f"Submitting job to {self._base_url}/job/submit")
            logger.info(f"Payload: {json.dumps(payload, indent=2)}")
            logger.info(f"Headers: X-SLURM-USER-NAME={headers['X-SLURM-USER-NAME']}, token length={len(headers['X-SLURM-USER-TOKEN'])}")
            response = requests.post(
                f"{self._base_url}/job/submit", 
                headers=headers, 
                json=payload,
                timeout=30
            )

            if not response.ok:
                logger.error(f"Failed to submit SLURM job: HTTP {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False, {"error": response.text, "status_code": response.status_code}
            
            # Parse JSON response
            response_data = response.json()
            logger.debug(f"SLURM job submission response: {json.dumps(response_data, indent=2)}")
            return True, response_data
                
        except Exception as e:
            logger.exception(f"Error submitting SLURM job via SSH tunnel: {e}")
            return False, {"error": str(e)} 