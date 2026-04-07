"""Tests for conversation history persistence via AI endpoints."""

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
        choice = MagicMock()
        choice.message = MagicMock()
        choice.message.content = "Great deck strategy!"
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    mock_ai = MagicMock()
    mock_ai.chat = MagicMock()
    mock_ai.chat.completions = MagicMock()
    mock_ai.chat.completions.create = AsyncMock(side_effect=capture_create)
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

    async def count_chat(**kwargs):  # type: ignore[no-untyped-def]
        nonlocal chat_call_count
        chat_call_count += 1
        choice = MagicMock()
        choice.message = MagicMock()
        choice.message.content = "[]"
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    async def count_embed(**kwargs):  # type: ignore[no-untyped-def]
        nonlocal emb_call_count
        emb_call_count += 1
        emb_item = MagicMock()
        emb_item.embedding = [0.0] * 1536
        emb_item.index = 0
        emb_resp = MagicMock()
        emb_resp.data = [emb_item]
        return emb_resp

    mock_ai = MagicMock()
    mock_ai.chat = MagicMock()
    mock_ai.chat.completions = MagicMock()
    mock_ai.chat.completions.create = AsyncMock(side_effect=count_chat)
    mock_ai.embeddings = MagicMock()
    mock_ai.embeddings.create = AsyncMock(side_effect=count_embed)
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


async def test_chat_deck_not_found(client: AsyncClient) -> None:
    """Chat with non-existent deck returns 404."""
    app.state.ai_client = _make_ai_client("hello")
    resp = await client.post(
        "/api/v1/decks/00000000-0000-0000-0000-000000000000/chat",
        json={"message": "hi"},
    )
    assert resp.status_code == 404
