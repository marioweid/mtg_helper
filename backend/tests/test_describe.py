"""Tests for the deck description agent endpoint and service."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from mtg_helper.main import app
from mtg_helper.services.ai_service import _parse_describe_response
from tests.conftest import HAZEL_SCRYFALL_ID


def _make_ai_client(response_text: str) -> MagicMock:
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = response_text
    choice.finish_reason = "stop"

    response = MagicMock()
    response.choices = [choice]

    ai = MagicMock()
    ai.chat = MagicMock()
    ai.chat.completions = MagicMock()
    ai.chat.completions.create = AsyncMock(return_value=response)
    return ai


# --- Unit tests for _parse_describe_response ---


def test_parse_describe_response_not_done() -> None:
    raw = "What win condition are you aiming for?"
    reply, done, desc, name = _parse_describe_response(raw)
    assert reply == raw
    assert done is False
    assert desc is None
    assert name is None


def test_parse_describe_response_done_inline() -> None:
    completion = json.dumps(
        {"done": True, "name": "Hazel Tokens", "description": "token aristocrats"}
    )
    raw = f"Here's your strategy!\n{completion}"
    reply, done, desc, name = _parse_describe_response(raw)
    assert done is True
    assert name == "Hazel Tokens"
    assert desc == "token aristocrats"
    assert "Here's your strategy" in reply
    assert "done" not in reply


def test_parse_describe_response_json_only() -> None:
    completion = json.dumps({"done": True, "name": "My Deck", "description": "counters voltron"})
    reply, done, desc, name = _parse_describe_response(completion)
    assert done is True
    assert desc == "counters voltron"
    assert reply  # fallback message set


def test_parse_describe_response_malformed_json() -> None:
    raw = 'What is your strategy? {"done": true, "name": bad json}'
    reply, done, desc, name = _parse_describe_response(raw)
    assert done is False
    assert desc is None


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
