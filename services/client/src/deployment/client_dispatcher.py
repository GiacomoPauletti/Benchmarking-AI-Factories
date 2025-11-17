import requests
import json
import os
import logging
import subprocess
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


    def _ensure_loadgen_container(self):
        """Ensure the load generator Apptainer container is built on the remote system.
        
        This method checks if the container exists, and if not, uploads the definition
        file and builds it. Container is cached after first build.
        """
        container_dir = f"{self._remote_base_path}/containers"
        container_def_path = f"{container_dir}/loadgen.def"
        container_sif_path = f"{container_dir}/loadgen.sif"
        
        # Check if container already exists
        check_cmd = f"test -f {container_sif_path} && echo 'exists' || echo 'missing'"
        success, stdout, stderr = self._ssh_manager.execute_remote_command(check_cmd, timeout=5)
        
        if success and 'exists' in stdout:
            logger.info(f"Load generator container already exists: {container_sif_path}")
            return
        
        logger.info("Building load generator container (first time setup, ~30-60s)...")
        
        # Create container directory
        mkdir_cmd = f"mkdir -p {container_dir}"
        self._ssh_manager.execute_remote_command(mkdir_cmd, timeout=10)
        
        # Read local container definition
        # The container definition is in services/client/src/client/client_container.def
        local_def_path = Path(__file__).parent.parent / "client" / "client_container.def"
        
        if not local_def_path.exists():
            raise FileNotFoundError(f"Container definition not found: {local_def_path}")
        
        with open(local_def_path, 'r') as f:
            def_content = f.read()
        
        # Upload definition file
        logger.info(f"Uploading container definition to {container_def_path}")
        upload_cmd = f"cat > {container_def_path} << 'CONTAINER_DEF_EOF'\n{def_content}\nCONTAINER_DEF_EOF"
        success, stdout, stderr = self._ssh_manager.execute_remote_command(upload_cmd, timeout=10)
        
        if not success:
            raise RuntimeError(f"Failed to upload container definition: {stderr}")
        
        # Build container using Apptainer
        logger.info("Building Apptainer container (this may take 30-60 seconds)...")
        build_cmd = f"cd {container_dir} && apptainer build {container_sif_path} {container_def_path}"
        success, stdout, stderr = self._ssh_manager.execute_remote_command(build_cmd, timeout=180)
        
        if success:
            logger.info(f"Container built successfully: {container_sif_path}")
        else:
            logger.error(f"Container build failed: {stderr}")
            raise RuntimeError(f"Failed to build load generator container: {stderr}")


    def get_job_logs(self, job_id: str, group_id: int) -> str:
        """Get logs from a SLURM job via SSH.
        
        Args:
            job_id: SLURM job ID
            group_id: Client group ID
            
        Returns:
            Formatted log content or error message
        """
        if not job_id:
            return "=== NO JOB ID ===\nJob ID not available"
        
        stdout_remote = f"{self._remote_logs_dir}/loadgen-{group_id}-{job_id}.out"
        stderr_remote = f"{self._remote_logs_dir}/loadgen-{group_id}-{job_id}.err"
        
        # Fetch stdout using tail for last 200 lines
        stdout_cmd = f"tail -n 200 {stdout_remote} 2>/dev/null || echo 'Log not yet available'"
        success_out, stdout_content, _ = self._ssh_manager.execute_remote_command(stdout_cmd, timeout=10)
        
        # Fetch stderr using tail for last 100 lines
        stderr_cmd = f"tail -n 100 {stderr_remote} 2>/dev/null || echo 'No errors logged'"
        success_err, stderr_content, _ = self._ssh_manager.execute_remote_command(stderr_cmd, timeout=10)
        
        # Format combined output
        log_output = f"=== SLURM STDOUT (last 200 lines) ===\n"
        if success_out:
            log_output += stdout_content if stdout_content else "Log not yet available"
        else:
            log_output += "Failed to fetch stdout"
        
        log_output += f"\n\n=== SLURM STDERR (last 100 lines) ===\n"
        if success_err:
            log_output += stderr_content if stderr_content else "No errors logged"
        else:
            log_output += "Failed to fetch stderr"
        
        return log_output

    def sync_logs_from_remote(self, local_logs_dir: str = "./logs", pattern: str = "loadgen-*.out"):
        """Sync SLURM logs from remote MeluXina to local directory.
        
        Args:
            local_logs_dir: Local directory to sync logs to
            pattern: Glob pattern for log files to sync (default: loadgen-*.out)
            
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
            "--include", pattern.replace('.out', '.err'),  # Also include .err files
            "--include", "loadgen-results-*.json",  # Include results JSON files
            "--include", "*/",  # Include directories for recursive search
            "--exclude", "*",   # Exclude everything else
            f"{self._ssh_manager.ssh_user}@{self._ssh_manager.ssh_host}:{self._remote_logs_dir}/",
            f"{local_logs_dir}/"
        ]
        
        # Add SSH port option
        rsync_cmd.insert(2, "-e")
        rsync_cmd.insert(3, f"ssh -p {self._ssh_manager.ssh_port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null")
        
        logger.debug(f"Running rsync command: {' '.join(rsync_cmd)}")
        
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
                logger.debug(f"Rsync stdout: {result.stdout}")
                if result.stderr:
                    logger.debug(f"Rsync stderr: {result.stderr}")
                return True, "Logs synced successfully"
            else:
                logger.error(f"Rsync failed with return code {result.returncode}")
                logger.error(f"Rsync stderr: {result.stderr}")
                logger.debug(f"Rsync stdout: {result.stdout}")
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
        
        
        # Build the complete bash script for the load generator
        script_content = self._build_load_generator_script(group_id)
        
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
            'cpus_per_task': 2,  # Async I/O workload only needs 2 CPUs regardless of client count
            'current_working_directory': self._remote_logs_dir,
            'standard_output': f'{self._remote_logs_dir}/loadgen-{group_id}-%j.out',
            'standard_error': f'{self._remote_logs_dir}/loadgen-{group_id}-%j.err',
            'environment': [f'USER={self._username}'],  # Mandatory per MeluXina docs
        }
        
        # Submit job via SSH
        success, response_data = self._submit_slurm_job_via_ssh(
            script_content=script_content,
            job_config=job_config
        )

        if success:
            # Extract job ID from response
            job_id = None
            if 'job_id' in response_data:
                job_id = str(response_data['job_id'])
            elif 'jobs' in response_data and len(response_data['jobs']) > 0:
                job_id = str(response_data['jobs'][0].get('job_id'))
            
            if job_id:
                logger.info(f"Load generator job submitted successfully! Job ID: {job_id}")
                return job_id
            else:
                logger.warning("Job submitted but no job_id in response")
                logger.debug(json.dumps(response_data, indent=2))
                return None
        else:
            logger.error(f"Job submission failed: {response_data}")
            return None
    
    def _build_load_generator_script(self, group_id: int) -> str:
        """Build the complete bash script to run the load generator on the compute node.
        
        This script:
        1. Loads required modules (env, Apptainer)
        2. Builds the container if it doesn't exist
        3. Runs the load test inside the container
        """
        prompts_json = json.dumps(self._load_config['prompts'])
        
        log_dir = self._remote_base_path.rstrip("/") + "/logs"
        sif_path = self._remote_base_path.rstrip("/") + "/containers/client.sif"

        script = f"""#!/bin/bash -l

# Load Generator Job for Group {group_id}

echo "Starting load test at $(date)"
echo "Configuration:"
echo "  Server API: {self._load_config['target_url']}"
echo "  Service ID: {self._load_config['service_id']}"
echo "  Clients: {self._load_config['num_clients']}"
echo "  RPS: {self._load_config['requests_per_second']}"
echo "  Duration: {self._load_config['duration_seconds']}s"
echo "  Container: {sif_path}"
echo ""

# Load required modules
echo "Loading modules..."
module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0

# Ensure HOME is set (SLURM sometimes clears it)
if [ -z "$HOME" ]; then
    export HOME=/home/users/$USER
fi

# Debug: Print environment info
echo "=== SLURM Job Debug Info ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Working directory: $(pwd)"
echo "HOME: $HOME"
echo "USER: $USER"
echo "Log directory: {log_dir}"
echo "Container sif: {sif_path}"
echo "==========================="

# Generate the Python load test script with config
echo "Generating Python load test script..."
cat > {self._remote_base_path}/src/client/main.py << 'PYTHON_EOF'
import asyncio
import aiohttp
import time
import json
import random
from dataclasses import dataclass

@dataclass
class RequestMetrics:
    timestamp: float
    latency_ms: float
    status_code: int
    success: bool
    error: str = None

async def send_request(session, url, prompt, config):
    '''Send request to Server API proxy endpoint.'''
    start = time.time()
    try:
        service_id = config.get("service_id")
        if not service_id:
            raise ValueError("service_id is required")
            
        payload = {{
            "prompt": prompt,
            "max_tokens": config["max_tokens"],
            "temperature": config.get("temperature", 0.7)
        }}
        
        # Server API proxy endpoint
        endpoint = f"{{url}}/api/v1/vllm/{{service_id}}/prompt"
            
        async with session.post(endpoint, json=payload, timeout=60) as resp:
            latency = (time.time() - start) * 1000
            if resp.status == 200:
                data = await resp.json()
                # Server proxy returns: {{"success": true, "response": "...", "usage": {{...}}}}
                success = data.get("success", False)
                if not success:
                    return RequestMetrics(start, latency, resp.status, False, data.get("error", "Unknown error"))
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
        "service_id": "{self._load_config['service_id']}",
        "num_clients": {self._load_config['num_clients']},
        "requests_per_second": {self._load_config['requests_per_second']},
        "duration_seconds": {self._load_config['duration_seconds']},
        "prompts": {prompts_json},
        "max_tokens": {self._load_config.get('max_tokens', 100)},
        "temperature": {self._load_config.get('temperature', 0.7)}
    }}
    
    print(f"Starting load test with {{config['num_clients']}} clients")
    print(f"Target: {{config['target_url']}}")
    print(f"Service ID: {{config['service_id']}}")
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
    results_file = "{log_dir}/loadgen-results-{group_id}.json"
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
PYTHON_EOF

# Build container if needed
if [ ! -f {sif_path} ]; then
    echo 'Building Apptainer image: {sif_path}'
    
    # Create containers directory
    mkdir -p $(dirname {sif_path})
    
    # Set up user-writable directories for Apptainer
    export APPTAINER_TMPDIR=/tmp/apptainer-$USER-$$
    export APPTAINER_CACHEDIR=$HOME/.apptainer/cache
    
    mkdir -p $APPTAINER_TMPDIR $APPTAINER_CACHEDIR $HOME/.apptainer
    
    # Create empty docker config to avoid authentication issues
    echo '{{}}' > $HOME/.apptainer/docker-config.json
    
    # Change to the source directory where files are located
    cd {self._remote_base_path}/src/client
    
    # Build container from this directory
    apptainer build {sif_path} client_container.def
    build_result=$?
    
    # Clean up temp directories
    rm -rf $APPTAINER_TMPDIR
    
    if [ $build_result -ne 0 ]; then
        echo "ERROR: Failed to build container (exit code: $build_result)"
        exit 1
    fi
    
    echo "Container build successful!"
else
    echo "Container already exists: {sif_path}"
fi

# Ensure log directory exists
mkdir -p {log_dir}

# Run the load test inside the container
echo "Starting container..."
echo "Running load test container..."

apptainer run --bind {log_dir}:/app/logs {sif_path}
container_exit_code=$?

echo ""
echo "Container exited with code: $container_exit_code"
echo "Load test completed at $(date)"

exit $container_exit_code
"""
        return script


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