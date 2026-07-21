import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("BRAND_STUDIO_RUN_E2E") != "1",
    reason="set BRAND_STUDIO_RUN_E2E=1 and start docker compose to run e2e tests",
)

_LONG_RUNNING_SERVICES = {
    "postgres",
    "redis",
    "minio",
    "api",
    "worker",
    "web",
}
_PROXY_SERVICES = {"gateway", "nginx"}


def test_compose_services_are_running_and_healthy() -> None:
    missing, missing_proxy, unhealthy = _wait_for_compose_health()

    assert missing == set()
    assert missing_proxy is False
    assert unhealthy == {}


@pytest.mark.parametrize(
    ("name", "url"),
    [
        ("gateway", lambda: f"http://127.0.0.1:{_config_value('GATEWAY_PORT', '8080')}/health"),
        ("web", lambda: f"http://127.0.0.1:{_config_value('WEB_PORT', '3000')}/api/health"),
        (
            "api ready",
            lambda: f"http://127.0.0.1:{_config_value('API_PORT', '8000')}/api/v1/health/ready",
        ),
        ("api docs", lambda: f"http://127.0.0.1:{_config_value('API_PORT', '8000')}/api/docs"),
        (
            "minio live",
            lambda: f"http://127.0.0.1:{_config_value('MINIO_API_PORT', '9000')}/minio/health/live",
        ),
    ],
)
def test_stack_endpoint_responds(name: str, url) -> None:
    response = _get(url())

    assert response["status"] == 200, name


def test_api_ready_reports_dependencies_ok() -> None:
    url = f"http://127.0.0.1:{_config_value('API_PORT', '8000')}/api/v1/health/ready"
    response = _get(url)
    payload = json.loads(response["body"].decode("utf-8"))

    assert payload["status"] == "ok"
    assert payload["dependencies"] == {
        "database": "ok",
        "redis": "ok",
        "object_storage": "ok",
    }


def _wait_for_compose_health(
    *,
    timeout_seconds: float = 45,
    interval_seconds: float = 1,
) -> tuple[set[str], bool, dict[str, dict[str, Any]]]:
    deadline = time.monotonic() + timeout_seconds
    missing: set[str] = set()
    missing_proxy = True
    unhealthy: dict[str, dict[str, Any]] = {}

    while time.monotonic() < deadline:
        services = _compose_services()
        by_service = {_service_name(service): service for service in services}
        missing = _LONG_RUNNING_SERVICES - by_service.keys()
        proxy_names = _PROXY_SERVICES & by_service.keys()
        missing_proxy = not proxy_names
        unhealthy = {
            name: service
            for name, service in by_service.items()
            if name in _LONG_RUNNING_SERVICES | proxy_names and not _is_running_and_healthy(service)
        }
        if not missing and not missing_proxy and not unhealthy:
            return missing, missing_proxy, unhealthy
        time.sleep(interval_seconds)

    return missing, missing_proxy, unhealthy


def _compose_services() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    if not output:
        return []

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return [json.loads(line) for line in output.splitlines() if line.strip()]

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _service_name(service: dict[str, Any]) -> str:
    value = str(service.get("Service") or service.get("Name") or "")
    if value.startswith("brand-agent-studio-") and value.endswith("-1"):
        return value.removeprefix("brand-agent-studio-").removesuffix("-1")
    return value


def _is_running_and_healthy(service: dict[str, Any]) -> bool:
    state = str(service.get("State", "")).lower()
    health = str(service.get("Health", "")).lower()
    status = str(service.get("Status", "")).lower()

    is_running = state == "running" or "running" in status or "up" in status
    is_unhealthy = health == "unhealthy" or "unhealthy" in status
    is_starting = health == "starting" or "starting" in status
    return is_running and not is_unhealthy and not is_starting


def _get(url: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=10) as response:
            return {
                "status": response.status,
                "body": response.read(),
            }
    except URLError as exc:
        pytest.fail(f"{url} did not respond: {exc}")


def _config_value(name: str, default: str) -> str:
    if name in os.environ:
        return os.environ[name]

    env_file = Path(".env")
    if not env_file.exists():
        return default

    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        if key == name:
            return value.strip().strip('"').strip("'")
    return default
