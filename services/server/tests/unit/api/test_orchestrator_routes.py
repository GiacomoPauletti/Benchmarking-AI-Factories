"""
Unit tests for orchestrator control API endpoints.
Tests the /api/v1/orchestrator/* routes for starting/stopping the orchestrator.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.orchestrator_routes import (
    router,
    set_orchestrator_control_functions,
    OrchestratorStartRequest,
    OrchestratorStatusResponse,
)


@pytest.fixture
def mock_session():
    """Create a mock orchestrator session."""
    class MockSession:
        def __init__(self):
            self.alive = False
            self.last_check = None
            self.last_error = "Orchestrator not started"
            self.job_id = None
            self.job_state = None
            self.started_at = None
            self.time_limit_minutes = None
            self.orchestrator_url = None

    return MockSession()


@pytest.fixture
def test_app(mock_session):
    """Create a test FastAPI app with orchestrator routes."""
    fastapi_app = FastAPI()
    fastapi_app.include_router(router, prefix="/api/v1")

    # Create mock control functions
    async def mock_start(time_limit_minutes: int):
        mock_session.alive = True
        mock_session.job_id = "12345"
        mock_session.started_at = datetime.now(timezone.utc)
        mock_session.time_limit_minutes = time_limit_minutes
        mock_session.orchestrator_url = "http://test:8003"
        mock_session.last_error = None
        return {"success": True, "job_id": "12345"}

    async def mock_stop():
        mock_session.alive = False
        mock_session.job_id = None
        mock_session.started_at = None
        mock_session.time_limit_minutes = None
        mock_session.orchestrator_url = None
        mock_session.last_error = "Orchestrator stopped by user"
        return {"success": True}

    # Register control functions
    set_orchestrator_control_functions(
        get_session_fn=lambda: mock_session,
        start_fn=mock_start,
        stop_fn=mock_stop,
    )

    return fastapi_app


@pytest.fixture
def client(test_app):
    """Create a test client."""
    return TestClient(test_app)


class TestOrchestratorStatus:
    """Tests for GET /api/v1/orchestrator/status."""

    def test_status_when_not_running(self, client, mock_session):
        """Test status endpoint when orchestrator is not running."""
        response = client.get("/api/v1/orchestrator/status")

        assert response.status_code == 200
        data = response.json()
        assert data["running"] is False
        assert data["job_id"] is None
        assert data["orchestrator_url"] is None
        assert data["remaining_seconds"] is None

    def test_status_when_running(self, client, mock_session):
        """Test status endpoint when orchestrator is running."""
        # Simulate running state
        mock_session.alive = True
        mock_session.job_id = "67890"
        mock_session.started_at = datetime.now(timezone.utc)
        mock_session.time_limit_minutes = 30
        mock_session.orchestrator_url = "http://node1:8003"
        mock_session.last_error = None

        response = client.get("/api/v1/orchestrator/status")

        assert response.status_code == 200
        data = response.json()
        assert data["running"] is True
        assert data["job_id"] == "67890"
        assert data["orchestrator_url"] == "http://node1:8003"
        assert data["time_limit_minutes"] == 30
        # remaining_seconds should be calculated (close to 30*60)
        assert data["remaining_seconds"] is not None
        assert data["remaining_seconds"] > 0


class TestOrchestratorStart:
    """Tests for POST /api/v1/orchestrator/start."""

    def test_start_with_default_time_limit(self, client, mock_session):
        """Test starting orchestrator with default time limit."""
        response = client.post("/api/v1/orchestrator/start", json={})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == "12345"
        assert data["time_limit_minutes"] == 30  # default

    def test_start_with_custom_time_limit(self, client, mock_session):
        """Test starting orchestrator with custom time limit."""
        response = client.post(
            "/api/v1/orchestrator/start",
            json={"time_limit_minutes": 120}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["time_limit_minutes"] == 120

    def test_start_when_already_running(self, client, mock_session):
        """Test starting orchestrator when already running returns 409."""
        # Simulate already running
        mock_session.alive = True
        mock_session.job_id = "existing_job"

        response = client.post("/api/v1/orchestrator/start", json={})

        assert response.status_code == 409
        assert "already running" in response.json()["detail"].lower()

    def test_start_with_invalid_time_limit_too_low(self, client, mock_session):
        """Test starting with time limit below minimum (5 min) fails validation."""
        response = client.post(
            "/api/v1/orchestrator/start",
            json={"time_limit_minutes": 2}
        )

        assert response.status_code == 422  # Validation error

    def test_start_with_invalid_time_limit_too_high(self, client, mock_session):
        """Test starting with time limit above maximum (240 min) fails validation."""
        response = client.post(
            "/api/v1/orchestrator/start",
            json={"time_limit_minutes": 500}
        )

        assert response.status_code == 422  # Validation error


class TestOrchestratorStop:
    """Tests for POST /api/v1/orchestrator/stop."""

    def test_stop_when_running(self, client, mock_session):
        """Test stopping a running orchestrator."""
        # Simulate running state
        mock_session.alive = True
        mock_session.job_id = "active_job"

        response = client.post("/api/v1/orchestrator/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_stop_when_not_running(self, client, mock_session):
        """Test stopping when orchestrator is not running returns 409."""
        response = client.post("/api/v1/orchestrator/stop")

        assert response.status_code == 409
        assert "not running" in response.json()["detail"].lower()


class TestOrchestratorControlNotInitialized:
    """Tests for when orchestrator control functions are not initialized."""

    def test_status_not_initialized(self):
        """Test status endpoint when control functions not set."""
        from api.orchestrator_routes import (
            router as fresh_router,
            set_orchestrator_control_functions,
        )

        # Reset the module-level functions
        set_orchestrator_control_functions(None, None, None)

        test_app = FastAPI()
        test_app.include_router(fresh_router, prefix="/api/v1")
        client = TestClient(test_app)

        response = client.get("/api/v1/orchestrator/status")
        assert response.status_code == 500
        assert "not initialized" in response.json()["detail"].lower()
