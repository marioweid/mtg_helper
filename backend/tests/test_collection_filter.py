"""Tests for the collection ownership filter on /suggest and /build."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import asyncpg
import pytest_asyncio
from httpx import AsyncClient

from mtg_helper.main import app
from mtg_helper.services import collection_service
from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
    create_test_deck,
)


def _make_ai_client() -> MagicMock:
    """Mock LLMClient with an embedding method of the correct dimension."""

    async def _embed(texts: list[str], **_: object) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]

    ai = MagicMock()
    ai.embed = AsyncMock(side_effect=_embed)
    return ai


def _set_qdrant_empty() -> None:
    mock = MagicMock()
    mock.search = AsyncMock(return_value=[])
    app.state.qdrant_client = mock


async def _get_card_id(pool: asyncpg.Pool, scryfall_id: UUID) -> UUID:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM cards WHERE scryfall_id = $1", scryfall_id)
    return row["id"]


async def _set_tags(pool: asyncpg.Pool, scryfall_id: UUID, tags: list[str]) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE cards SET tags = $1::text[] WHERE scryfall_id = $2",
            tags,
            scryfall_id,
        )


async def _insert_alternate_printing(
    pool: asyncpg.Pool,
    *,
    scryfall_id: UUID,
    oracle_id: UUID,
    source_scryfall_id: UUID,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cards (
                scryfall_id, oracle_id, name, color_identity, oracle_text, type_line,
                cmc, mana_cost, rarity, set_code, legalities, prices, tags
            )
            SELECT $1, $2, name, color_identity, oracle_text, type_line,
                   cmc, mana_cost, rarity, 'alt', legalities, prices, tags
            FROM cards
            WHERE scryfall_id = $3
            ON CONFLICT (scryfall_id) DO NOTHING
            """,
            scryfall_id,
            oracle_id,
            source_scryfall_id,
        )


async def _add_to_collection(
    client: AsyncClient,
    cid: str,
    scryfall_id: UUID,
    set_code: str,
    collector_number: str,
) -> None:
    resp = await client.post(
        f"/api/v1/collections/{cid}/cards",
        json={
            "scryfall_id": str(scryfall_id),
            "quantity": 1,
            "set_code": set_code,
            "collector_number": collector_number,
        },
    )
    assert resp.status_code == 201


async def _create_collection(client: AsyncClient, label: str) -> tuple[str, str]:
    account_id = await create_test_account(client, f"{label} User")
    create = await client.post("/api/v1/me/collections", json={"name": f"{label} Collection"})
    assert create.status_code == 201
    return account_id, create.json()["data"]["id"]


@pytest_asyncio.fixture(autouse=True)
async def _reset_card_tags(db_pool: asyncpg.Pool):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE cards SET tags = ARRAY[]::text[]")
    yield


# ── get_owned_card_ids* ─────────────────────────────────────────────────────


async def test_get_owned_card_ids_returns_distinct_cards(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    _, cid = await _create_collection(client, "Distinct")
    await _add_to_collection(client, cid, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _add_to_collection(client, cid, SOL_RING_SCRYFALL_ID, "lea", "270")
    await _add_to_collection(client, cid, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")

    sol_id = await _get_card_id(db_pool, SOL_RING_SCRYFALL_ID)
    ds_id = await _get_card_id(db_pool, DOUBLING_SEASON_SCRYFALL_ID)

    result = await collection_service.get_owned_card_ids(db_pool, UUID(cid))
    assert result == frozenset({sol_id, ds_id})


async def test_get_owned_card_ids_empty_collection(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    _, cid = await _create_collection(client, "Empty")
    result = await collection_service.get_owned_card_ids(db_pool, UUID(cid))
    assert result == frozenset()


async def test_get_owned_card_ids_for_collections_unions_across(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    await create_test_account(client, "UnionLookup")
    create_a = await client.post("/api/v1/me/collections", json={"name": "A"})
    create_b = await client.post("/api/v1/me/collections", json={"name": "B"})
    col_a = create_a.json()["data"]["id"]
    col_b = create_b.json()["data"]["id"]
    await _add_to_collection(client, col_a, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _add_to_collection(client, col_b, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")

    sol_id = await _get_card_id(db_pool, SOL_RING_SCRYFALL_ID)
    ds_id = await _get_card_id(db_pool, DOUBLING_SEASON_SCRYFALL_ID)

    result = await collection_service.get_owned_card_ids_for_collections(
        db_pool, [UUID(col_a), UUID(col_b)]
    )
    assert result == frozenset({sol_id, ds_id})


async def test_get_owned_card_ids_for_collections_empty_list(
    db_pool: asyncpg.Pool,
) -> None:
    result = await collection_service.get_owned_card_ids_for_collections(db_pool, [])
    assert result == frozenset()


# ── /suggest collection filter ───────────────────────────────────────────────


async def test_suggest_with_collection_filters_to_owned(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    _, cid = await _create_collection(client, "Filter")
    await _add_to_collection(client, cid, SOL_RING_SCRYFALL_ID, "c19", "255")

    deck_id = await create_test_deck(client, name="Filter Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "collection_ids": [cid]},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert names == {"Sol Ring"}


async def test_suggest_without_collection_returns_unfiltered(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    deck_id = await create_test_deck(client, name="Unfiltered Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert {"Sol Ring", "Doubling Season"}.issubset(names)


async def test_empty_collection_returns_no_suggestions(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    _, cid = await _create_collection(client, "EmptyFilter")
    deck_id = await create_test_deck(client, name="Empty Filter Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "collection_ids": [cid]},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["suggestions"] == []


# ── /build collection filter ─────────────────────────────────────────────────


async def test_build_with_collection_ids_filters_stage(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    _, cid = await _create_collection(client, "Build")
    await _add_to_collection(client, cid, SOL_RING_SCRYFALL_ID, "c19", "255")

    deck_id = await create_test_deck(client, name="Build Filter Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/build",
        json={"stage": "ramp", "collection_ids": [cid]},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Doubling Season" not in names
    if names:
        assert names == {"Sol Ring"}


async def test_build_excludes_alternate_printing_already_in_deck(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_empty()

    alternate_sol_ring = UUID("33333333-36f5-40e7-91de-9c8c1b44da67")
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _insert_alternate_printing(
        db_pool,
        scryfall_id=alternate_sol_ring,
        oracle_id=UUID("33333333-aaaa-40e7-91de-9c8c1b44da67"),
        source_scryfall_id=SOL_RING_SCRYFALL_ID,
    )

    deck_id = await create_test_deck(client, name="Alternate Printing Deck")
    add = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID), "added_by": "user"},
    )
    assert add.status_code == 201

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/build",
        json={"stage": "ramp", "target": 10},
    )

    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Sol Ring" not in names
