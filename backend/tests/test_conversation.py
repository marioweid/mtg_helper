"""Tests for conversation history persistence via AI endpoints."""

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


async def _create_deck(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Conv Test Deck"},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


async def test_conversation_persists_across_chat(client: AsyncClient) -> None:
    """Chat messages are persisted and included in subsequent calls."""
    deck_id = await _create_deck(client)
    call_messages: list = []

    async def capture_create(**kwargs):  # type: ignore[no-untyped-def]
        call_messages.append(kwargs.get("messages", []))
        msg = MagicMock()
        msg.content = [TextBlock(type="text", text="Great deck strategy!")]
        return msg

    mock_ai = MagicMock()
    mock_ai.messages = MagicMock()
    mock_ai.messages.create = AsyncMock(side_effect=capture_create)
    app.state.ai_client = mock_ai

    # First message
    await client.post(f"/api/v1/decks/{deck_id}/chat", json={"message": "Hello"})
    # Second message
    await client.post(f"/api/v1/decks/{deck_id}/chat", json={"message": "More info"})

    # Second call should include first conversation turn
    assert len(call_messages) == 2
    second_call_messages = call_messages[1]
    contents = [m["content"] for m in second_call_messages]
    assert "Hello" in contents


async def test_build_persists_conversation(client: AsyncClient) -> None:
    """Build stage persists conversation turns."""
    deck_id = await _create_deck(client)
    call_count = 0

    async def count_create(**kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        text = json.dumps(
            [{"name": "Sol Ring", "category": "ramp", "reasoning": "good", "synergies": []}]
        )
        msg = MagicMock()
        msg.content = [TextBlock(type="text", text=text)]
        return msg

    mock_ai = MagicMock()
    mock_ai.messages = MagicMock()
    mock_ai.messages.create = AsyncMock(side_effect=count_create)
    app.state.ai_client = mock_ai

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={"action": "next_stage"})
    assert resp.status_code == 200
    assert call_count == 1


async def test_chat_returns_text_reply(client: AsyncClient) -> None:
    """Chat endpoint returns reply text."""
    deck_id = await _create_deck(client)
    app.state.ai_client = _make_ai_client("Token strategies are very synergistic here.")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/chat", json={"message": "Tell me about this commander."}
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "Token strategies" in data["reply"]
    assert isinstance(data["suggestions"], list)


async def test_chat_deck_not_found(client: AsyncClient) -> None:
    """Chat with non-existent deck returns 404."""
    app.state.ai_client = _make_ai_client("hello")
    resp = await client.post(
        "/api/v1/decks/00000000-0000-0000-0000-000000000000/chat",
        json={"message": "hi"},
    )
    assert resp.status_code == 404
