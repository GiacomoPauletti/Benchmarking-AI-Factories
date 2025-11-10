#!/usr/bin/env python3
"""
End-to-End Monitoring Example
==============================

This example demonstrates the complete workflow for:
1. Launching services via Server API (vLLM, Qdrant)
2. Creating a monitoring session
3. Registering services for metrics collection
4. Running a workload
5. Collecting metrics
6. Stopping the session

Prerequisites:
- Docker services running: docker-compose up -d
- Server API available at http://localhost:8001
- Monitoring API available at http://localhost:8002
- Prometheus available at http://localhost:9090
"""

import requests
import time
import json
from datetime import datetime, timedelta
from typing import Dict, Any

# Import server utilities
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))
from server_utils import wait_for_service_ready


class MonitoringWorkflow:
    """Complete end-to-end monitoring workflow example."""
    
    def __init__(
        self,
        server_url: str = "http://localhost:8001",
        monitoring_url: str = "http://localhost:8002"
    ):
        self.server_url = server_url.rstrip('/')
        self.monitoring_url = monitoring_url.rstrip('/')
        self.session_id = None
        self.job_ids = []
        
    def check_services(self) -> bool:
        """Verify that Server and Monitoring APIs are accessible."""
        print("[CHECK] Checking service availability...")
        
        try:
            # Check Server API
            response = requests.get(f"{self.server_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"  [OK] Server API is available at {self.server_url}")
            else:
                print(f"  [ERROR] Server API returned status {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Server API is not accessible: {e}")
            return False
        
        try:
            # Check Monitoring API
            response = requests.get(f"{self.monitoring_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"  [OK] Monitoring API is available at {self.monitoring_url}")
            else:
                print(f"  [ERROR] Monitoring API returned status {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Monitoring API is not accessible: {e}")
            return False
        
        print()
        return True
    
    def create_monitoring_session(self, run_id: str = None) -> str:
        """
        Step 1: Create a monitoring session.
        
        Returns:
            session_id
        """
        print("[SESSION] Step 1: Creating monitoring session...")
        
        payload = {
            "run_id": run_id or f"benchmark-{int(time.time())}",
            "scrape_interval": "15s",
            "labels": {
                "environment": "local",
                "example": "end-to-end"
            }
        }
        
        response = requests.post(
            f"{self.monitoring_url}/api/v1/sessions",
            json=payload
        )
        
        if response.status_code == 409:
            print("  [WARNING]  Another session is already running!")
            print("  [INFO] Listing active sessions...")
            sessions = self.list_sessions()
            for session in sessions:
                if session.get("status") == "RUNNING":
                    print(f"     → Session '{session['session_id']}' is RUNNING")
                    print(f"     → Stop it with: curl -X POST {self.monitoring_url}/api/v1/sessions/{session['session_id']}/stop")
            raise RuntimeError("Cannot create session - another session is running")
        
        response.raise_for_status()
        data = response.json()
        
        self.session_id = data["session_id"]
        print(f"  [OK] Created session: {self.session_id}")
        print(f"  [OK] Prometheus URL: {data['prometheus_url']}")
        print(f"  [OK] Status: {data['status']}")
        print(f"  [OK] Targets count: {data['targets_count']}")
        print()
        
        return self.session_id
    
    def launch_vllm_service(self) -> Dict[str, Any]:
        """
        Step 2a: Launch vLLM service via Server API.
        
        Returns:
            Service data dictionary with id, name, status, etc.
        """
        print("[LAUNCH] Step 2a: Launching single noded vLLM service...")
      
        try:
            response = requests.post(
                f"{self.server_url}/api/v1/services",
                json={
                    "recipe_name": "inference/vllm-single-node"
                },
                timeout=60
            )
            response.raise_for_status()
            service = response.json()
            
            # Server returns: {id, name, recipe_name, status, config, created_at}
            self.job_ids.append(service["id"])
            
            print(f"  [OK] vLLM service created:")
            print(f"    ID: {service['id']}")
            print(f"    Name: {service['name']}")
            print(f"    Status: {service['status']}")
            print(f"    Recipe: {service['recipe_name']}")
            print(f"  [OK] Metrics endpoint: {self.server_url}/api/v1/vllm/{service['id']}/metrics")
            print()
            
            return service
            
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Failed to launch vLLM service: {e}")
            if hasattr(e.response, 'text'):
                print(f"  Response: {e.response.text}")
            raise
    
    def launch_qdrant_service(self) -> Dict[str, Any]:
        """
        Step 2b: Launch Qdrant service via Server API.
        
        Returns:
            Service data dictionary with id, name, status, etc.
        """
        print("[LAUNCH] Step 2b: Launching Qdrant service...")
        
        # Server API expects recipe_name and optional config
        payload = {
            "recipe_name": "vector-db/qdrant",
            "config": {
                "resources": {
                    "cpu": "2",
                    "memory": "8G",
                    "time_limit": 30  # 30 minutes
                }
            }
        }
        
        try:
            response = requests.post(
                f"{self.server_url}/api/v1/services",
                json=payload
            )
            response.raise_for_status()
            service = response.json()
            
            # Server returns: {id, name, recipe_name, status, config, created_at}
            self.job_ids.append(service["id"])
            
            print(f"  [OK] Qdrant service created:")
            print(f"    ID: {service['id']}")
            print(f"    Name: {service['name']}")
            print(f"    Status: {service['status']}")
            print(f"    Recipe: {service['recipe_name']}")
            print(f"  [OK] Metrics endpoint: {self.server_url}/api/v1/vector-db/{service['id']}/metrics")
            print()
            
            return service
            
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Failed to launch Qdrant service: {e}")
            if hasattr(e.response, 'text'):
                print(f"  Response: {e.response.text}")
            raise
    
    def register_service_for_monitoring(
        self,
        session_id: str,
        service: Dict[str, Any]
    ):
        """
        Step 3: Register a service for monitoring using its service_id.
        
        The Monitoring API will automatically resolve the metrics endpoint
        from the Server API. The service_id is used as the Prometheus job label.
        
        Args:
            session_id: Monitoring session ID
            service: Service data from Server API (with id, name, recipe_name, etc.)
        """
        service_id = service["id"]
        recipe_name = service["recipe_name"]
        
        print(f"[STEP 3] Registering service {service_id} for monitoring...")
        
        # Determine service type for labels
        if recipe_name.startswith("inference/vllm"):
            service_type = "vllm"
        elif recipe_name.startswith("vector-db/qdrant"):
            service_type = "qdrant"
        else:
            service_type = "unknown"
        
        payload = {
            "session_id": session_id,
            "service_id": service_id,  # Monitoring API will auto-resolve endpoint
            "labels": {
                "recipe_name": recipe_name,
                "service_type": service_type,
                "environment": "local"
            }
        }
        
        response = requests.post(
            f"{self.monitoring_url}/api/v1/services",
            json=payload
        )
        
        if response.status_code != 200:
            print(f"  [ERROR] Registration failed: {response.status_code}")
            print(f"  Response: {response.text}")
        
        response.raise_for_status()
        data = response.json()
        
        print(f"[OK] Registered service {service_id}")
        print(f"  Endpoint: {data['endpoint']}")
        print()
    
    def check_prometheus_targets(self):
        """Step 4: Verify Prometheus is scraping the targets."""
        print("[TARGETS] Step 4: Checking Prometheus targets...")
        
        # Query Prometheus directly (not through Monitoring API)
        response = requests.get("http://localhost:9090/api/v1/targets")
        response.raise_for_status()
        data = response.json()
        
        if data.get("data", {}).get("activeTargets"):
            print(f"  [OK] Found {len(data['data']['activeTargets'])} active targets:")
            for target in data["data"]["activeTargets"]:
                health = target.get("health", "unknown")
                labels = target.get("labels", {})
                job = labels.get("job", "unknown")
                instance = labels.get("instance", "unknown")
                
                health_icon = "[OK]" if health == "up" else "[ERROR]"
                print(f"    {health_icon} {job} - {instance} ({health})")
        else:
            print("  [WARNING]  No active targets found")
        
        print()
    
    def run_vllm_workload(
        self,
        vllm_service: Dict[str, Any],
        num_prompts: int = 10
    ):
        """
        Step 4: Run a workload against the vLLM service to generate metrics.
        
        Sends prompts to the vLLM service to generate inference metrics.
        """
        service_id = vllm_service["id"]
        service_name = vllm_service["name"]
        
        print(f"[STEP 4] Running vLLM workload ({num_prompts} prompts)...")
        print(f"  Service: {service_name} ({service_id})")
        
        # Sample prompts for testing
        prompts = [
            "What is artificial intelligence?",
            "Explain machine learning in simple terms.",
            "Write a haiku about programming.",
            "What are neural networks?",
            "Describe deep learning.",
            "How does natural language processing work?",
            "What is supervised learning?",
            "Explain gradient descent.",
            "What are transformers in AI?",
            "How do large language models work?"
        ]
        
        successful_requests = 0
        failed_requests = 0
        
        for i in range(num_prompts):
            prompt = prompts[i % len(prompts)]
            
            try:
                response = requests.post(
                    f"{self.server_url}/api/v1/vllm/{service_id}/prompt",
                    json={
                        "prompt": prompt,
                        "max_tokens": 50,
                        "temperature": 0.7
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        successful_requests += 1
                        if (i + 1) % 5 == 0:
                            print(f"  Progress: {i + 1}/{num_prompts} prompts sent...")
                    else:
                        failed_requests += 1
                        print(f"  [WARNING] Prompt {i+1} failed: {result.get('error', 'Unknown error')}")
                else:
                    failed_requests += 1
                    print(f"  [WARNING] Prompt {i+1} returned HTTP {response.status_code}")
                
                # Small delay between requests
                time.sleep(1)
                
            except requests.exceptions.RequestException as e:
                failed_requests += 1
                print(f"  [WARNING] Prompt {i+1} failed: {e}")
        
        print(f"[OK] Workload completed")
        print(f"  Successful requests: {successful_requests}/{num_prompts}")
        print(f"  Failed requests: {failed_requests}/{num_prompts}")
        print()
    
    def collect_metrics(
        self,
        session_id: str,
        window_minutes: int = 5,
        output_dir: str = "./metrics_output"
    ) -> Dict[str, Any]:
        """
        Step 6: Collect metrics for the time window.
        """
        print("[COLLECT] Step 6: Collecting metrics...")
        
        # Define time window (last N minutes)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=window_minutes)
        
        payload = {
            "window_start": start_time.isoformat() + "Z",
            "window_end": end_time.isoformat() + "Z",
            "out_dir": output_dir,
            "run_id": f"run-{int(time.time())}"
        }
        
        print(f"  ime window: {payload['window_start']} to {payload['window_end']}")
        
        response = requests.post(
            f"{self.monitoring_url}/api/v1/sessions/{session_id}/collect",
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        
        print(f"  [OK] Metrics collected")
        print(f"  [OK] Artifacts:")
        for key, path in data.get("artifacts", {}).items():
            print(f"    - {key}: {path}")
        print()
        
        return data
    
    def get_session_status(self, session_id: str):
        """Check the status of a monitoring session."""
        print(f"[SESSION] Checking session status: {session_id}")
        
        response = requests.get(
            f"{self.monitoring_url}/api/v1/sessions/{session_id}/status"
        )
        response.raise_for_status()
        data = response.json()
        
        print(f"  [OK] Session: {data['session_id']}")
        print(f"  [OK] Status: {data['status']}")
        print(f"  [OK] Prometheus healthy: {data['prometheus']['healthy']}")
        print(f"  [OK] Prometheus ready: {data['prometheus']['ready']}")
        print(f"  [OK] Targets count: {data['targets_count']}")
        print()
        
        return data
    
    def list_sessions(self):
        """List all monitoring sessions."""
        response = requests.get(f"{self.monitoring_url}/api/v1/sessions")
        response.raise_for_status()
        return response.json().get("sessions", [])
    
    def stop_session(self, session_id: str):
        """Step 7: Stop the monitoring session."""
        print(f"[STOP] Step 7: Stopping monitoring session...")
        
        response = requests.post(
            f"{self.monitoring_url}/api/v1/sessions/{session_id}/stop"
        )
        response.raise_for_status()
        data = response.json()
        
        print(f"  [OK] {data['message']}")
        print()
    
    def cleanup_services(self):
        """Stop any services that were launched."""
        if not self.job_ids:
            return
        
        print("[CLEANUP] Cleaning up services...")
        for service_id in self.job_ids:
            try:
                # Stop the service via Server API (POST to update status to cancelled)
                response = requests.post(
                    f"{self.server_url}/api/v1/services/{service_id}/status",
                    json={"status": "cancelled"}
                )
                if response.status_code == 200:
                    print(f"  [OK] Stopped service {service_id}")
                else:
                    print(f"  [WARNING]  Failed to stop {service_id}: {response.status_code}")
            except Exception as e:
                print(f"  [WARNING]  Could not stop {service_id}: {e}")
        print()
    
    def run_full_workflow(self):
        """Execute the complete end-to-end workflow."""
        print("=" * 70)
        print("End-to-End Monitoring Workflow")
        print("=" * 70)
        print()
        
        try:
            # Step 0: Check services are running
            if not self.check_services():
                print("[ERROR] Services are not available. Please run:")
                print("   docker-compose up -d")
                return
            
            # Step 1: Create monitoring session
            session_id = self.create_monitoring_session()
            
            # Step 2: Launch services
            vllm_service = self.launch_vllm_service()
            qdrant_service = self.launch_qdrant_service()
            
            # Step 2b: Wait for services to actually be running
            # SLURM jobs can take several minutes to start (queue + resource allocation + container startup)
            print()
            print(f"[WAIT] Waiting for {vllm_service['name']} (ID: {vllm_service['id']}) to start...")
            vllm_ready = wait_for_service_ready(
                self.server_url,
                vllm_service["id"],
                max_wait=600,  # 10 minutes
                poll_interval=10
            )
            
            print()
            print(f"[WAIT] Waiting for {qdrant_service['name']} (ID: {qdrant_service['id']}) to start...")
            qdrant_ready = wait_for_service_ready(
                self.server_url,
                qdrant_service["id"],
                max_wait=300,  # 5 minutes
                poll_interval=10
            )
            
            if not vllm_ready or not qdrant_ready:
                print("\n[ERROR] One or more services failed to start. Skipping workload execution.")
                print("  This is normal if SLURM queue is busy or resources are unavailable.")
                print("  You can still check Prometheus configuration and session management.\n")
                # Continue to demonstrate other features even if services didn't start
            
            print()
            
            # Step 3: Register services for monitoring
            self.register_service_for_monitoring(session_id, vllm_service)
            self.register_service_for_monitoring(session_id, qdrant_service)
            
            # Wait for Prometheus to start scraping
            print("[WAIT] Waiting for Prometheus to start scraping (15 seconds)...")
            time.sleep(15)
            print()
            
            # Step 4: Check Prometheus targets
            self.check_prometheus_targets()
            
            # Step 5: Run vLLM workload to generate metrics (only if service is ready)
            if vllm_ready:
                self.run_vllm_workload(vllm_service, num_prompts=10)
            else:
                print("[SKIP] Skipping vLLM workload - service is not running\n")
            
            # Wait for final metrics to be collected
            print("[WAIT] Waiting for final metrics to be scraped (10 seconds)...")
            time.sleep(10)
            print()
            
            # Step 6: Collect metrics
            self.collect_metrics(session_id, window_minutes=5)
            
            # Check final status
            self.get_session_status(session_id)
            
            # Step 7: Stop session
            self.stop_session(session_id)
            
            print("=" * 70)
            print("[SUCCESS] Workflow completed successfully!")
            print("=" * 70)
            print()
            print("Next steps:")
            print("  - Check collected metrics in ./metrics_output/")
            print("  - View Prometheus UI at http://localhost:9090")
            print("  - View Grafana dashboards at http://localhost:3000")
            print()
            
        except Exception as e:
            print(f"\n[ERROR] Error during workflow: {e}")
            raise
        
        finally:
            # Cleanup
            self.cleanup_services()


def main():
    """Run the example workflow."""
    workflow = MonitoringWorkflow()
    workflow.run_full_workflow()


if __name__ == "__main__":
    main()
