"""Tests for per-account rate limiting on LLM-backed AI endpoints."""

from typing import Any

import pytest
from httpx import AsyncClient
from pydantic_ai.models.test import TestModel

from mtg_helper.main import app
from mtg_helper.services import rate_limit_service
from mtg_helper.services.agents import describe_agent
from tests.conftest import HAZEL_SCRYFALL_ID, create_test_account, set_current_account


def _override_describe() -> Any:
    """Swap the describe agent's model for a fixed TestModel."""
    return describe_agent.get_agent().override(
        model=TestModel(custom_output_args={"reply": "What's your win condition?", "done": False})
    )


@pytest.mark.asyncio
async def test_describe_rate_limit_trips_after_threshold(client: AsyncClient) -> None:
    """31st describe call within the window returns 429 with RATE_LIMITED."""
    await create_test_account(client, "Rate Describe")
    payload = {
        "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
        "bracket": 3,
        "history": [],
        "message": "hi",
    }

    with _override_describe():
        for _ in range(30):
            resp = await client.post("/api/v1/decks/describe", json=payload)
            assert resp.status_code == 200
        resp = await client.post("/api/v1/decks/describe", json=payload)
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_rate_limit_keys_are_per_account(client: AsyncClient) -> None:
    """Different authenticated accounts get independent rate-limit buckets."""
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

    with _override_describe():
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
