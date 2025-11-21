"""
Orchestrator initialization and job submission logic.
Handles automatic Orchestrator startup via Slurm REST API.
"""

import os
import logging
import requests
import time
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


def get_orchestrator_script(remote_base_path: str) -> str:
    """Generate the bash script for running the Orchestrator.
    
    Args:
        remote_base_path: Base path on MeluXina for the project
        
    Returns:
        Bash script content as a string
    """
    return f"""#!/bin/bash
# Load modules
module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0

# Get SLURM JWT token for API calls
echo "Fetching SLURM JWT token..."
SLURM_JWT=$(scontrol token | grep SLURM_JWT= | cut -d= -f2)
if [ -z "$SLURM_JWT" ]; then
    echo "ERROR: Failed to get SLURM JWT token"
    exit 1
fi
echo "SLURM JWT token obtained"

# Get the node's IP
ORCHESTRATOR_HOST=$(hostname -i)
ORCHESTRATOR_PORT=8003

# Define base directory
BENCHMARK_DIR="{remote_base_path}"
ENV_FILE="${{BENCHMARK_DIR}}/orchestrator.env"

# Ensure HOME is set for Apptainer
if [ -z "$HOME" ] || [ "$HOME" = "/" ]; then
    export HOME=$(dirname "$BENCHMARK_DIR")
fi

echo "Starting ServiceOrchestrator on ${{ORCHESTRATOR_HOST}}:${{ORCHESTRATOR_PORT}}"
echo "ORCHESTRATOR_URL=http://${{ORCHESTRATOR_HOST}}:${{ORCHESTRATOR_PORT}}" > "$ENV_FILE"

# Define paths
ORCH_DIR="${{BENCHMARK_DIR}}/src/service_orchestration"
SIF_PATH="${{ORCH_DIR}}/orchestrator.sif"
DEF_PATH="${{ORCH_DIR}}/orchestrator.def"

# Function to validate if SIF is a valid Singularity/Apptainer image
validate_sif() {{
    local sif_file="$1"
    
    if [ ! -f "$sif_file" ]; then
        return 1
    fi
    
    # Check file signature - valid SIF files start with specific magic bytes
    # Run a quick inspection to validate format
    if ! apptainer inspect "$sif_file" &>/dev/null; then
        echo "WARNING: $sif_file exists but is not a valid Apptainer image"
        return 1
    fi
    
    return 0
}}

# Check if container exists and is valid
NEED_REBUILD=0
if [ -f "$SIF_PATH" ]; then
    echo "Checking if existing container is valid..."
    if validate_sif "$SIF_PATH"; then
        echo "✓ Existing container is valid"
    else
        echo "✗ Existing container is corrupted or invalid - will rebuild"
        rm -f "$SIF_PATH"
        NEED_REBUILD=1
    fi
else
    echo "Container does not exist - will build"
    NEED_REBUILD=1
fi

# Build container if needed
if [ $NEED_REBUILD -eq 1 ] || [ ! -f "$SIF_PATH" ]; then
    echo "Building Apptainer container from $DEF_PATH..."
    cd "$ORCH_DIR"
    
    export APPTAINER_TMPDIR=/tmp/apptainer-$USER-$$
    export APPTAINER_CACHEDIR=$HOME/.apptainer/cache
    mkdir -p $APPTAINER_TMPDIR $APPTAINER_CACHEDIR
    
    apptainer build "$SIF_PATH" "$DEF_PATH"
    BUILD_RES=$?
    
    rm -rf $APPTAINER_TMPDIR
    
    if [ $BUILD_RES -ne 0 ]; then
        echo "ERROR: Failed to build container"
        exit 1
    fi
    
    # Validate the newly built container
    if ! validate_sif "$SIF_PATH"; then
        echo "ERROR: Built container is invalid"
        rm -f "$SIF_PATH"
        exit 1
    fi
    
    echo "✓ Container built and validated successfully"
fi

# Final validation before running
if ! validate_sif "$SIF_PATH"; then
    echo "ERROR: Container validation failed before execution"
    exit 1
fi

# Run the orchestrator
echo "Running orchestrator container..."
apptainer run \\
    --env ORCHESTRATOR_HOST=0.0.0.0 \\
    --env ORCHESTRATOR_PORT=$ORCHESTRATOR_PORT \\
    --env SLURM_JWT=$SLURM_JWT \\
    --env REMOTE_BASE_PATH=$BENCHMARK_DIR \\
    "$SIF_PATH" \\
    --host 0.0.0.0 --port $ORCHESTRATOR_PORT
"""


def submit_orchestrator_job(ssh_manager, remote_base_path: str) -> Tuple[bool, str]:
    """Submit Orchestrator job via Slurm REST API.
    
    Args:
        ssh_manager: SSH manager instance
        remote_base_path: Base path on MeluXina
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Get Slurm token
        token = ssh_manager.get_slurm_token()
        
        headers = {
            'X-SLURM-USER-TOKEN': token,
            'X-SLURM-USER-NAME': ssh_manager.ssh_user,
            'Content-Type': 'application/json'
        }
        
        # Build job payload
        script_content = get_orchestrator_script(remote_base_path)
        
        job_payload = {
            "job": {
                "name": "service-orchestrator",
                "qos": "default",
                "account": "p200776",
                "partition": "cpu",
                "nodes": 1,
                "tasks": 1,
                "cpus_per_task": 4,
                "time_limit": {
                    "number": 30,  # 30 minutes
                    "set": True
                },
                "current_working_directory": remote_base_path,
                "standard_output": f"{remote_base_path}/logs/orchestrator_job.out",
                "standard_error": f"{remote_base_path}/logs/orchestrator_job.err",
                "environment": {
                    "PATH": "/bin:/usr/bin:/usr/local/bin",
                    "USER": ssh_manager.ssh_user,
                    "BASH_ENV": "/etc/profile"
                }
            },
            "script": script_content
        }
        
        # Submit via REST API
        resp = requests.post(
            "http://localhost:6820/slurm/v0.0.40/job/submit",
            headers=headers,
            json=job_payload,
            timeout=10
        )
        
        if resp.status_code != 200:
            error_msg = f"REST API submission failed: {resp.text}"
            logger.error(error_msg)
            return False, error_msg
        
        response_data = resp.json()
        job_id = response_data.get('job_id', 'unknown')
        logger.info(f"Orchestrator job submitted successfully. Job ID: {job_id}")
        return True, f"Job submitted: {job_id}"
        
    except Exception as e:
        error_msg = f"Failed to submit orchestrator job: {e}"
        logger.error(error_msg)
        return False, error_msg


def wait_for_orchestrator_url(ssh_manager, remote_env_file: str, timeout: int = 120) -> Optional[str]:
    """Poll for the orchestrator URL from the discovery file.
    
    Args:
        ssh_manager: SSH manager instance
        remote_env_file: Path to the orchestrator.env file on remote
        timeout: Maximum wait time in seconds
        
    Returns:
        Orchestrator URL if found, None otherwise
    """
    logger.info(f"Waiting for orchestrator to start (timeout: {timeout}s)...")
    
    start_time = time.time()
    poll_interval = 2  # seconds
    
    while time.time() - start_time < timeout:
        success, stdout, stderr = ssh_manager.execute_remote_command(f"cat {remote_env_file}")
        
        if success and stdout:
            for line in stdout.splitlines():
                if line.startswith("ORCHESTRATOR_URL="):
                    orchestrator_url = line.split("=", 1)[1].strip()
                    logger.info(f"Found orchestrator URL: {orchestrator_url}")
                    return orchestrator_url
        
        time.sleep(poll_interval)
    
    logger.warning(f"Orchestrator did not start within {timeout} seconds")
    return None


def wait_for_orchestrator_ready(ssh_manager, orchestrator_url: str, timeout: int = 180) -> bool:
    """Wait for orchestrator to be fully ready and accepting requests.
    
    This ensures the orchestrator container has finished building and starting up.
    
    Args:
        ssh_manager: SSH manager instance
        orchestrator_url: URL of the orchestrator service
        timeout: Maximum wait time in seconds
        
    Returns:
        True if orchestrator is ready, False otherwise
    """
    logger.info(f"Waiting for orchestrator to be fully ready at {orchestrator_url} (timeout: {timeout}s)...")
    logger.info("This may take a while if the container is being built for the first time...")
    
    start_time = time.time()
    poll_interval = 3  # seconds
    last_error = None
    attempts = 0
    
    # Parse URL to get host and port for SSH curl
    from urllib.parse import urlparse
    parsed = urlparse(orchestrator_url)
    host = parsed.hostname
    port = parsed.port or 8003
    
    while time.time() - start_time < timeout:
        attempts += 1
        elapsed = int(time.time() - start_time)
        
        try:
            # Use SSH to curl the health endpoint from MeluXina
            health_path = "/health"
            success, status_code, body = ssh_manager.http_request_via_ssh(
                remote_host=host,
                remote_port=port,
                method="GET",
                path=health_path,
                timeout=5
            )
            
            if success and status_code == 200:
                logger.info(f"✓ Orchestrator is ready! (took {elapsed}s, {attempts} attempts)")
                return True
            else:
                last_error = f"Status {status_code}: {body[:100]}"
                logger.debug(f"Orchestrator not ready yet (attempt {attempts}, {elapsed}s): {last_error}")
                
        except Exception as e:
            last_error = str(e)
            logger.debug(f"Orchestrator not ready yet (attempt {attempts}, {elapsed}s): {last_error}")
        
        # Log progress every 30 seconds
        if elapsed > 0 and elapsed % 30 == 0:
            logger.info(f"Still waiting for orchestrator... ({elapsed}s elapsed, {timeout-elapsed}s remaining)")
        
        time.sleep(poll_interval)
    
    logger.error(f"✗ Orchestrator failed to become ready within {timeout} seconds")
    if last_error:
        logger.error(f"Last error: {last_error}")
    return False


def check_existing_orchestrator(ssh_manager, remote_env_file: str) -> Optional[str]:
    """Check if an orchestrator is already running by reading the discovery file.
    
    Args:
        ssh_manager: SSH manager instance
        remote_env_file: Path to the orchestrator.env file on remote
        
    Returns:
        Orchestrator URL if found and valid, None otherwise
    """
    success, stdout, stderr = ssh_manager.execute_remote_command(f"cat {remote_env_file}")
    
    if success and stdout:
        for line in stdout.splitlines():
            if line.startswith("ORCHESTRATOR_URL="):
                orchestrator_url = line.split("=", 1)[1].strip()
                logger.info(f"Found existing orchestrator URL: {orchestrator_url}")
                
                # Verify the URL is actually reachable
                try:
                    health_url = f"{orchestrator_url}/health"
                    response = requests.get(health_url, timeout=5)
                    if response.status_code == 200:
                        logger.info(f"Orchestrator at {orchestrator_url} is healthy")
                        return orchestrator_url
                    else:
                        logger.warning(f"Orchestrator at {orchestrator_url} returned status {response.status_code}")
                except Exception as e:
                    logger.warning(f"Orchestrator at {orchestrator_url} is not reachable: {e}")
                
                # If health check failed, remove the stale env file
                logger.info("Removing stale orchestrator.env file")
                ssh_manager.execute_remote_command(f"rm -f {remote_env_file}")
    
    return None


def initialize_orchestrator_proxy(ssh_manager):
    """Initialize the OrchestratorProxy by connecting to or starting the orchestrator.
    
    Args:
        ssh_manager: SSH manager instance
        
    Returns:
        OrchestratorProxy instance if successful, None otherwise
    """
    from service_orchestration.orchestrator_proxy import OrchestratorProxy
    
    try:
        # Get remote paths
        remote_base_path = os.environ.get("REMOTE_BASE_PATH", "/project/home/p200981/benchmark")
        
        # Resolve ~ if present
        if remote_base_path.startswith("~"):
            success, stdout, stderr = ssh_manager.execute_remote_command("echo $HOME")
            if success and stdout:
                home_dir = stdout.strip()
                remote_base_path = remote_base_path.replace("~", home_dir, 1)
                logger.info(f"Resolved remote base path to: {remote_base_path}")
        
        remote_env_file = f"{remote_base_path}/orchestrator.env"
        
        # Ensure requirements.txt exists in service_orchestration directory
        logger.info("Ensuring requirements.txt exists on MeluXina...")
        req_content = "fastapi==0.109.0\\nuvicorn[standard]==0.27.0\\npydantic==2.5.3\\nrequests==2.31.0\\nparamiko==3.4.0\\nhttpx==0.26.0\\npyyaml==6.0.3"
        create_req_cmd = f"printf '{req_content}' > {remote_base_path}/src/service_orchestration/requirements.txt"
        success, _, _ = ssh_manager.execute_remote_command(create_req_cmd, timeout=10)
        if success:
            logger.info("requirements.txt ready")
        
        # Track job ID for cleanup
        orchestrator_job_id = None
        
        # 1. Check if orchestrator is already running
        orchestrator_url = check_existing_orchestrator(ssh_manager, remote_env_file)
        
        if orchestrator_url:
            # Try to find the job ID from squeue
            success, stdout, stderr = ssh_manager.execute_remote_command(
                "squeue -u $USER --format='%.18i %.50j' --noheader | grep 'service-orchestrator' | head -1 | awk '{print $1}'",
                timeout=10
            )
            if success and stdout.strip():
                orchestrator_job_id = stdout.strip()
                logger.info(f"Found existing orchestrator job ID: {orchestrator_job_id}")
        
        # 2. If not running, submit a new job
        if not orchestrator_url:
            logger.info("Orchestrator not running. Submitting new job...")
            
            success, message = submit_orchestrator_job(ssh_manager, remote_base_path)
            if not success:
                raise RuntimeError(message)
            
            # Extract job ID from message (format: "Job submitted: 1234567")
            if "Job submitted:" in message:
                orchestrator_job_id = message.split("Job submitted:")[1].strip()
                logger.info(f"New orchestrator job ID: {orchestrator_job_id}")
            
            # Wait for orchestrator URL to appear
            orchestrator_url = wait_for_orchestrator_url(ssh_manager, remote_env_file, timeout=120)
            
            if not orchestrator_url:
                raise RuntimeError("Orchestrator URL not found within timeout - job may have failed")
            
            # Wait for orchestrator to be fully ready (container built, service started)
            logger.info("Orchestrator URL found, now waiting for service to be fully ready...")
            if not wait_for_orchestrator_ready(ssh_manager, orchestrator_url, timeout=180):
                raise RuntimeError(
                    "Orchestrator failed to become ready - container may still be building or service failed to start. "
                    f"Check logs at: {remote_base_path}/logs/orchestrator_job.err"
                )
        else:
            # Orchestrator was already running, verify it's still healthy
            logger.info("Existing orchestrator found, verifying it's ready...")
            if not wait_for_orchestrator_ready(ssh_manager, orchestrator_url, timeout=30):
                logger.warning("Existing orchestrator is not responding, will need to restart")
                # Remove stale env file and return None to trigger restart
                ssh_manager.execute_remote_command(f"rm -f {remote_env_file}")
                raise RuntimeError("Existing orchestrator is not responding")
        
        # If we still don't have job ID, try to get it from squeue
        if not orchestrator_job_id:
            success, stdout, stderr = ssh_manager.execute_remote_command(
                "squeue -u $USER --format='%.18i %.50j' --noheader | grep 'service-orchestrator' | head -1 | awk '{print $1}'",
                timeout=10
            )
            if success and stdout.strip():
                orchestrator_job_id = stdout.strip()
                logger.info(f"Retrieved orchestrator job ID from squeue: {orchestrator_job_id}")
        
        # 3. Create and return the proxy
        orchestrator_proxy = OrchestratorProxy(ssh_manager, orchestrator_url, orchestrator_job_id)
        logger.info(f"Successfully connected to orchestrator at {orchestrator_url}")
        return orchestrator_proxy
        
    except Exception as e:
        logger.error(f"Failed to initialize orchestrator proxy: {e}")
        return None
