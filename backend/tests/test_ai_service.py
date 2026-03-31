"""Tests for AI deck building endpoints (OpenAI API mocked)."""

import json
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from mtg_helper.main import app
from mtg_helper.services.deck_service import STAGES
from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    HAZEL_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
    create_test_deck,
)


def _make_ai_client(response_text: str) -> MagicMock:
    """Build a mock OpenAI client returning response_text."""
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = response_text

    response = MagicMock()
    response.choices = [choice]

    ai = MagicMock()
    ai.chat = MagicMock()
    ai.chat.completions = MagicMock()
    ai.chat.completions.create = AsyncMock(return_value=response)
    return ai


def _card_json(names: list[str], category: str = "theme") -> str:
    items = [
        {"name": n, "category": category, "reasoning": f"{n} fits", "synergies": []} for n in names
    ]
    return json.dumps(items)


async def _create_deck(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "AI Test Deck"},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


async def test_build_stage_first_stage(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client(_card_json(["Sol Ring"]))

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["stage"] == STAGES[0]
    assert data["stage_number"] == 1
    matched = [s["name"] for s in data["suggestions"]]
    assert "Sol Ring" in matched


async def test_build_stage_advances_deck_stage(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client(_card_json(["Sol Ring"]))

    await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    resp = await client.get(f"/api/v1/decks/{deck_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["stage"] == STAGES[0]


async def test_card_validation_filters_bad_names(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client(_card_json(["Sol Ring", "ZZZFakeCardXXX"]))

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    matched = [s["name"] for s in data["suggestions"]]
    assert "Sol Ring" in matched
    assert "ZZZFakeCardXXX" in data["unresolved"]


async def test_suggest_cards(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client(_card_json(["Sol Ring"], category="ramp"))

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "give me ramp", "count": 5},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["suggestions"]) >= 1
    assert data["suggestions"][0]["name"] == "Sol Ring"
    assert data["suggestions"][0]["category"] == "ramp"


async def test_chat_about_deck_returns_reply(client: AsyncClient) -> None:
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client("This is a great commander for a token strategy!")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/chat",
        json={"message": "What do you think?"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "token" in data["reply"].lower()
    assert data["suggestions"] == []


async def test_build_stage_deck_not_found(client: AsyncClient) -> None:
    app.state.ai_client = _make_ai_client("[]")
    resp = await client.post(
        "/api/v1/decks/00000000-0000-0000-0000-000000000000/build",
        json={"action": "next_stage"},
    )
    assert resp.status_code == 404


async def test_build_stage_includes_preferences_in_prompt(client: AsyncClient) -> None:
    account_id = await create_test_account(client, "Pref User")
    deck_id = await create_test_deck(client, owner_id=account_id)

    await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={"preference_type": "pet_card", "card_scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID)},
    )
    await client.post(
        f"/api/v1/accounts/{account_id}/preferences",
        json={"preference_type": "avoid_archetype", "description": "stax"},
    )

    captured_messages: list = []
    ai_client = _make_ai_client(_card_json(["Sol Ring"]))
    original_create = ai_client.chat.completions.create

    async def capture_and_call(**kwargs):  # type: ignore[no-untyped-def]
        captured_messages.extend(kwargs.get("messages", []))
        return await original_create(**kwargs)

    ai_client.chat.completions.create = capture_and_call
    app.state.ai_client = ai_client

    await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    system_content = next(m["content"] for m in captured_messages if m["role"] == "system")
    assert "PLAYER PREFERENCES" in system_content
    assert "Doubling Season" in system_content
    assert "stax" in system_content


async def test_build_stage_includes_downvoted_cards_in_prompt(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)

    await client.post(
        f"/api/v1/decks/{deck_id}/feedback",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "feedback": "down"},
    )

    captured_messages: list = []
    ai_client = _make_ai_client(_card_json(["Rhystic Study"]))
    original_create = ai_client.chat.completions.create

    async def capture_and_call(**kwargs):  # type: ignore[no-untyped-def]
        captured_messages.extend(kwargs.get("messages", []))
        return await original_create(**kwargs)

    ai_client.chat.completions.create = capture_and_call
    app.state.ai_client = ai_client

    await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    system_content = next(m["content"] for m in captured_messages if m["role"] == "system")
    assert "FEEDBACK" in system_content
    assert "Sol Ring" in system_content


async def test_build_stage_no_owner_skips_preferences(client: AsyncClient) -> None:
    deck_id = await create_test_deck(client)

    captured_messages: list = []
    ai_client = _make_ai_client(_card_json(["Sol Ring"]))
    original_create = ai_client.chat.completions.create

    async def capture_and_call(**kwargs):  # type: ignore[no-untyped-def]
        captured_messages.extend(kwargs.get("messages", []))
        return await original_create(**kwargs)

    ai_client.chat.completions.create = capture_and_call
    app.state.ai_client = ai_client

    await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})

    system_content = next(m["content"] for m in captured_messages if m["role"] == "system")
    assert "PLAYER PREFERENCES" not in system_content
