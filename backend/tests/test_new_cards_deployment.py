"""Deployment contracts for New Cards execution permissions."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_db,
    pytest.mark.skipif(shutil.which("docker") is None, reason="Docker Compose CLI is unavailable"),
]

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("compose_files", "expected"),
    [
        (["docker-compose.prod.yml"], "${ENABLE_NEW_CARDS_WORKER:-true}"),
        (["docker-compose.yml"], "false"),
        (["docker-compose.yml", "docker-compose.live.yml"], "false"),
    ],
)
def test_worker_permission_is_forwarded_only_in_production(
    compose_files: list[str], expected: str
) -> None:
    command = ["docker", "compose"]
    for path in compose_files:
        command.extend(["-f", path])
    command.extend(["config", "--no-interpolate", "--format", "json"])
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    backend_environment = json.loads(result.stdout)["services"]["backend"]["environment"]
    if isinstance(backend_environment, list):
        backend_environment = dict(value.split("=", 1) for value in backend_environment)

    assert backend_environment.get("ENABLE_NEW_CARDS_WORKER") == expected
