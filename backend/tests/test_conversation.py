"""Tests for conversation history persistence via AI endpoints."""

from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from mtg_helper.main import app
from tests.conftest import HAZEL_SCRYFALL_ID


def _make_ai_client(response_text: str) -> MagicMock:
    async def _embed(texts: list[str], **_: object) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]

    ai = MagicMock()
    ai.chat = AsyncMock(return_value=response_text)
    ai.embed = AsyncMock(side_effect=_embed)
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

    async def capture_chat(**kwargs: object) -> str:
        call_messages.append(kwargs.get("messages", []))
        return "Great deck strategy!"

    mock_ai = MagicMock()
    mock_ai.chat = AsyncMock(side_effect=capture_chat)
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


async def test_build_uses_embeddings_not_chat_llm(client: AsyncClient) -> None:
    """Build stage uses embeddings for retrieval but does not call the chat LLM."""
    deck_id = await _create_deck(client)
    chat_call_count = 0
    emb_call_count = 0

    async def count_chat(**_: object) -> str:
        nonlocal chat_call_count
        chat_call_count += 1
        return "[]"

    async def count_embed(texts: list[str], **_: object) -> list[list[float]]:
        nonlocal emb_call_count
        emb_call_count += 1
        return [[0.0] * 1536 for _ in texts]

    mock_ai = MagicMock()
    mock_ai.chat = AsyncMock(side_effect=count_chat)
    mock_ai.embed = AsyncMock(side_effect=count_embed)
    app.state.ai_client = mock_ai

    resp = await client.post(f"/api/v1/decks/{deck_id}/build", json={})
    assert resp.status_code == 200
    assert chat_call_count == 0  # LLM not used for build
    assert emb_call_count >= 1  # Embeddings used for Qdrant query


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


async def test_chat_history_is_capped(client: AsyncClient) -> None:
    """Only the most recent _MAX_HISTORY_TURNS turns reach the LLM."""
    import asyncpg

    from mtg_helper.services import ai_service, conversation_service
    from mtg_helper.services.ai_service import _MAX_HISTORY_TURNS

    deck_id = await _create_deck(client)
    pool: asyncpg.Pool = app.state.db_pool
    for i in range(30):
        role = "user" if i % 2 == 0 else "assistant"
        await conversation_service.append_turn(pool, deck_id, role, f"old turn {i}")

    captured: dict[str, object] = {}

    async def capture(**kwargs: object) -> str:
        captured["system"] = kwargs.get("system")
        captured["messages"] = list(kwargs.get("messages", []))
        return "ack"

    mock_ai = MagicMock()
    mock_ai.chat = AsyncMock(side_effect=capture)
    app.state.ai_client = mock_ai

    resp = await client.post(f"/api/v1/decks/{deck_id}/chat", json={"message": "next"})
    assert resp.status_code == 200

    # System instruction is passed separately; messages contain [...history, user].
    assert isinstance(captured["system"], str)
    messages = captured["messages"]
    assert messages[-1]["content"] == "next"
    history_slice = messages[:-1]
    assert len(history_slice) <= _MAX_HISTORY_TURNS

    # First retained turn should be in the last 20 (not "old turn 0").
    assert "old turn 0" not in [m["content"] for m in history_slice]
    assert any("old turn 29" == m["content"] for m in history_slice)

    # Sanity: module constant equals expected cap.
    assert ai_service._MAX_HISTORY_TURNS == 20


async def test_chat_deck_not_found(client: AsyncClient) -> None:
    """Chat with non-existent deck returns 404."""
    app.state.ai_client = _make_ai_client("hello")
    resp = await client.post(
        "/api/v1/decks/00000000-0000-0000-0000-000000000000/chat",
        json={"message": "hi"},
    )
    assert resp.status_code == 404
