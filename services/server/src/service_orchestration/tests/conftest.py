import pytest
from unittest.mock import MagicMock, AsyncMock
import sys
from pathlib import Path

# Add src to path so we can import service_orchestration
src_path = Path(__file__).parent.parent.parent
sys.path.append(str(src_path))

from service_orchestration.core.service_orchestrator import ServiceOrchestrator, VLLMEndpoint

@pytest.fixture
def mock_slurm_client():
    client = MagicMock()
    client.submit_job.return_value = "12345"
    client.get_job_status.return_value = "running"
    client.cancel_job.return_value = True
    return client

@pytest.fixture
def mock_service_manager():
    manager = MagicMock()
    manager.list_services.return_value = []
    manager.get_service.return_value = None
    manager.is_group.return_value = False
    return manager

@pytest.fixture
def mock_job_builder():
    builder = MagicMock()
    builder.build_job.return_value = {"script": "script", "job": "job"}
    return builder

@pytest.fixture
def mock_recipe_loader():
    loader = MagicMock()
    # Default to single node recipe (no gpu_per_replica)
    loader.load.return_value = {"name": "test-recipe", "gpu_per_replica": None}
    loader.list_all.return_value = []
    return loader

@pytest.fixture
def mock_endpoint_resolver():
    resolver = MagicMock()
    resolver.resolve.return_value = "http://node1:8001"
    return resolver

@pytest.fixture
def orchestrator(mock_slurm_client, mock_service_manager, mock_job_builder, mock_recipe_loader, mock_endpoint_resolver):
    """Create a ServiceOrchestrator with mocked dependencies"""
    # Patch the dependencies in the class or during init
    # Since ServiceOrchestrator instantiates them in __init__, we need to patch the classes
    
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("service_orchestration.core.service_orchestrator.SlurmClient", lambda: mock_slurm_client)
        mp.setattr("service_orchestration.core.service_orchestrator.ServiceManager", lambda: mock_service_manager)
        mp.setattr("service_orchestration.core.service_orchestrator.JobBuilder", lambda base_path: mock_job_builder)
        mp.setattr("service_orchestration.core.service_orchestrator.RecipeLoader", lambda path: mock_recipe_loader)
        mp.setattr("service_orchestration.core.service_orchestrator.EndpointResolver", lambda s, sm, rl: mock_endpoint_resolver)
        
        orch = ServiceOrchestrator()
        # Also mock the http client
        orch._http_client = AsyncMock()
        
        yield orch
