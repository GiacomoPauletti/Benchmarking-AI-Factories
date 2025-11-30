"""
ServiceManager Unit Tests

These tests verify ServiceManager functionality including replica group
management and the get_replica_info method.
"""

import pytest
from unittest.mock import Mock

from service_orchestration.managers.service_manager import ServiceManager


class TestServiceManagerReplicaHandling:
    """Test ServiceManager replica group functionality."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset ServiceManager singleton before each test."""
        ServiceManager._instance = None
        yield
        ServiceManager._instance = None

    @pytest.fixture
    def service_manager(self):
        """Create a fresh ServiceManager instance."""
        return ServiceManager()

    def test_create_replica_group(self, service_manager):
        """Test that create_replica_group correctly initializes a group."""
        group_id = service_manager.create_replica_group(
            recipe_name="inference/vllm-single-node",
            num_nodes=2,
            replicas_per_node=4,
            total_replicas=8
        )

        assert group_id is not None
        group_info = service_manager.get_group_info(group_id)
        assert group_info is not None
        assert group_info["recipe_name"] == "inference/vllm-single-node"
        assert group_info["num_nodes"] == 2
        assert group_info["replicas_per_node"] == 4
        assert group_info["total_replicas"] == 8

    def test_add_replica_to_group(self, service_manager):
        """Test that add_replica correctly adds replicas to a group."""
        group_id = service_manager.create_replica_group(
            recipe_name="inference/vllm-single-node",
            num_nodes=1,
            replicas_per_node=2,
            total_replicas=2
        )

        service_manager.add_replica(
            group_id=group_id,
            job_id="12345",
            node_index=0,
            replica_index=0,
            port=8001,
            gpu_id=0
        )

        replicas = service_manager.get_all_replicas_flat(group_id)
        assert len(replicas) == 1
        assert replicas[0]["id"] == "12345:8001"
        assert replicas[0]["port"] == 8001

    def test_get_replica_info_returns_replica_with_recipe_name(self, service_manager):
        """Test that get_replica_info returns replica info with parent group's recipe_name."""
        group_id = service_manager.create_replica_group(
            recipe_name="inference/vllm-single-node",
            num_nodes=1,
            replicas_per_node=2,
            total_replicas=2
        )

        service_manager.add_replica(
            group_id=group_id,
            job_id="12345",
            node_index=0,
            replica_index=0,
            port=8001,
            gpu_id=0
        )
        service_manager.add_replica(
            group_id=group_id,
            job_id="12345",
            node_index=0,
            replica_index=1,
            port=8002,
            gpu_id=1
        )

        # Test get_replica_info for first replica
        replica_info = service_manager.get_replica_info("12345:8001")
        assert replica_info is not None
        assert replica_info["id"] == "12345:8001"
        assert replica_info["port"] == 8001
        assert replica_info["gpu_id"] == 0
        assert replica_info["group_id"] == group_id
        assert replica_info["recipe_name"] == "inference/vllm-single-node"

        # Test get_replica_info for second replica
        replica_info = service_manager.get_replica_info("12345:8002")
        assert replica_info is not None
        assert replica_info["id"] == "12345:8002"
        assert replica_info["port"] == 8002
        assert replica_info["gpu_id"] == 1
        assert replica_info["recipe_name"] == "inference/vllm-single-node"

    def test_get_replica_info_returns_none_for_nonexistent_replica(self, service_manager):
        """Test that get_replica_info returns None for nonexistent replica."""
        replica_info = service_manager.get_replica_info("99999:8001")
        assert replica_info is None

    def test_get_replica_info_includes_node_info(self, service_manager):
        """Test that get_replica_info includes node hostname when available."""
        group_id = service_manager.create_replica_group(
            recipe_name="inference/vllm-single-node",
            num_nodes=1,
            replicas_per_node=1,
            total_replicas=1
        )

        service_manager.add_replica(
            group_id=group_id,
            job_id="12345",
            node_index=0,
            replica_index=0,
            port=8001,
            gpu_id=0
        )

        # Update node info
        service_manager.update_node_info(group_id, "12345", "compute-node-001")

        replica_info = service_manager.get_replica_info("12345:8001")
        assert replica_info is not None
        assert replica_info["node"] == "compute-node-001"

    def test_get_group_for_replica(self, service_manager):
        """Test that get_group_for_replica correctly maps replica to group."""
        group_id = service_manager.create_replica_group(
            recipe_name="inference/vllm-single-node",
            num_nodes=1,
            replicas_per_node=1,
            total_replicas=1
        )

        service_manager.add_replica(
            group_id=group_id,
            job_id="12345",
            node_index=0,
            replica_index=0,
            port=8001,
            gpu_id=0
        )

        found_group_id = service_manager.get_group_for_replica("12345:8001")
        assert found_group_id == group_id

    def test_get_group_for_replica_returns_none_for_nonexistent(self, service_manager):
        """Test that get_group_for_replica returns None for nonexistent replica."""
        result = service_manager.get_group_for_replica("99999:8001")
        assert result is None


class TestServiceManagerServiceHandling:
    """Test ServiceManager individual service (non-replica) functionality."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset ServiceManager singleton before each test."""
        ServiceManager._instance = None
        yield
        ServiceManager._instance = None

    @pytest.fixture
    def service_manager(self):
        """Create a fresh ServiceManager instance."""
        return ServiceManager()

    def test_register_and_get_service(self, service_manager):
        """Test that services can be registered and retrieved."""
        service_manager.register_service({
            "id": "12345",
            "name": "vllm-test",
            "recipe_name": "inference/vllm-single-node",
            "status": "running",
            "config": {"model": "meta-llama/Llama-2-7b"}
        })

        service_info = service_manager.get_service("12345")
        assert service_info is not None
        assert service_info["id"] == "12345"
        assert service_info["name"] == "vllm-test"
        assert service_info["recipe_name"] == "inference/vllm-single-node"

    def test_get_service_returns_none_for_nonexistent(self, service_manager):
        """Test that get_service returns None for nonexistent service."""
        service_info = service_manager.get_service("nonexistent")
        assert service_info is None

    def test_get_service_does_not_return_replica_by_id(self, service_manager):
        """Test that get_service does NOT return replica info (replicas are in groups, not _services)."""
        # Create a group with a replica
        group_id = service_manager.create_replica_group(
            recipe_name="inference/vllm-single-node",
            num_nodes=1,
            replicas_per_node=1,
            total_replicas=1
        )

        service_manager.add_replica(
            group_id=group_id,
            job_id="12345",
            node_index=0,
            replica_index=0,
            port=8001,
            gpu_id=0
        )

        # get_service should NOT find replicas (they're stored in groups, not _services)
        # This confirms the bug we fixed - replicas need get_replica_info
        service_info = service_manager.get_service("12345:8001")
        assert service_info is None

        # But get_replica_info should work
        replica_info = service_manager.get_replica_info("12345:8001")
        assert replica_info is not None
        assert replica_info["id"] == "12345:8001"
