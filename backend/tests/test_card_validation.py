"""Tests for card name resolution via the AI build endpoint."""

import json
from unittest.mock import AsyncMock, MagicMock

from anthropic.types import TextBlock
from httpx import AsyncClient

from mtg_helper.main import app
from tests.conftest import HAZEL_SCRYFALL_ID


def _make_ai_client(response_text: str) -> MagicMock:
    message = MagicMock()
    message.content = [TextBlock(type="text", text=response_text)]
    ai = MagicMock()
    ai.messages = MagicMock()
    ai.messages.create = AsyncMock(return_value=message)
    return ai


def _card_json(names: list[str]) -> str:
    items = [
        {"name": n, "category": "theme", "reasoning": "good card", "synergies": []} for n in names
    ]
    return json.dumps(items)


async def _create_hazel_deck(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Validation Test"},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


async def test_resolve_exact_match_via_build(client: AsyncClient) -> None:
    """Exact card name match returns the card in suggestions."""
    deck_id = await _create_hazel_deck(client)
    app.state.ai_client = _make_ai_client(_card_json(["Sol Ring"]))

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["data"]["suggestions"]]
    assert "Sol Ring" in names
    assert resp.json()["data"]["unresolved"] == []


async def test_resolve_fuzzy_match_via_build(client: AsyncClient) -> None:
    """Slightly misspelled name is fuzzy-matched to the correct card."""
    deck_id = await _create_hazel_deck(client)
    # "Doublin Season" should fuzzy-match to "Doubling Season"
    app.state.ai_client = _make_ai_client(_card_json(["Doublin Season"]))

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    names = [s["name"] for s in data["suggestions"]]
    assert "Doubling Season" in names
    assert "Doublin Season" not in data["unresolved"]


async def test_unresolved_names_reported(client: AsyncClient) -> None:
    """Card names with no match appear in unresolved list."""
    deck_id = await _create_hazel_deck(client)
    app.state.ai_client = _make_ai_client(_card_json(["Sol Ring", "ZZZFakeCardXXX"]))

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "ZZZFakeCardXXX" in data["unresolved"]
    assert any(s["name"] == "Sol Ring" for s in data["suggestions"])


async def test_color_identity_violations_excluded(client: AsyncClient) -> None:
    """Cards outside the commander's color identity are excluded (not returned as suggestions)."""
    deck_id = await _create_hazel_deck(client)
    # Rhystic Study is Blue — outside Hazel's GW identity
    app.state.ai_client = _make_ai_client(_card_json(["Rhystic Study", "Sol Ring"]))

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    names = [s["name"] for s in data["suggestions"]]
    assert "Rhystic Study" not in names
    assert "Sol Ring" in names


async def test_case_insensitive_match(client: AsyncClient) -> None:
    """Lowercase name still resolves to the correct card."""
    deck_id = await _create_hazel_deck(client)
    app.state.ai_client = _make_ai_client(_card_json(["sol ring"]))

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    names = [s["name"] for s in data["suggestions"]]
    assert "Sol Ring" in names
