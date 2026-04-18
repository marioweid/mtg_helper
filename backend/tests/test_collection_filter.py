"""Tests for Phase 4 collection filter + score floor on retrieval."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import asyncpg
import pytest_asyncio
from httpx import AsyncClient
from qdrant_client.models import ScoredPoint

from mtg_helper.main import app
from mtg_helper.services import collection_service
from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
    create_test_deck,
)


def _make_ai_client() -> MagicMock:
    """OpenAI mock with an embedding response of the correct dimension."""
    emb_item = MagicMock()
    emb_item.embedding = [0.0] * 1536
    emb_item.index = 0
    emb_response = MagicMock()
    emb_response.data = [emb_item]

    ai = MagicMock()
    ai.embeddings = MagicMock()
    ai.embeddings.create = AsyncMock(return_value=emb_response)
    return ai


def _set_qdrant_points(points: list[ScoredPoint]) -> None:
    mock = MagicMock()
    mock.search = AsyncMock(return_value=points)
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
    create = await client.post(
        f"/api/v1/accounts/{account_id}/collections", json={"name": f"{label} Collection"}
    )
    assert create.status_code == 201
    return account_id, create.json()["data"]["id"]


@pytest_asyncio.fixture(autouse=True)
async def _reset_card_tags(db_pool: asyncpg.Pool):
    """Clear cards.tags before each test to avoid cross-test bleed."""
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE cards SET tags = ARRAY[]::text[]")
    yield


# ── get_owned_card_ids ────────────────────────────────────────────────────────


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


# ── /suggest collection filter ───────────────────────────────────────────────


async def test_suggest_with_collection_filters_to_owned(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    _, cid = await _create_collection(client, "Filter")
    await _add_to_collection(client, cid, SOL_RING_SCRYFALL_ID, "c19", "255")

    deck_id = await create_test_deck(client, name="Filter Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "collection_id": cid},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert names == {"Sol Ring"}


async def test_suggest_without_collection_returns_unfiltered(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])

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


async def test_min_score_drops_low_scoring_candidates(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    sol_id = await _get_card_id(db_pool, SOL_RING_SCRYFALL_ID)
    ds_id = await _get_card_id(db_pool, DOUBLING_SEASON_SCRYFALL_ID)
    # Mock Qdrant so Sol Ring scores near-max, Doubling Season scores 0.
    _set_qdrant_points(
        [
            ScoredPoint(id=str(sol_id), score=0.99, version=0, payload={}),
            ScoredPoint(id=str(ds_id), score=0.0, version=0, payload={}),
        ]
    )

    _, cid = await _create_collection(client, "Threshold")
    await _add_to_collection(client, cid, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _add_to_collection(client, cid, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")

    deck_id = await create_test_deck(client, name="Threshold Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={
            "prompt": "mana acceleration",
            "count": 10,
            "collection_id": cid,
            "min_score": 0.3,
        },
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Sol Ring" in names
    assert "Doubling Season" not in names


async def test_empty_collection_returns_no_suggestions(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])

    _, cid = await _create_collection(client, "EmptyFilter")
    deck_id = await create_test_deck(client, name="Empty Filter Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "collection_id": cid},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["suggestions"] == []


# ── /build collection filter ─────────────────────────────────────────────────


async def test_build_with_collection_id_filters_stage(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])

    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    _, cid = await _create_collection(client, "Build")
    await _add_to_collection(client, cid, SOL_RING_SCRYFALL_ID, "c19", "255")

    deck_id = await create_test_deck(client, name="Build Filter Deck")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/build",
        json={"stage": "ramp", "collection_id": cid},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Doubling Season" not in names
    if names:
        assert names == {"Sol Ring"}
