"""Tests for the EUR price cap filter on /suggest and /build."""

from uuid import UUID

import asyncpg
from httpx import AsyncClient

from tests.conftest import (
    DOCKSIDE_ORACLE_ID,
    DOUBLING_SEASON_ORACLE_ID,
    RHYSTIC_STUDY_ORACLE_ID,
    SOL_RING_ORACLE_ID,
    create_test_deck,
)

SOURCE_TAG_ID = UUID("10000000-0000-0000-0000-000000000012")


async def _seed_source_membership(pool: asyncpg.Pool) -> None:
    """Give price-filter fixtures a direct shared Scryfall source membership."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO scryfall_tags (id, slug, metadata) VALUES ($1, 'price-test', $2)",
            SOURCE_TAG_ID,
            '{"label":"Price test"}',
        )
        await conn.execute(
            "INSERT INTO scryfall_tag_descendants (ancestor_id, descendant_id) VALUES ($1, $1)",
            SOURCE_TAG_ID,
        )
        await conn.executemany(
            "INSERT INTO scryfall_tag_memberships "
            "(tag_id, oracle_id, details) VALUES ($1, $2, '{}')",
            [
                (SOURCE_TAG_ID, SOL_RING_ORACLE_ID),
                (SOURCE_TAG_ID, RHYSTIC_STUDY_ORACLE_ID),
                (SOURCE_TAG_ID, DOUBLING_SEASON_ORACLE_ID),
                (SOURCE_TAG_ID, DOCKSIDE_ORACLE_ID),
            ],
        )


# ── /suggest price cap ──────────────────────────────────────────────────────


async def test_suggest_with_price_cap_excludes_expensive(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """With a 50-cent cap, only cards priced <= €0.50 survive.

    Sol Ring (€0.20) passes. Rhystic Study (€12), Doubling Season (€45),
    Dockside (no EUR price) are excluded.
    """
    await _seed_source_membership(db_pool)
    deck_id = await create_test_deck(
        client, name="Price Cap Deck", archetype_tags=[str(SOURCE_TAG_ID)]
    )

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
    await _seed_source_membership(db_pool)
    deck_id = await create_test_deck(
        client, name="Null Price Deck", archetype_tags=[str(SOURCE_TAG_ID)]
    )

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "max_price_cents": 10000},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Dockside Extortionist" not in names


async def test_suggest_without_cap_includes_all(client: AsyncClient, db_pool: asyncpg.Pool) -> None:
    """No cap → expensive cards allowed (color-identity still applies)."""
    await _seed_source_membership(db_pool)
    deck_id = await create_test_deck(
        client, name="Uncapped Deck", archetype_tags=[str(SOURCE_TAG_ID)]
    )

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
    await _seed_source_membership(db_pool)
    deck_id = await create_test_deck(
        client, name="Build Price Deck", archetype_tags=[str(SOURCE_TAG_ID)]
    )

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
    await _seed_source_membership(db_pool)
    deck_id = await create_test_deck(
        client, name="Price Floor Deck", archetype_tags=[str(SOURCE_TAG_ID)]
    )

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
    await _seed_source_membership(db_pool)
    deck_id = await create_test_deck(
        client, name="Price Range Deck", archetype_tags=[str(SOURCE_TAG_ID)]
    )

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
    await _seed_source_membership(db_pool)
    deck_id = await create_test_deck(
        client, name="Build Floor Deck", archetype_tags=[str(SOURCE_TAG_ID)]
    )

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/build",
        json={"stage": "ramp", "min_price_cents": 100},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Sol Ring" not in names
    if names:
        assert names == {"Doubling Season"}
