"""Deployment templates must not reintroduce the retired New Cards AI worker."""

from pathlib import Path

import pytest

from mtg_helper.config import Settings

pytestmark = pytest.mark.no_db
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "template",
    [
        "docker-compose.prod.yml",
        "docker-compose.yml",
        "docker-compose.live.yml",
        "portainer.env.example",
    ],
)
def test_deployment_has_no_retired_worker_permission(template: str) -> None:
    assert "ENABLE_NEW_CARDS_WORKER" not in (ROOT / template).read_text(encoding="utf-8")
    assert "enable_new_cards_worker" not in Settings.model_fields
