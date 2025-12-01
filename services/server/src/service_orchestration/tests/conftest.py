import pytest
from unittest.mock import MagicMock, AsyncMock
import sys
from pathlib import Path

# Add src to path so we can import service_orchestration
src_path = Path(__file__).parent.parent.parent
sys.path.append(str(src_path))

from service_orchestration.core.service_orchestrator import ServiceOrchestrator
from service_orchestration.recipes import (
    Recipe, InferenceRecipe, VectorDbRecipe, StorageRecipe,
    RecipeResources, RecipeCategory
)


def create_mock_recipe(
    name: str = "test-recipe",
    category: str = "inference",
    is_replica: bool = False,
    gpu: int = 1,
    nodes: int = 1
) -> Recipe:
    """Create a mock Recipe object for testing."""
    resources = RecipeResources(nodes=nodes, cpu=4, memory="16G", gpu=gpu, time_limit=60)
    
    if is_replica:
        return InferenceRecipe(
            name=name,
            category=RecipeCategory.INFERENCE,
            container_def=f"{name}.def",
            image=f"{name}.sif",
            resources=resources,
            environment={"TEST": "1"},
            gpu_per_replica=1,
            base_port=8001
        )
    
    if category == "inference":
        return InferenceRecipe(
            name=name,
            category=RecipeCategory.INFERENCE,
            container_def=f"{name}.def",
            image=f"{name}.sif",
            resources=resources,
            environment={"TEST": "1"},
            gpu_per_replica=None,
            base_port=8001
        )
    elif category == "vector-db":
        return VectorDbRecipe(
            name=name,
            category=RecipeCategory.VECTOR_DB,
            container_def=f"{name}.def",
            image=f"{name}.sif",
            resources=resources,
            environment={"TEST": "1"},
            port=6333
        )
    else:
        return StorageRecipe(
            name=name,
            category=RecipeCategory.STORAGE,
            container_def=f"{name}.def",
            image=f"{name}.sif",
            resources=resources,
            environment={"TEST": "1"},
            port=9000
        )


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
    builder.build_job.return_value = {"script": "script", "job": {"name": "test"}}
    return builder

@pytest.fixture
def mock_recipe_loader():
    loader = MagicMock()
    # Default to single node recipe (no gpu_per_replica)
    default_recipe = create_mock_recipe("test-recipe", "inference", is_replica=False)
    loader.load.return_value = default_recipe
    loader.list_all.return_value = [default_recipe]
    loader.get_recipe_port.return_value = 8001
    return loader

@pytest.fixture
def mock_endpoint_resolver():
    resolver = MagicMock()
    resolver.resolve.return_value = "http://node1:8001"
    resolver.register.return_value = None
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
        # Set the endpoint_resolver mock directly for tests that need it
        orch.endpoint_resolver = mock_endpoint_resolver
        
        yield orch
