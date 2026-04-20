"""Tests for the deck description agent endpoint and service."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from mtg_helper.main import app
from mtg_helper.services.ai_service import _parse_describe_response
from tests.conftest import HAZEL_SCRYFALL_ID


def _make_ai_client(response_text: str) -> MagicMock:
    ai = MagicMock()
    ai.chat = AsyncMock(return_value=response_text)
    return ai


# --- Unit tests for _parse_describe_response ---


def test_parse_describe_response_not_done() -> None:
    raw = "What win condition are you aiming for?"
    reply, done, desc, name, targets = _parse_describe_response(raw)
    assert reply == raw
    assert done is False
    assert desc is None
    assert name is None
    assert targets is None


def test_parse_describe_response_done_inline() -> None:
    completion = json.dumps(
        {"done": True, "name": "Hazel Tokens", "description": "token aristocrats"}
    )
    raw = f"Here's your strategy!\n{completion}"
    reply, done, desc, name, _ = _parse_describe_response(raw)
    assert done is True
    assert name == "Hazel Tokens"
    assert desc == "token aristocrats"
    assert "Here's your strategy" in reply
    assert "done" not in reply


def test_parse_describe_response_json_only() -> None:
    completion = json.dumps({"done": True, "name": "My Deck", "description": "counters voltron"})
    reply, done, desc, _name, _targets = _parse_describe_response(completion)
    assert done is True
    assert desc == "counters voltron"
    assert reply  # fallback message set


def test_parse_describe_response_malformed_json() -> None:
    raw = 'What is your strategy? {"done": true, "name": bad json}'
    _reply, done, desc, _name, _targets = _parse_describe_response(raw)
    assert done is False
    assert desc is None


def test_parse_describe_response_with_nested_stage_targets() -> None:
    """Regex-based parser failed on nested stage_targets. Regression guard."""
    completion = json.dumps(
        {
            "done": True,
            "name": "Nicol Bolas Discard",
            "description": "discard control",
            "stage_targets": {"ramp": 12, "interaction": 10, "lands": 37},
        }
    )
    reply, done, desc, name, targets = _parse_describe_response(completion)
    assert done is True
    assert name == "Nicol Bolas Discard"
    assert desc == "discard control"
    assert targets == {"ramp": 12, "interaction": 10, "lands": 37}
    assert reply  # fallback message


# --- Integration tests for POST /decks/describe ---


@pytest.mark.asyncio
async def test_describe_follow_up_question(client: AsyncClient) -> None:
    """Agent returns a follow-up question when it needs more info."""
    app.state.ai_client = _make_ai_client("What win condition are you aiming for?")

    resp = await client.post(
        "/api/v1/decks/describe",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "bracket": 3,
            "history": [],
            "message": "",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["done"] is False
    assert data["description"] is None
    assert "win condition" in data["reply"]


@pytest.mark.asyncio
async def test_describe_completion(client: AsyncClient) -> None:
    """Agent returns done=True with name and description when it synthesizes."""
    completion = json.dumps(
        {
            "done": True,
            "name": "Hazel Tokens",
            "description": "token aristocrats deck with sacrifice payoffs and lifegain",
        }
    )
    app.state.ai_client = _make_ai_client(f"Got it!\n{completion}")

    resp = await client.post(
        "/api/v1/decks/describe",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "bracket": 2,
            "history": [
                {"role": "assistant", "content": "What's your strategy?"},
                {"role": "user", "content": "tokens and sacrifice"},
            ],
            "message": "tokens and sacrifice",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["done"] is True
    assert data["suggested_name"] == "Hazel Tokens"
    assert "aristocrats" in data["description"]


@pytest.mark.asyncio
async def test_describe_history_is_truncated_before_llm(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """History sent to the LLM is capped at _MAX_HISTORY_TURNS turns."""
    from mtg_helper.services import ai_service

    captured: dict[str, list[dict[str, str]]] = {}

    async def fake_call_llm(_ai, _system, history, _user):  # type: ignore[no-untyped-def]
        captured["history"] = list(history)
        return "What's your gameplan?"

    monkeypatch.setattr(ai_service, "_call_llm", fake_call_llm)

    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(24)
    ]
    resp = await client.post(
        "/api/v1/decks/describe",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "bracket": 3,
            "history": long_history,
            "message": "keep going",
        },
    )
    assert resp.status_code == 200
    assert len(captured["history"]) <= ai_service._MAX_HISTORY_TURNS


@pytest.mark.asyncio
async def test_describe_message_max_length_rejected(client: AsyncClient) -> None:
    """Over-long user message is rejected by Pydantic validation."""
    resp = await client.post(
        "/api/v1/decks/describe",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "bracket": 3,
            "history": [],
            "message": "x" * 3000,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_describe_history_length_exceeded_rejected(client: AsyncClient) -> None:
    """Over-long history (>24 entries) is rejected by Pydantic validation."""
    too_long = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(25)
    ]
    resp = await client.post(
        "/api/v1/decks/describe",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "bracket": 3,
            "history": too_long,
            "message": "hi",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_describe_unknown_commander(client: AsyncClient) -> None:
    """Returns 404 when commander scryfall_id is not in the DB."""
    import uuid

    resp = await client.post(
        "/api/v1/decks/describe",
        json={
            "commander_scryfall_id": str(uuid.uuid4()),
            "bracket": 3,
            "history": [],
            "message": "",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "CARD_NOT_FOUND"
