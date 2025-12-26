"""EndpointResolver unit tests.

Focus: multi-node replica groups where the SLURM job spans multiple nodes.
Composite replica IDs (job_id:port) should resolve to the correct node using
replica metadata (node_index) from ServiceManager.
"""

from unittest.mock import MagicMock

import pytest

from service_orchestration.networking.endpoint_resolver import EndpointResolver


@pytest.fixture
def mock_deployer():
    mock = MagicMock()
    mock.get_job_details.return_value = {"nodes": ["node-a", "node-b"]}
    return mock


@pytest.fixture
def mock_service_manager():
    mock = MagicMock()
    mock.get_service.return_value = {"id": "12345", "recipe_name": "inference/vllm-single-node"}
    return mock


@pytest.fixture
def mock_recipe_loader():
    mock = MagicMock()
    mock.get_recipe_port.return_value = 8001
    return mock


def test_resolve_composite_uses_node_index(mock_deployer, mock_service_manager, mock_recipe_loader):
    mock_service_manager.get_replica_info.return_value = {"id": "12345:8002", "node_index": 1}
    resolver = EndpointResolver(mock_deployer, mock_service_manager, mock_recipe_loader)

    assert resolver.resolve("12345:8002") == "http://node-b:8002"


def test_resolve_composite_falls_back_to_first_node_when_no_node_index(mock_deployer, mock_service_manager, mock_recipe_loader):
    mock_service_manager.get_replica_info.return_value = None
    resolver = EndpointResolver(mock_deployer, mock_service_manager, mock_recipe_loader)

    assert resolver.resolve("12345:8002") == "http://node-a:8002"


def test_resolve_prefers_registered_endpoint(mock_deployer, mock_service_manager, mock_recipe_loader):
    mock_service_manager.get_replica_info.return_value = {"id": "12345:8002", "node_index": 1}
    resolver = EndpointResolver(mock_deployer, mock_service_manager, mock_recipe_loader)

    resolver.register("12345:8002", "registered-host", 9000)

    assert resolver.resolve("12345:8002") == "http://registered-host:9000"
    mock_deployer.get_job_details.assert_not_called()
