"""Tests for the EUR price cap filter on /suggest and /build."""

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


# ── /suggest price floor ────────────────────────────────────────────────────


async def test_suggest_with_price_floor_excludes_cheap(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """With a 50-cent floor, Sol Ring (€0.20) is excluded; Doubling Season (€45) passes.

    Dockside (no EUR price) is also excluded — safe default for null prices.
    """
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
