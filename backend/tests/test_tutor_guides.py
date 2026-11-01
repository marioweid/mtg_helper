"""Authenticated Tutor guide lifecycle checks."""

import asyncio
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from tests.conftest import HAZEL_SCRYFALL_ID


async def _deck_id(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Tutor test deck"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


@pytest.mark.asyncio
async def test_setup_saves_mode_without_starting_a_guide(client: AsyncClient) -> None:
    """Tutor mode is owner-saved and setup remains a no-model action."""
    deck_id = await _deck_id(client)

    saved = await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "cedh"})
    assert saved.status_code == 200
    assert saved.json()["data"]["mode"] == "cedh"
    assert saved.json()["data"]["latest_run"] is None

    loaded = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    assert loaded.status_code == 200
    assert loaded.json()["data"]["mode"] == "cedh"
    assert loaded.json()["data"]["latest_run"] is None


def test_tutor_fixture_commander_is_stable() -> None:
    """The shared Tutor fixture uses the existing deterministic commander identity."""
    assert UUID(str(HAZEL_SCRYFALL_ID)).version == 4


@pytest.mark.asyncio
async def test_freshness_marks_saved_guide_historical_after_actual_card_change(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Actual list identity, rather than a deck timestamp, controls guide freshness."""
    from mtg_helper.models.tutor import TutorGuideDraft
    from mtg_helper.services.tutor import commander

    async def fixed_teacher(_input: object) -> TutorGuideDraft:
        return TutorGuideDraft(title="Hazel guide", content="Interpretation: build a token engine.")

    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})

    created = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert created.status_code == 200
    for _ in range(20):
        await asyncio.sleep(0)
        state = await client.get(f"/api/v1/decks/{deck_id}/tutor")
        if state.json()["data"]["latest_run"]["status"] != "running":
            break
    guide = state.json()["data"]["latest_run"]
    assert guide["status"] == "succeeded"
    assert guide["current"] is True

    changed = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": "3d7b8d2c-36f5-40e7-91de-9c8c1b44da67"},
    )
    assert changed.status_code == 201
    historical = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    assert historical.json()["data"]["latest_run"]["current"] is False
