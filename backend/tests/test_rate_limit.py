"""Tests for per-key rate limiting on LLM-backed AI endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from mtg_helper.main import app
from mtg_helper.services import rate_limit_service
from tests.conftest import HAZEL_SCRYFALL_ID


def _stub_ai_client() -> MagicMock:
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = "What's your win condition?"
    response = MagicMock()
    response.choices = [choice]
    ai = MagicMock()
    ai.chat = MagicMock()
    ai.chat.completions = MagicMock()
    ai.chat.completions.create = AsyncMock(return_value=response)
    return ai


@pytest.mark.asyncio
async def test_describe_rate_limit_trips_after_threshold(client: AsyncClient) -> None:
    """31st describe call within the window returns 429 with RATE_LIMITED."""
    app.state.ai_client = _stub_ai_client()
    headers = {"X-Account-Id": "rate-test-describe"}
    payload = {
        "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
        "bracket": 3,
        "history": [],
        "message": "hi",
    }

    for _ in range(30):
        resp = await client.post("/api/v1/decks/describe", json=payload, headers=headers)
        assert resp.status_code == 200

    resp = await client.post("/api/v1/decks/describe", json=payload, headers=headers)
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_chat_rate_limit_trips_after_threshold(client: AsyncClient) -> None:
    """21st chat call within the window returns 429."""
    app.state.ai_client = _stub_ai_client()

    # Create deck
    deck_resp = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Rate Test Deck"},
    )
    deck_id = deck_resp.json()["data"]["id"]

    headers = {"X-Account-Id": "rate-test-chat"}
    for _ in range(20):
        resp = await client.post(
            f"/api/v1/decks/{deck_id}/chat", json={"message": "hi"}, headers=headers
        )
        assert resp.status_code == 200

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/chat", json={"message": "hi"}, headers=headers
    )
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_rate_limit_keys_are_per_account(client: AsyncClient) -> None:
    """Different X-Account-Id headers get independent rate-limit buckets."""
    app.state.ai_client = _stub_ai_client()
    payload = {
        "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
        "bracket": 3,
        "history": [],
        "message": "hi",
    }

    # Exhaust account A.
    for _ in range(30):
        resp = await client.post(
            "/api/v1/decks/describe", json=payload, headers={"X-Account-Id": "acct-a"}
        )
        assert resp.status_code == 200
    resp = await client.post(
        "/api/v1/decks/describe", json=payload, headers={"X-Account-Id": "acct-a"}
    )
    assert resp.status_code == 429

    # Account B still has a fresh bucket.
    resp = await client.post(
        "/api/v1/decks/describe", json=payload, headers={"X-Account-Id": "acct-b"}
    )
    assert resp.status_code == 200


def test_rate_limit_service_raises_when_exceeded() -> None:
    """Unit test: direct calls exceeding the window raise RateLimitExceeded."""
    rate_limit_service.reset()
    for _ in range(5):
        rate_limit_service.check("unit:key", 5, 60)
    with pytest.raises(rate_limit_service.RateLimitExceeded):
        rate_limit_service.check("unit:key", 5, 60)
