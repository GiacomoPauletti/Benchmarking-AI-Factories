from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from ..core.service_orchestrator import ServiceOrchestrator
from .conftest import create_mock_recipe

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

    def test_register_endpoint(self, orchestrator, mock_service_manager, mock_endpoint_resolver):
        """Test registering a service endpoint"""
        service_id = "12345"
        host = "node1"
        port = 8001
        
        result = orchestrator.register_endpoint(service_id, host, port, {"model": "gpt2"})
        
        assert result["status"] == "registered"
        assert service_id in orchestrator.registered_endpoints
        assert orchestrator.registered_endpoints[service_id]["url"] == f"http://{host}:{port}"
        mock_service_manager.update_service_status.assert_called_with(service_id, "running")
        mock_endpoint_resolver.register.assert_called_with(service_id, host, port)

    def test_unregister_endpoint(self, orchestrator):
        """Test unregistering a service endpoint"""
        # First register an endpoint
        orchestrator.registered_endpoints["12345"] = {
            "service_id": "12345",
            "host": "node1",
            "port": 8001,
            "url": "http://node1:8001"
        }
        
        result = orchestrator.unregister_endpoint("12345")
        
        assert result["status"] == "unregistered"
        assert "12345" not in orchestrator.registered_endpoints

    def test_start_replica_group(self, orchestrator, mock_slurm_client, mock_service_manager, mock_recipe_loader):
        """Test starting a replica group"""
        recipe_name = "test-replica-recipe"
        config = {"nodes": 2, "gpu_per_replica": 1}
        
        # Mock recipe loader to return a replica group Recipe
        mock_recipe = create_mock_recipe(
            name=recipe_name, 
            category="inference", 
            is_replica=True, 
            gpu=4, 
            nodes=1
        )
        mock_recipe_loader.load.return_value = mock_recipe
        
        # Mock service manager group methods
        mock_service_manager.create_replica_group.return_value = "sg-123"
        mock_service_manager.get_group_info.return_value = {"id": "sg-123", "replicas": []}
        
        result = orchestrator.start_service(recipe_name, config)
        
        assert result["status"] == "submitted"
        assert result["group_id"] == "sg-123"
        mock_service_manager.create_replica_group.assert_called_once()
        # Should add replicas: config nodes=2 * (4 GPUs / 1 per replica) = 8 replicas
        assert mock_service_manager.add_replica.call_count == 8

    def test_stop_service_group(self, orchestrator, mock_slurm_client, mock_service_manager):
        """Test stopping a service group"""
        group_id = "sg-123"
        
        # Mock group info
        mock_service_manager.get_group_info.return_value = {
            "node_jobs": [{"job_id": "job1"}, {"job_id": "job2"}]
        }
        
        result = orchestrator.stop_service_group(group_id)
        
        assert result["status"] == "success"
        assert result["stopped"] == 2
        mock_slurm_client.cancel_job.assert_any_call("job1")
        mock_slurm_client.cancel_job.assert_any_call("job2")
        mock_service_manager.update_group_status.assert_called_with(group_id, "cancelled")

    @pytest.mark.asyncio
    async def test_check_vllm_health_success(self, orchestrator):
        """Test VLLM health check for healthy endpoint"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        orchestrator._http_client.get = AsyncMock(return_value=mock_response)
        
        result = await orchestrator._check_vllm_health("http://node1:8001")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_check_vllm_health_failure(self, orchestrator):
        """Test VLLM health check for unhealthy endpoint"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        orchestrator._http_client.get = AsyncMock(return_value=mock_response)
        
        result = await orchestrator._check_vllm_health("http://node1:8001")
        
        assert result is False

    def test_get_metrics(self, orchestrator):
        """Test getting aggregated metrics"""
        # Setup some metrics
        orchestrator.metrics["total_requests"] = 100
        orchestrator.metrics["failed_requests"] = 5
        
        # Register an endpoint using the new dict format
        orchestrator.registered_endpoints["123"] = {
            "service_id": "123",
            "host": "node1",
            "port": 8001,
            "url": "http://node1:8001",
            "status": "healthy",
            "registered_at": 1234567890
        }
        
        metrics = orchestrator.get_metrics()
        
        assert metrics["global"]["total_requests"] == 100
        assert metrics["global"]["failed_requests"] == 5
        assert "123" in metrics["services"]
        assert metrics["services"]["123"]["status"] == "healthy"

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
        
        def test_get_service_metrics_service_group_synthetic_status(mock_orchestrator):
            """Service groups should expose synthetic metrics with service_status_info."""
            group_id = "sg-123"
            mock_orchestrator.service_manager.create_replica_group(
                recipe_name="inference/vllm-replicas",
                num_nodes=1,
                replicas_per_node=2,
                total_replicas=2,
                config={},
                job_id="123",
            )
            # Group starts as starting and should be reflected in metrics as value 1.
            result = mock_orchestrator.get_service_metrics(group_id)
            assert result.get("success") is True
            metrics = result.get("metrics", "")
            assert "service_status_info" in metrics
            assert f'service_status_info{{service_id="{group_id}"}} 1' in metrics

        def test_service_group_status_running_only_when_all_replicas_ready(mock_orchestrator):
            """Group should remain starting until all replicas are ready/running."""
            group_id = mock_orchestrator.service_manager.create_replica_group(
                recipe_name="inference/vllm-replicas",
                num_nodes=1,
                replicas_per_node=2,
                total_replicas=2,
                config={},
                job_id="999",
            )
            # Add 2 replicas; group starts as starting.
            mock_orchestrator.service_manager.add_replica(
                group_id=group_id,
                job_id="999",
                node_index=0,
                replica_index=0,
                port=8001,
                gpu_id=0,
                status="starting",
            )
            mock_orchestrator.service_manager.add_replica(
                group_id=group_id,
                job_id="999",
                node_index=0,
                replica_index=1,
                port=8002,
                gpu_id=1,
                status="starting",
            )
            assert mock_orchestrator.service_manager.get_group_info(group_id)["status"] == "starting"

            # Mark one replica ready -> group should still be starting.
            mock_orchestrator.service_manager.update_replica_status("999:8001", "ready")
            assert mock_orchestrator.service_manager.get_group_info(group_id)["status"] == "starting"

            # Mark second replica ready -> group becomes running.
            mock_orchestrator.service_manager.update_replica_status("999:8002", "ready")
            assert mock_orchestrator.service_manager.get_group_info(group_id)["status"] == "running"
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

    def test_get_service_returns_group_info(self, orchestrator, mock_service_manager):
        """Test get_service returns group info when service_id is a group"""
        mock_service_manager.is_group.return_value = True
        mock_service_manager.get_group_info.return_value = {
            "id": "sg-123",
            "replicas": [{"id": "r1"}, {"id": "r2"}]
        }
        
        result = orchestrator.get_service("sg-123")
        
        assert result["id"] == "sg-123"
        assert len(result["replicas"]) == 2

    def test_get_service_group_status_counts(self, orchestrator, mock_service_manager):
        """Group status summary should aggregate replica states"""
        mock_service_manager.get_group_info.return_value = {"id": "sg-1"}
        mock_service_manager.get_all_replicas_flat.return_value = [
            {"id": "r1", "status": "running"},
            {"id": "r2", "status": "starting"},
            {"id": "r3", "status": "failed"}
        ]
        orchestrator.service_manager = mock_service_manager
        
        result = orchestrator.get_service_group_status("sg-1")
        
        assert result["overall_status"] == "degraded"
        assert result["healthy_replicas"] == 1
        assert result["failed_replicas"] == 1
