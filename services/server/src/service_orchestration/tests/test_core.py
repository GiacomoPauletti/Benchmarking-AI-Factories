from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from ..core.service_orchestrator import ServiceOrchestrator, VLLMEndpoint

class TestServiceOrchestratorCore:
    
    def test_start_service_success(self, orchestrator, mock_slurm_client, mock_service_manager):
        """Test starting a service successfully"""
        recipe_name = "test-recipe"
        config = {"nodes": 1}
        
        result = orchestrator.start_service(recipe_name, config)
        
        assert result["status"] == "submitted"
        assert result["job_id"] == "12345"
        mock_slurm_client.submit_job.assert_called_once()
        mock_service_manager.register_service.assert_called_once()

    def test_start_service_failure(self, orchestrator, mock_slurm_client):
        """Test starting a service with failure"""
        mock_slurm_client.submit_job.side_effect = Exception("SLURM error")
        
        result = orchestrator.start_service("test-recipe", {})
        
        assert result["status"] == "error"
        assert "SLURM error" in result["message"]

    def test_stop_service(self, orchestrator, mock_slurm_client, mock_service_manager):
        """Test stopping a service"""
        service_id = "12345"
        
        result = orchestrator.stop_service(service_id)
        
        assert result["status"] == "cancelled"
        mock_slurm_client.cancel_job.assert_called_with(service_id)
        mock_service_manager.update_service_status.assert_called_with(service_id, "cancelled")

    def test_register_service(self, orchestrator, mock_service_manager):
        """Test registering a service"""
        service_id = "12345"
        host = "node1"
        port = 8001
        model = "gpt2"
        
        # Mock asyncio.create_task to avoid needing an event loop
        with patch("asyncio.create_task") as mock_create_task:
            result = orchestrator.register_service(service_id, host, port, model)
            
            assert result["status"] == "registered"
            assert service_id in orchestrator.endpoints
            assert orchestrator.endpoints[service_id].url == f"http://{host}:{port}"
            mock_service_manager.update_service_status.assert_called_with(service_id, "running")
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_completion_success(self, orchestrator):
        """Test forwarding completion request"""
        # Setup endpoint
        endpoint = VLLMEndpoint("123", "node1", 8001, "gpt2", status="healthy")
        orchestrator.endpoints["123"] = endpoint
        
        # Mock http response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}
        orchestrator._http_client.post.return_value = mock_response
        
        request_data = {"prompt": "Hello"}
        result = await orchestrator.forward_completion(request_data)
        
        assert "_orchestrator_meta" in result
        assert result["_orchestrator_meta"]["service_id"] == "123"
        orchestrator._http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_completion_no_endpoints(self, orchestrator):
        """Test forwarding when no endpoints available"""
        orchestrator.endpoints = {}
        
        with pytest.raises(RuntimeError, match="No healthy vLLM services available"):
            await orchestrator.forward_completion({"prompt": "Hello"})

    def test_load_balancer_round_robin(self, orchestrator):
        """Test round robin load balancing"""
        # Setup endpoints
        ep1 = VLLMEndpoint("1", "node1", 8001, "gpt2", status="healthy")
        ep2 = VLLMEndpoint("2", "node2", 8001, "gpt2", status="healthy")
        
        endpoints = [ep1, ep2]
        
        # We need to run async method
        import asyncio
        
        async def run_test():
            selected1 = await orchestrator.load_balancer.select_endpoint(endpoints)
            selected2 = await orchestrator.load_balancer.select_endpoint(endpoints)
            selected_again = await orchestrator.load_balancer.select_endpoint(endpoints)
            
            assert selected1 != selected2
            assert selected_again == selected1
            
        asyncio.run(run_test())

    def test_start_replica_group(self, orchestrator, mock_slurm_client, mock_service_manager, mock_recipe_loader):
        """Test starting a replica group"""
        recipe_name = "test-replica-recipe"
        config = {"nodes": 2, "gpu_per_replica": 1}
        
        # Mock recipe loader to return a recipe with gpu_per_replica
        mock_recipe_loader.load.return_value = (f"bob/${recipe_name}", {"name": recipe_name, "gpu_per_replica": 1, "resources": {"gpu": 4}})
        
        # Mock group manager
        mock_service_manager.group_manager.create_replica_group.return_value = "sg-123"
        mock_service_manager.get_group_info.return_value = {"id": "sg-123", "replicas": []}
        
        result = orchestrator.start_service(recipe_name, config)
        
        assert result["status"] == "submitted"
        assert result["group_id"] == "sg-123"
        mock_service_manager.group_manager.create_replica_group.assert_called_once()
        # Should add replicas: 2 nodes * (4 GPUs / 1 per replica) = 8 replicas
        assert mock_service_manager.group_manager.add_replica.call_count == 8

    def test_stop_service_group(self, orchestrator, mock_slurm_client, mock_service_manager):
        """Test stopping a service group"""
        group_id = "sg-123"
        
        # Mock group info
        mock_service_manager.group_manager.get_group.return_value = {
            "node_jobs": [{"job_id": "job1"}, {"job_id": "job2"}]
        }
        
        result = orchestrator.stop_service_group(group_id)
        
        assert result["status"] == "success"
        assert result["stopped"] == 2
        mock_slurm_client.cancel_job.assert_any_call("job1")
        mock_slurm_client.cancel_job.assert_any_call("job2")
        mock_service_manager.group_manager.update_group_status.assert_called_with(group_id, "cancelled")

    @pytest.mark.asyncio
    async def test_check_endpoint_healthy(self, orchestrator):
        """Test health check for healthy endpoint"""
        endpoint = VLLMEndpoint("123", "node1", 8001, "gpt2", status="unknown")
        
        # Mock http response
        mock_response = MagicMock()
        mock_response.status_code = 200
        orchestrator._http_client.get.return_value = mock_response
        
        await orchestrator._check_endpoint(endpoint)
        
        assert endpoint.status == "healthy"
        assert endpoint.last_health_check > 0

    @pytest.mark.asyncio
    async def test_check_endpoint_unhealthy(self, orchestrator):
        """Test health check for unhealthy endpoint"""
        endpoint = VLLMEndpoint("123", "node1", 8001, "gpt2", status="healthy")
        
        # Mock http response
        mock_response = MagicMock()
        mock_response.status_code = 500
        orchestrator._http_client.get.return_value = mock_response
        
        await orchestrator._check_endpoint(endpoint)
        
        assert endpoint.status == "unhealthy"

    def test_get_metrics(self, orchestrator):
        """Test getting aggregated metrics"""
        # Setup some metrics
        orchestrator.metrics["total_requests"] = 100
        orchestrator.metrics["failed_requests"] = 5
        
        # Setup an endpoint
        ep = VLLMEndpoint("123", "node1", 8001, "gpt2", status="healthy")
        ep.total_requests = 50
        orchestrator.endpoints["123"] = ep
        
        metrics = orchestrator.get_metrics()
        
        assert metrics["global"]["total_requests"] == 100
        assert metrics["global"]["failed_requests"] == 5
        assert "123" in metrics["services"]
        assert metrics["services"]["123"]["total_requests"] == 50

    def test_get_service_metrics_success(self, orchestrator, mock_service_manager, mock_endpoint_resolver):
        """Test getting Prometheus metrics for a service"""
        service_id = "123"
        mock_service_manager.is_group.return_value = False
        mock_service_manager.get_service.return_value = {
            "id": service_id, 
            "recipe_name": "inference/vllm", 
            "status": "running"
        }
        mock_endpoint_resolver.resolve.return_value = "http://node1:8001"
        
        # Mock requests.get (since get_service_metrics uses requests, not httpx)
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "# HELP metrics"
            mock_get.return_value = mock_response
            
            result = orchestrator.get_service_metrics(service_id)
            
            assert result["success"] is True
            assert result["metrics"] == "# HELP metrics"
            mock_get.assert_called_once()

    def test_get_service_metrics_not_ready(self, orchestrator, mock_service_manager):
        """Test getting metrics for not ready service"""
        service_id = "123"
        mock_service_manager.is_group.return_value = False
        mock_service_manager.get_service.return_value = {
            "id": service_id, 
            "recipe_name": "inference/vllm", 
            "status": "pending"
        }
        
        result = orchestrator.get_service_metrics(service_id)
        
        assert result["success"] is False
        assert "not ready" in result["error"]

    def test_configure_load_balancer(self, orchestrator):
        """Test configuring load balancer strategy"""
        result = orchestrator.configure_load_balancer("least_loaded")
        
        assert result["status"] == "configured"
        assert orchestrator.load_balancer.strategy == "least_loaded"
        
        # Test invalid strategy
        result = orchestrator.configure_load_balancer("invalid")
        assert result["status"] == "error"

    def test_get_job_logs(self, orchestrator, mock_slurm_client):
        """Test getting job logs"""
        job_id = "123"
        mock_slurm_client.get_job_details.return_value = {"job_id": job_id}
        
        # Mock subprocess.run
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "Log content"
            
            # Mock Path.exists
            with patch("pathlib.Path.exists") as mock_exists:
                mock_exists.return_value = True
                
                result = orchestrator.get_service_logs(job_id)
                
                assert result["logs"] == "Log content"
