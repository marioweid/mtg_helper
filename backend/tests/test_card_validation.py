"""Tests for card name resolution via the AI chat endpoint."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from mtg_helper.main import app
from tests.conftest import HAZEL_SCRYFALL_ID


def _make_ai_client(response_text: str) -> MagicMock:
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = response_text

    response = MagicMock()
    response.choices = [choice]

    emb_item = MagicMock()
    emb_item.embedding = [0.0] * 1536
    emb_item.index = 0
    emb_response = MagicMock()
    emb_response.data = [emb_item]

    ai = MagicMock()
    ai.chat = MagicMock()
    ai.chat.completions = MagicMock()
    ai.chat.completions.create = AsyncMock(return_value=response)
    ai.embeddings = MagicMock()
    ai.embeddings.create = AsyncMock(return_value=emb_response)
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


# Card name resolution is exercised through the chat endpoint (which still uses
# the LLM and validates its card suggestions against the database).


async def test_resolve_exact_match_via_chat(client: AsyncClient) -> None:
    """Exact card name from LLM chat response is resolved and returned."""
    deck_id = await _create_hazel_deck(client)
    app.state.ai_client = _make_ai_client(_card_json(["Sol Ring"]))

    resp = await client.post(f"/api/v1/decks/{deck_id}/chat", json={"message": "suggest ramp"})

    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["data"]["suggestions"]]
    assert "Sol Ring" in names


async def test_resolve_fuzzy_match_via_chat(client: AsyncClient) -> None:
    """Slightly misspelled name in LLM chat response is fuzzy-matched."""
    deck_id = await _create_hazel_deck(client)
    app.state.ai_client = _make_ai_client(_card_json(["Doublin Season"]))

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/chat", json={"message": "suggest enchantments"}
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    names = [s["name"] for s in data["suggestions"]]
    assert "Doubling Season" in names


async def test_color_identity_violations_excluded_from_chat(client: AsyncClient) -> None:
    """Cards outside the commander's color identity are excluded from chat suggestions."""
    deck_id = await _create_hazel_deck(client)
    # Rhystic Study is Blue — outside Hazel's GW identity; Sol Ring is colorless (OK)
    app.state.ai_client = _make_ai_client(_card_json(["Rhystic Study", "Sol Ring"]))

    resp = await client.post(f"/api/v1/decks/{deck_id}/chat", json={"message": "suggest cards"})

    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["data"]["suggestions"]]
    assert "Rhystic Study" not in names
    assert "Sol Ring" in names


async def test_unknown_card_not_in_chat_suggestions(client: AsyncClient) -> None:
    """Unknown card names from LLM are silently dropped from chat suggestions."""
    deck_id = await _create_hazel_deck(client)
    app.state.ai_client = _make_ai_client(_card_json(["Sol Ring", "ZZZFakeCardXXX"]))

    resp = await client.post(f"/api/v1/decks/{deck_id}/chat", json={"message": "suggest cards"})

    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["data"]["suggestions"]]
    assert "ZZZFakeCardXXX" not in names
    assert "Sol Ring" in names
