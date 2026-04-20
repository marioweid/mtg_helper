"""Tests for the EUR price cap filter on /suggest and /build."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import asyncpg
import pytest_asyncio
from httpx import AsyncClient

from mtg_helper.main import app
from tests.conftest import (
    DOCKSIDE_SCRYFALL_ID,
    DOUBLING_SEASON_SCRYFALL_ID,
    RHYSTIC_STUDY_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_deck,
)


def _make_ai_client() -> MagicMock:
    async def _embed(texts: list[str], **_: object) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]

    ai = MagicMock()
    ai.embed = AsyncMock(side_effect=_embed)
    return ai


def _set_qdrant_empty() -> None:
    mock = MagicMock()
    mock.search = AsyncMock(return_value=[])
    app.state.qdrant_client = mock


async def _set_tags(pool: asyncpg.Pool, scryfall_id: UUID, tags: list[str]) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE cards SET tags = $1::text[] WHERE scryfall_id = $2",
            tags,
            scryfall_id,
        )


@pytest_asyncio.fixture(autouse=True)
async def _reset_card_tags(db_pool: asyncpg.Pool):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE cards SET tags = ARRAY[]::text[]")
    yield


# ── /suggest price cap ──────────────────────────────────────────────────────


async def test_suggest_with_price_cap_excludes_expensive(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """With a 50-cent cap, only cards priced <= €0.50 survive.

    Sol Ring (€0.20) passes. Rhystic Study (€12), Doubling Season (€45),
    Dockside (no EUR price) are excluded.
    """
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, RHYSTIC_STUDY_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOCKSIDE_SCRYFALL_ID, ["ramp"])

    deck_id = await create_test_deck(client, name="Price Cap Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "max_price_cents": 50},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Sol Ring" in names
    assert "Rhystic Study" not in names
    assert "Doubling Season" not in names
    assert "Dockside Extortionist" not in names


async def test_suggest_null_eur_price_excluded_when_cap_active(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Cards with no EUR price must be excluded — safe default."""
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, DOCKSIDE_SCRYFALL_ID, ["ramp"])

    deck_id = await create_test_deck(client, name="Null Price Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "max_price_cents": 10000},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Dockside Extortionist" not in names


async def test_suggest_without_cap_includes_all(client: AsyncClient, db_pool: asyncpg.Pool) -> None:
    """No cap → expensive cards allowed (color-identity still applies)."""
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    deck_id = await create_test_deck(client, name="Uncapped Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert {"Sol Ring", "Doubling Season"}.issubset(names)


# ── /build price cap ────────────────────────────────────────────────────────


async def test_build_honors_request_override_cap(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    deck_id = await create_test_deck(client, name="Build Price Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/build",
        json={"stage": "ramp", "max_price_cents": 50},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Doubling Season" not in names
    if names:
        assert names == {"Sol Ring"}


# ── Deck persistence ────────────────────────────────────────────────────────


async def test_deck_create_persists_max_price_cents(client: AsyncClient) -> None:
    from tests.conftest import HAZEL_SCRYFALL_ID

    resp = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "name": "Budget Deck",
            "max_price_cents": 50,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["max_price_cents"] == 50


async def test_deck_update_clears_cap_with_zero(client: AsyncClient) -> None:
    from tests.conftest import HAZEL_SCRYFALL_ID

    resp = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "name": "Toggleable Deck",
            "max_price_cents": 200,
        },
    )
    assert resp.status_code == 201
    deck_id = resp.json()["data"]["id"]

    clear = await client.patch(f"/api/v1/decks/{deck_id}", json={"max_price_cents": 0})
    assert clear.status_code == 200
    assert clear.json()["data"]["max_price_cents"] is None


# ── /suggest price floor ────────────────────────────────────────────────────


async def test_suggest_with_price_floor_excludes_cheap(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """With a 50-cent floor, Sol Ring (€0.20) is excluded; Doubling Season (€45) passes.

    Dockside (no EUR price) is also excluded — safe default for null prices.
    """
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOCKSIDE_SCRYFALL_ID, ["ramp"])

    deck_id = await create_test_deck(client, name="Price Floor Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "min_price_cents": 50},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Sol Ring" not in names
    assert "Doubling Season" in names
    assert "Dockside Extortionist" not in names


async def test_suggest_price_range_bounds_both_sides(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Range €0.10 – €1.00 keeps Sol Ring (€0.20) and excludes Doubling Season (€45)."""
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    deck_id = await create_test_deck(client, name="Price Range Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={
            "prompt": "ramp",
            "count": 10,
            "min_price_cents": 10,
            "max_price_cents": 100,
        },
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Doubling Season" not in names
    assert "Sol Ring" in names


# ── /build price floor ──────────────────────────────────────────────────────


async def test_build_honors_request_override_floor(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    deck_id = await create_test_deck(client, name="Build Floor Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/build",
        json={"stage": "ramp", "min_price_cents": 100},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Sol Ring" not in names
    if names:
        assert names == {"Doubling Season"}


# ── Deck persistence of min floor ───────────────────────────────────────────


async def test_deck_create_persists_min_price_cents(client: AsyncClient) -> None:
    from tests.conftest import HAZEL_SCRYFALL_ID

    resp = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "name": "Floor Deck",
            "min_price_cents": 100,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["min_price_cents"] == 100


async def test_deck_update_clears_floor_with_zero(client: AsyncClient) -> None:
    from tests.conftest import HAZEL_SCRYFALL_ID

    resp = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "name": "Toggleable Floor Deck",
            "min_price_cents": 200,
        },
    )
    assert resp.status_code == 201
    deck_id = resp.json()["data"]["id"]

    clear = await client.patch(f"/api/v1/decks/{deck_id}", json={"min_price_cents": 0})
    assert clear.status_code == 200
    assert clear.json()["data"]["min_price_cents"] is None


async def test_build_uses_deck_stored_floor_when_request_omits(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Stored deck floor applies when the request has no override."""
    from tests.conftest import HAZEL_SCRYFALL_ID

    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    create = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "name": "Stored Floor Deck",
            "min_price_cents": 100,
        },
    )
    assert create.status_code == 201
    deck_id = create.json()["data"]["id"]

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/build",
        json={"stage": "ramp"},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Sol Ring" not in names


async def test_build_uses_deck_stored_cap_when_request_omits(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Stored deck cap applies when the request has no override."""
    from tests.conftest import HAZEL_SCRYFALL_ID

    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    create = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "name": "Stored Cap Deck",
            "max_price_cents": 50,
        },
    )
    assert create.status_code == 201
    deck_id = create.json()["data"]["id"]

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/build",
        json={"stage": "ramp"},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Doubling Season" not in names
