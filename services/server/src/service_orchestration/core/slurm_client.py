"""
SLURM REST API Client for Service Orchestrator.
Routes all requests through the SOCKS5 proxy at localhost:1080.
"""

import os
import json
import logging
import subprocess
import requests
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class SlurmClient:
    """
    Client for interacting with SLURM REST API via SOCKS5 proxy.
    Routes all requests through the SSH SOCKS5 proxy at localhost:1080.
    """
    
    def __init__(self):
        self.base_url = os.getenv("SLURM_REST_URL", "http://slurmrestd.meluxina.lxp.lu:6820/slurm/v0.0.40")
        self.token = self._get_token()
        self.username = os.getenv("USER", "unknown")
        
        self.headers = {
            'X-SLURM-USER-NAME': self.username,
            'X-SLURM-USER-TOKEN': self.token,
            'Content-Type': 'application/json'
        }
        
        # Configure session - only use SOCKS proxy if explicitly enabled
        # (Orchestrator runs ON MeluXina, so it can reach SLURM REST directly)
        self.session = requests.Session()
        logger.info(f"Initialized SlurmClient for user {self.username} at {self.base_url} (direct connection, no proxy)")

    def _get_token(self) -> str:
        """Get SLURM JWT token from env or scontrol"""
        token = os.getenv("SLURM_JWT")
        if token:
            return token
            
        try:
            # Try scontrol
            result = subprocess.run(
                ["scontrol", "token"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith("SLURM_JWT="):
                        return line.split("=", 1)[1].strip()
        except Exception as e:
            logger.warning(f"Failed to get token from scontrol: {e}")
            
        logger.warning("SLURM_JWT not found and scontrol failed. API calls may fail.")
        return ""

    def submit_job(self, job_payload: Dict[str, Any]) -> str:
        """Submit a job via REST API"""
        try:
            logger.info(f"Submitting job with payload: {json.dumps(job_payload, indent=2)}")
            response = self.session.post(
                f"{self.base_url}/job/submit",
                headers=self.headers,
                json=job_payload,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('errors'):
                raise RuntimeError(f"SLURM API errors: {result['errors']}")
                
            job_id = result.get('job_id')
            if not job_id:
                raise RuntimeError(f"No job_id in response: {result}")
                
            return str(job_id)
            
        except Exception as e:
            logger.error(f"Failed to submit job: {e}")
            if isinstance(e, requests.exceptions.HTTPError):
                logger.error(f"Response: {e.response.text}")
            raise

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        try:
            job_id = job_id.split(':', 1)[0]
            response = self.session.delete(
                f"{self.base_url}/job/{job_id}",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False

    def get_job_status(self, job_id: str) -> str:
        """Get job status"""
        try:
            job_id = job_id.split(':', 1)[0]
            response = self.session.get(
                f"{self.base_url}/job/{job_id}",
                headers=self.headers,
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                jobs = result.get('jobs', [])
                if jobs:
                    state = jobs[0].get('job_state', 'unknown')
                    if isinstance(state, list):
                        return state[0].lower()
                    return str(state).lower()
            return "unknown"
        except Exception as e:
            logger.error(f"Failed to get status for {job_id}: {e}")
            return "unknown"
    
    def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """Get detailed job information including node assignment"""
        try:
            slurm_job_id = job_id.split(':', 1)[0]
            response = self.session.get(
                f"{self.base_url}/job/{slurm_job_id}",
                headers=self.headers,
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                jobs = result.get('jobs', [])
                if jobs:
                    job = jobs[0]
                    
                    # Try to extract node list from various possible fields
                    nodes = []
                    
                    # Try direct nodes field
                    if 'nodes' in job and job['nodes']:
                        node_str = job['nodes']
                        # Could be a string like "mel2074" or "mel[2074-2076]"
                        if isinstance(node_str, str):
                            # Simple case: single node or comma-separated
                            if '[' not in node_str:
                                nodes = [n.strip() for n in node_str.split(',')]
                            else:
                                # Range expansion would go here, for now just take first node
                                # Format: "mel[2074-2076]" -> extract "mel2074"
                                import re
                                match = re.match(r'([a-zA-Z]+)\[(\d+)', node_str)
                                if match:
                                    prefix, first_num = match.groups()
                                    nodes = [f"{prefix}{first_num}"]
                        elif isinstance(node_str, list):
                            nodes = node_str
                    
                    # Fallback: try node_list field
                    if not nodes and 'node_list' in job:
                        nodes = [job['node_list']]
                    
                    # Fallback: try job_resources
                    if not nodes and 'job_resources' in job:
                        resources = job['job_resources']
                        if 'allocated_nodes' in resources:
                            nodes = resources['allocated_nodes']
                    
                    logger.debug(f"Job {job_id} nodes: {nodes}")
                    
                    return {
                        "job_id": job_id,
                        "state": job.get('job_state', 'unknown'),
                        "nodes": nodes,
                        "node_count": len(nodes) if nodes else job.get('node_count', 0)
                    }
            return {}
        except Exception as e:
            logger.error(f"Failed to get details for {job_id}: {e}")
            logger.exception(e)
            return {}
