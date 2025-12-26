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


def _split_top_level_csv(value: str) -> List[str]:
    """Split a SLURM hostlist string on commas, ignoring commas inside brackets."""
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in value:
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth = max(0, depth - 1)
        if ch == ',' and depth == 0:
            part = ''.join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            continue
        buf.append(ch)
    tail = ''.join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _expand_slurm_hostlist(value: str) -> List[str]:
    """Expand SLURM hostlist syntax into a list of hostnames.

    Examples:
      - "mel2074" -> ["mel2074"]
      - "mel2074,mel2075" -> ["mel2074", "mel2075"]
      - "mel[2074-2075]" -> ["mel2074", "mel2075"]
      - "mel[0001-0003]" -> ["mel0001", "mel0002", "mel0003"]
      - "mel[2074-2075],mel2080" -> ["mel2074", "mel2075", "mel2080"]
    """
    value = (value or "").strip()
    if not value:
        return []

    def expand_token(token: str) -> List[str]:
        token = token.strip()
        if not token:
            return []

        if '[' not in token:
            return [token]

        # Expand the first bracket expression, then recurse (supports multiple bracket groups).
        start = token.find('[')
        end = token.find(']', start + 1)
        if end == -1:
            return [token]  # malformed; return as-is

        prefix = token[:start]
        inside = token[start + 1:end]
        suffix = token[end + 1:]

        expanded: List[str] = []
        for part in inside.split(','):
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                a, b = part.split('-', 1)
                a = a.strip()
                b = b.strip()
                if not a or not b:
                    continue
                width = max(len(a), len(b))
                try:
                    start_num = int(a)
                    end_num = int(b)
                except ValueError:
                    continue
                step = 1 if end_num >= start_num else -1
                for n in range(start_num, end_num + step, step):
                    expanded.extend(expand_token(f"{prefix}{n:0{width}d}{suffix}"))
            else:
                expanded.extend(expand_token(f"{prefix}{part}{suffix}"))

        return expanded

    results: List[str] = []
    for tok in _split_top_level_csv(value):
        results.extend(expand_token(tok))
    return [r for r in results if r]

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
                            nodes = _expand_slurm_hostlist(node_str)
                        elif isinstance(node_str, list):
                            expanded_nodes: List[str] = []
                            for item in node_str:
                                if isinstance(item, str):
                                    expanded_nodes.extend(_expand_slurm_hostlist(item))
                            nodes = expanded_nodes
                    
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
