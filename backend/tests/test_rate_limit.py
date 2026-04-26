"""Tests for per-account rate limiting on LLM-backed AI endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from mtg_helper.main import app
from mtg_helper.services import rate_limit_service
from tests.conftest import HAZEL_SCRYFALL_ID, create_test_account, set_current_account


def _stub_ai_client() -> MagicMock:
    ai = MagicMock()
    ai.chat = AsyncMock(return_value="What's your win condition?")
    return ai


@pytest.mark.asyncio
async def test_describe_rate_limit_trips_after_threshold(client: AsyncClient) -> None:
    """31st describe call within the window returns 429 with RATE_LIMITED."""
    app.state.ai_client = _stub_ai_client()
    await create_test_account(client, "Rate Describe")
    payload = {
        "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
        "bracket": 3,
        "history": [],
        "message": "hi",
    }

    for _ in range(30):
        resp = await client.post("/api/v1/decks/describe", json=payload)
        assert resp.status_code == 200

    resp = await client.post("/api/v1/decks/describe", json=payload)
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_chat_rate_limit_trips_after_threshold(client: AsyncClient) -> None:
    """21st chat call within the window returns 429."""
    app.state.ai_client = _stub_ai_client()
    await create_test_account(client, "Rate Chat")

    deck_resp = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Rate Test Deck"},
    )
    deck_id = deck_resp.json()["data"]["id"]

    for _ in range(20):
        resp = await client.post(f"/api/v1/decks/{deck_id}/chat", json={"message": "hi"})
        assert resp.status_code == 200

    resp = await client.post(f"/api/v1/decks/{deck_id}/chat", json={"message": "hi"})
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_rate_limit_keys_are_per_account(client: AsyncClient) -> None:
    """Different authenticated accounts get independent rate-limit buckets."""
    app.state.ai_client = _stub_ai_client()
    payload = {
        "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
        "bracket": 3,
        "history": [],
        "message": "hi",
    }

    from mtg_helper.models.accounts import AccountResponse

    pool = app.state.db_pool
    async with pool.acquire() as conn:
        row_a = await conn.fetchrow(
            "INSERT INTO accounts (display_name, email) VALUES ($1, $2) RETURNING *",
            "Acct A",
            "a@test.local",
        )
        row_b = await conn.fetchrow(
            "INSERT INTO accounts (display_name, email) VALUES ($1, $2) RETURNING *",
            "Acct B",
            "b@test.local",
        )
    acct_a = AccountResponse(
        id=row_a["id"],
        display_name=row_a["display_name"],
        email=row_a["email"],
        created_at=row_a["created_at"],
    )
    acct_b = AccountResponse(
        id=row_b["id"],
        display_name=row_b["display_name"],
        email=row_b["email"],
        created_at=row_b["created_at"],
    )

    set_current_account(acct_a)
    for _ in range(30):
        resp = await client.post("/api/v1/decks/describe", json=payload)
        assert resp.status_code == 200
    resp = await client.post("/api/v1/decks/describe", json=payload)
    assert resp.status_code == 429

    set_current_account(acct_b)
    resp = await client.post("/api/v1/decks/describe", json=payload)
    assert resp.status_code == 200


def test_rate_limit_service_raises_when_exceeded() -> None:
    """Unit test: direct calls exceeding the window raise RateLimitExceeded."""
    rate_limit_service.reset()
    for _ in range(5):
        rate_limit_service.check("unit:key", 5, 60)
    with pytest.raises(rate_limit_service.RateLimitExceeded):
        rate_limit_service.check("unit:key", 5, 60)
