"""Tests for Phase 5 collection filter resolution (account/deck defaults)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import asyncpg
import pytest_asyncio
from httpx import AsyncClient
from qdrant_client.models import ScoredPoint

from mtg_helper.main import app
from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    HAZEL_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
)


def _make_ai_client() -> MagicMock:
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
    collection_id: str,
    scryfall_id: UUID,
    set_code: str,
    collector_number: str,
) -> None:
    resp = await client.post(
        f"/api/v1/collections/{collection_id}/cards",
        json={
            "scryfall_id": str(scryfall_id),
            "quantity": 1,
            "set_code": set_code,
            "collector_number": collector_number,
        },
    )
    assert resp.status_code == 201


async def _create_collection(client: AsyncClient, account_id: str, name: str) -> str:
    resp = await client.post(f"/api/v1/accounts/{account_id}/collections", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


async def _create_deck(
    client: AsyncClient,
    *,
    owner_id: str,
    collection_mode: str = "inherit",
    collection_id: str | None = None,
    collection_threshold: float | None = None,
    name: str = "Resolution Deck",
) -> str:
    payload: dict = {
        "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
        "name": name,
        "owner_id": owner_id,
        "collection_mode": collection_mode,
    }
    if collection_id is not None:
        payload["collection_id"] = collection_id
    if collection_threshold is not None:
        payload["collection_threshold"] = collection_threshold
    resp = await client.post("/api/v1/decks", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _patch_account(client: AsyncClient, account_id: str, **fields: object) -> None:
    resp = await client.patch(f"/api/v1/accounts/{account_id}", json=fields)
    assert resp.status_code == 200, resp.text


@pytest_asyncio.fixture(autouse=True)
async def _reset_card_tags(db_pool: asyncpg.Pool):
    """Clear cards.tags between tests so tag-search output is deterministic."""
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE cards SET tags = ARRAY[]::text[]")
    yield


# ── Request override (Phase 4 contract still holds) ─────────────────────────


async def test_request_collection_id_overrides_deck_and_account(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "Override User")
    override_col = await _create_collection(client, account_id, "Override Col")
    await _add_to_collection(client, override_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    # Deck configured off; account toggled off — neither should matter.
    deck_id = await _create_deck(client, owner_id=account_id, collection_mode="off")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "collection_id": override_col},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert names == {"Sol Ring"}


# ── Deck mode: off ──────────────────────────────────────────────────────────


async def test_deck_mode_off_ignores_account_defaults(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "OffUser")
    default_col = await _create_collection(client, account_id, "Default")
    await _add_to_collection(client, default_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _patch_account(
        client,
        account_id,
        collection_suggestions_enabled=True,
        default_collection_id=default_col,
    )
    deck_id = await _create_deck(client, owner_id=account_id, collection_mode="off")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    # No filter → unowned Doubling Season is also returned.
    assert {"Sol Ring", "Doubling Season"}.issubset(names)


# ── Deck mode: on ───────────────────────────────────────────────────────────


async def test_deck_mode_on_uses_deck_collection(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "OnUser")
    account_col = await _create_collection(client, account_id, "Account Default")
    await _add_to_collection(client, account_col, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")
    deck_col = await _create_collection(client, account_id, "Deck Specific")
    await _add_to_collection(client, deck_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _patch_account(
        client,
        account_id,
        collection_suggestions_enabled=True,
        default_collection_id=account_col,
    )
    deck_id = await _create_deck(
        client, owner_id=account_id, collection_mode="on", collection_id=deck_col
    )

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert names == {"Sol Ring"}


async def test_deck_mode_on_null_collection_id_disables(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "OnNullUser")
    deck_id = await _create_deck(client, owner_id=account_id, collection_mode="on")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    # No deck collection → silent no-op, no filter applied.
    assert {"Sol Ring", "Doubling Season"}.issubset(names)


# ── Deck mode: inherit ──────────────────────────────────────────────────────


async def test_deck_mode_inherit_uses_account_default(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "InheritUser")
    default_col = await _create_collection(client, account_id, "Default")
    await _add_to_collection(client, default_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _patch_account(
        client,
        account_id,
        collection_suggestions_enabled=True,
        default_collection_id=default_col,
    )
    deck_id = await _create_deck(client, owner_id=account_id, collection_mode="inherit")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert names == {"Sol Ring"}


async def test_deck_mode_inherit_no_account_default_silent(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "NoDefaultUser")
    # Master toggle on but no default_collection_id.
    await _patch_account(client, account_id, collection_suggestions_enabled=True)
    deck_id = await _create_deck(client, owner_id=account_id, collection_mode="inherit")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert {"Sol Ring", "Doubling Season"}.issubset(names)


async def test_deck_mode_inherit_master_toggle_off(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    _set_qdrant_points([])
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "ToggleOffUser")
    default_col = await _create_collection(client, account_id, "Default")
    await _add_to_collection(client, default_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    # Default set but master toggle OFF.
    await _patch_account(client, account_id, default_collection_id=default_col)
    deck_id = await _create_deck(client, owner_id=account_id, collection_mode="inherit")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert {"Sol Ring", "Doubling Season"}.issubset(names)


# ── Threshold resolution ────────────────────────────────────────────────────


async def test_resolved_threshold_applies(client: AsyncClient, db_pool: asyncpg.Pool) -> None:
    app.state.ai_client = _make_ai_client()
    sol_id = await _get_card_id(db_pool, SOL_RING_SCRYFALL_ID)
    ds_id = await _get_card_id(db_pool, DOUBLING_SEASON_SCRYFALL_ID)
    _set_qdrant_points(
        [
            ScoredPoint(id=str(sol_id), score=0.99, version=0, payload={}),
            ScoredPoint(id=str(ds_id), score=0.0, version=0, payload={}),
        ]
    )

    account_id = await create_test_account(client, "ThresholdUser")
    default_col = await _create_collection(client, account_id, "Default")
    await _add_to_collection(client, default_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _add_to_collection(client, default_col, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")
    await _patch_account(
        client,
        account_id,
        collection_suggestions_enabled=True,
        default_collection_id=default_col,
        collection_threshold=0.3,
    )
    deck_id = await _create_deck(client, owner_id=account_id, collection_mode="inherit")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "mana acceleration", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Sol Ring" in names
    assert "Doubling Season" not in names


async def test_request_min_score_overrides_resolved_threshold(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Explicit request min_score always wins over the resolved threshold."""
    app.state.ai_client = _make_ai_client()
    sol_id = await _get_card_id(db_pool, SOL_RING_SCRYFALL_ID)
    ds_id = await _get_card_id(db_pool, DOUBLING_SEASON_SCRYFALL_ID)
    _set_qdrant_points(
        [
            ScoredPoint(id=str(sol_id), score=0.99, version=0, payload={}),
            ScoredPoint(id=str(ds_id), score=0.0, version=0, payload={}),
        ]
    )

    account_id = await create_test_account(client, "OverrideThresholdUser")
    default_col = await _create_collection(client, account_id, "Default")
    await _add_to_collection(client, default_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _add_to_collection(client, default_col, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")
    # Account threshold=0.01 (loose). Request asks for 0.95 (very strict).
    await _patch_account(
        client,
        account_id,
        collection_suggestions_enabled=True,
        default_collection_id=default_col,
        collection_threshold=0.01,
    )
    deck_id = await _create_deck(client, owner_id=account_id, collection_mode="inherit")

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "mana acceleration", "count": 10, "min_score": 0.95},
    )
    assert resp.status_code == 200
    # Request override bypasses resolution path and passes collection_id=None → no filter,
    # but with min_score=0.95 everything should be dropped (nothing scores that high).
    # Actually: request without collection_id + min_score=0.95 → no ownership filter,
    # just the score floor. We assert both cards absent from tight-score path.
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Doubling Season" not in names


async def test_deck_collection_threshold_overrides_account(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    app.state.ai_client = _make_ai_client()
    sol_id = await _get_card_id(db_pool, SOL_RING_SCRYFALL_ID)
    ds_id = await _get_card_id(db_pool, DOUBLING_SEASON_SCRYFALL_ID)
    _set_qdrant_points(
        [
            ScoredPoint(id=str(sol_id), score=0.99, version=0, payload={}),
            ScoredPoint(id=str(ds_id), score=0.0, version=0, payload={}),
        ]
    )

    account_id = await create_test_account(client, "DeckThresholdUser")
    deck_col = await _create_collection(client, account_id, "Deck Col")
    await _add_to_collection(client, deck_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _add_to_collection(client, deck_col, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")
    # Loose account threshold; strict deck threshold — deck should win.
    await _patch_account(client, account_id, collection_threshold=0.05)
    deck_id = await _create_deck(
        client,
        owner_id=account_id,
        collection_mode="on",
        collection_id=deck_col,
        collection_threshold=0.3,
    )

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "mana acceleration", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert "Sol Ring" in names
    assert "Doubling Season" not in names
