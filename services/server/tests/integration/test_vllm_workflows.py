"""Integration tests mirroring the public vLLM examples."""

import os
import sys
from pathlib import Path
from typing import Optional

import pytest
import requests

# Ensure the repository root (so `examples` is importable) is on sys.path.
# The tests may run inside the test container where tests are mounted at /app/tests,
# so compute the repo root by walking upward looking for repo markers instead of
# assuming a fixed parent depth.
def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for _ in range(10):
        # Common repository markers: top-level `services` and `src` directories
        if (p / "services").exists() and (p / "src").exists():
            return p
        # Docker compose files or a git repo are also good indicators
        if (p / "docker-compose.test.yml").exists() or (p / "docker-compose.yml").exists() or (p / ".git").exists():
            return p
        p = p.parent

    # Fall back to environment variable or the container /app path
    env = os.getenv("REPO_ROOT")
    if env:
        return Path(env)
    if Path("/app").exists():
        return Path("/app")
    return Path.cwd()

REPO_ROOT = _find_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import time

# Lightweight copies of the helper functions used by the examples.
# These are defined here so the integration tests can run inside the
# `server-test` container where the top-level `examples/` directory is
# not mounted into `/app`.

def wait_for_server(server_url: str, max_wait: int = 30) -> bool:
    start = time.time()
    while time.time() - start < max_wait:
        try:
            r = requests.get(f"{server_url}/health", timeout=3)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


def wait_for_service_ready(server_url: str, service_id: str, max_wait: int = 300, poll_interval: int = 5) -> Optional[str]:
    api_base = f"{server_url}/api/v1"
    start = time.time()
    while time.time() - start < max_wait:
        try:
            r = requests.get(f"{api_base}/services/{service_id}/status", timeout=5)
            if r.status_code == 200:
                status = r.json().get("status")
                if status == "running":
                    # Verify vLLM models endpoint responds
                    try:
                        models = requests.get(f"{api_base}/vllm/{service_id}/models", timeout=5)
                        if models.status_code == 200:
                            md = models.json()
                            if md.get("success") is True:
                                return f"/api/v1/vllm/{service_id}"
                    except requests.RequestException:
                        pass
        except requests.RequestException:
            pass
        time.sleep(poll_interval)
    return None


def wait_for_service_group_ready(server_url: str, group_id: str, min_healthy: int = 1, timeout: int = 600, check_interval: int = 5) -> bool:
    api_base = f"{server_url}/api/v1"
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{api_base}/service-groups/{group_id}", timeout=5)
            if r.status_code == 200:
                data = r.json()
                node_jobs = data.get("node_jobs", [])
                healthy = 0
                total = data.get("total_replicas") or 0
                for nj in node_jobs:
                    for rep in nj.get("replicas", []):
                        if rep.get("status") in ["running", "ready", "healthy"]:
                            healthy += 1
                if healthy >= min_healthy:
                    return True
        except requests.RequestException:
            pass
        time.sleep(check_interval)
    return False

pytestmark = pytest.mark.integration

SERVER_WAIT_TIMEOUT = int(os.getenv("INTEGRATION_SERVER_WAIT", "60"))
SERVICE_READY_TIMEOUT = int(os.getenv("INTEGRATION_SERVICE_TIMEOUT", "900"))
GROUP_READY_TIMEOUT = int(os.getenv("INTEGRATION_GROUP_TIMEOUT", "900"))
PROMPT_TEXT = os.getenv(
    "INTEGRATION_PROMPT",
    "What is the capital of France? Answer in one sentence."
)
MIN_HEALTHY_REPLICAS = int(os.getenv("INTEGRATION_MIN_HEALTHY_REPLICAS", "1"))


@pytest.fixture(scope="module")
def server_base_url() -> str:
    """Discover and validate the base URL for the running server service."""
    url = _discover_server_url()
    if not wait_for_server(url, max_wait=SERVER_WAIT_TIMEOUT):
        pytest.skip(f"Server not reachable at {url}")
    return url.rstrip("/")


@pytest.fixture(scope="module")
def api_base(server_base_url: str) -> str:
    """Convenience fixture for the API v1 base path."""
    return f"{server_base_url}/api/v1"


def test_vllm_single_node_service_lifecycle(server_base_url: str, api_base: str):
    """Full lifecycle test that mirrors examples/vllm_simple_example.py."""
    service_id: Optional[str] = None
    endpoint_path: Optional[str] = None

    try:
        service = _create_service(api_base, "inference/vllm-single-node")
        service_id = service["id"]

        endpoint_path = wait_for_service_ready(
            server_base_url,
            service_id,
            max_wait=SERVICE_READY_TIMEOUT,
        )
        assert endpoint_path, "Service never reached the running state"

        completion = _prompt_vllm(server_base_url, endpoint_path, PROMPT_TEXT)
        assert completion.get("success"), f"Prompt failed: {completion}"
        assert completion.get("response"), "Response payload is empty"
    finally:
        if service_id:
            _stop_service(api_base, service_id)


def test_vllm_replica_group_service_lifecycle(server_base_url: str, api_base: str):
    """Same flow as the simple example but for the replica recipe."""
    group_id: Optional[str] = None

    try:
        service = _create_service(api_base, "inference/vllm-replicas")
        group_id = service.get("group_id") or service.get("id")
        assert group_id, "Replica group creation did not return a group identifier"

        ready = wait_for_service_group_ready(
            server_base_url,
            group_id,
            min_healthy=MIN_HEALTHY_REPLICAS,
            timeout=GROUP_READY_TIMEOUT,
        )
        assert ready, "Replica group never reached the expected healthy replica count"

        endpoint_path = f"/api/v1/vllm/{group_id}"
        completion = _prompt_vllm(server_base_url, endpoint_path, PROMPT_TEXT)
        assert completion.get("success"), f"Prompt failed: {completion}"
        assert completion.get("response"), "Response payload is empty"
    finally:
        if group_id:
            _stop_service_group(api_base, group_id)


def _discover_server_url() -> str:
    """Resolve the server base URL using env vars or the discovery file."""
    env_url = os.getenv("SERVER_URL")
    if env_url:
        return env_url.rstrip("/")

    endpoint_file = REPO_ROOT / "services" / "server" / ".server-endpoint"
    if endpoint_file.exists():
        content = endpoint_file.read_text(encoding="utf-8").strip()
        if content:
            url = content.rstrip("/")
            # When running inside the test container (`server-test`) the server
            # is reachable at the compose service hostname `server:8001`, not
            # `localhost:8001` (localhost would resolve to the test container).
            # The test runner sets `TESTING=true` in the container; if present,
            # rewrite localhost -> server so network calls reach the server
            # container.
            testing_flag = os.getenv("TESTING")
            if testing_flag and "localhost" in url:
                return url.replace("localhost", "server")
            return url

    return "http://localhost:8001"


def _create_service(api_base: str, recipe_name: str) -> dict:
    response = requests.post(
        f"{api_base}/services",
        json={"recipe_name": recipe_name},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def _prompt_vllm(server_base_url: str, endpoint_path: str, prompt: str) -> dict:
    response = requests.post(
        f"{server_base_url}{endpoint_path}/prompt",
        json={
            "prompt": prompt,
            "max_tokens": int(os.getenv("INTEGRATION_MAX_TOKENS", "100")),
            "temperature": float(os.getenv("INTEGRATION_TEMPERATURE", "0.7")),
        },
        timeout=int(os.getenv("INTEGRATION_PROMPT_TIMEOUT", "180")),
    )
    response.raise_for_status()
    return response.json()


def _stop_service(api_base: str, service_id: str) -> None:
    try:
        requests.delete(f"{api_base}/services/{service_id}", timeout=30)
    except requests.RequestException as exc:
        print(f"Warning: failed to stop service {service_id}: {exc}")


def _stop_service_group(api_base: str, group_id: str) -> None:
    response = requests.delete(f"{api_base}/service-groups/{group_id}", timeout=60)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        # Surface a clear assertion failure if orchestrator/server cannot stop the group
        pytest.fail(f"Failed to stop service group {group_id}: {exc} (status={response.status_code}, body={response.text!r})")
