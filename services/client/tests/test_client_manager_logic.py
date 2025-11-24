import pytest
from types import SimpleNamespace

from client_manager.client_manager import ClientManager, ClientManagerResponseStatus
from client_manager.client_group import ClientGroupStatus


@pytest.fixture(autouse=True)
def reset_client_manager_singleton():
    """Ensure each test gets a fresh ClientManager singleton instance."""
    ClientManager._instance = None  # type: ignore[attr-defined]
    yield
    ClientManager._instance = None  # type: ignore[attr-defined]


def test_set_orchestrator_url_success(monkeypatch):
    manager = ClientManager()

    requested_urls = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"endpoint": "http://orch:9000"}

    def fake_get(url, timeout):  # pylint: disable=unused-argument
        requested_urls.append(url)
        return FakeResponse()

    monkeypatch.setattr("client_manager.client_manager.requests.get", fake_get)

    assert manager.set_orchestrator_url("http://server:8001") is True
    assert manager._orchestrator_url == "http://orch:9000"  # type: ignore[attr-defined]
    assert requested_urls == ["http://server:8001/api/v1/orchestrator/endpoint"]


def test_set_orchestrator_url_handles_non_200(monkeypatch):
    manager = ClientManager()

    class FakeResponse:
        status_code = 503

        @staticmethod
        def json():
            return {}

    monkeypatch.setattr("client_manager.client_manager.requests.get", lambda *args, **kwargs: FakeResponse())

    assert manager.set_orchestrator_url("http://server:8001") is False
    assert manager._orchestrator_url is None  # type: ignore[attr-defined]


def test_set_orchestrator_url_handles_exception(monkeypatch):
    manager = ClientManager()

    def fake_get(*args, **kwargs):  # pylint: disable=unused-argument
        raise RuntimeError("boom")

    monkeypatch.setattr("client_manager.client_manager.requests.get", fake_get)

    assert manager.set_orchestrator_url("http://server:8001") is False
    assert manager._orchestrator_url is None  # type: ignore[attr-defined]


def test_add_client_group_injects_prompt_url(monkeypatch):
    manager = ClientManager()
    manager._server_addr = "http://server:8001"  # type: ignore[attr-defined]
    manager._orchestrator_url = "http://orch:9000"  # type: ignore[attr-defined]

    created = {}

    class FakeClientGroup:
        def __init__(self, group_id, load_config, account=None, use_container=None):  # pylint: disable=unused-argument
            created["group_id"] = group_id
            created["load_config"] = dict(load_config)

    monkeypatch.setattr("client_manager.client_manager.ClientGroup", FakeClientGroup)

    load_config = {
        "service_id": "sg-123",
        "num_clients": 2,
        "requests_per_second": 0.5,
        "duration_seconds": 30,
    }

    status = manager.add_client_group(42, load_config)

    assert status == ClientManagerResponseStatus.OK
    assert load_config["prompt_url"] == "http://orch:9000/api/services/vllm/sg-123/prompt"
    assert created["load_config"]["prompt_url"] == load_config["prompt_url"]


def test_add_client_group_without_orchestrator_keeps_config(monkeypatch):
    manager = ClientManager()
    manager._server_addr = "http://server:8001"  # type: ignore[attr-defined]

    monkeypatch.setattr("client_manager.client_manager.ClientGroup", lambda *args, **kwargs: None)
    monkeypatch.setattr(manager, "set_orchestrator_url", lambda *_args, **_kwargs: False)

    load_config = {
        "service_id": "sg-123",
        "num_clients": 2,
        "requests_per_second": 0.5,
    }

    status = manager.add_client_group(7, load_config)

    assert status == ClientManagerResponseStatus.OK
    assert "prompt_url" not in load_config


def test_run_client_group_rejects_non_running_group():
    manager = ClientManager()
    dummy_group = SimpleNamespace(
        get_status=lambda: ClientGroupStatus.PENDING,
        get_client_address=lambda: "http://client",
    )
    manager._client_groups[1] = dummy_group  # type: ignore[attr-defined]

    result = manager.run_client_group(1)

    assert result[0]["error"] == "client group not running"


def test_run_client_group_forwards_request(monkeypatch):
    manager = ClientManager()

    class RunningGroup:
        def __init__(self):
            self._addr = "http://client"

        def get_status(self):
            return ClientGroupStatus.RUNNING

        def get_client_address(self):
            return self._addr

    manager._client_groups[5] = RunningGroup()  # type: ignore[attr-defined]

    class FakeResponse:
        status_code = 200
        text = "ok"

    captured = {}

    def fake_post(url, timeout):  # pylint: disable=unused-argument
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr("client_manager.client_manager.requests.post", fake_post)

    results = manager.run_client_group(5)

    assert captured["url"] == "http://client/run"
    assert results[0]["status_code"] == 200
    assert results[0]["body"] == "ok"
