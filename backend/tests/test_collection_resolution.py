"""Tests for deck-level suggestion_collection_ids resolution."""

from uuid import UUID

import asyncpg
import pytest_asyncio
from httpx import AsyncClient

from mtg_helper.main import app
from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    HAZEL_SCRYFALL_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
)

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
    resp = await client.post("/api/v1/me/collections", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


async def _create_deck(
    client: AsyncClient,
    *,
    owner_id: str,  # noqa: ARG001 — auth override drives ownership
    suggestion_collection_ids: list[str] | None = None,
    name: str = "Resolution Deck",
) -> str:
    payload: dict = {
        "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
        "name": name,
    }
    if suggestion_collection_ids is not None:
        payload["suggestion_collection_ids"] = suggestion_collection_ids
    resp = await client.post("/api/v1/decks", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


@pytest_asyncio.fixture(autouse=True)
async def _reset_card_tags(db_pool: asyncpg.Pool):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE cards SET tags = ARRAY[]::text[]")
    yield


async def test_no_deck_filter_no_request_override_returns_unfiltered(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "NoFilter")
    deck_id = await _create_deck(client, owner_id=account_id)

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert {"Sol Ring", "Doubling Season"}.issubset(names)


async def test_deck_suggestion_collection_ids_restricts_suggestions(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "DeckFilter")
    col = await _create_collection(client, account_id, "Mine")
    await _add_to_collection(client, col, SOL_RING_SCRYFALL_ID, "c19", "255")
    deck_id = await _create_deck(client, owner_id=account_id, suggestion_collection_ids=[col])

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert names == {"Sol Ring"}


async def test_multiple_collections_form_union(client: AsyncClient, db_pool: asyncpg.Pool) -> None:
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "Union")
    col_a = await _create_collection(client, account_id, "A")
    col_b = await _create_collection(client, account_id, "B")
    await _add_to_collection(client, col_a, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _add_to_collection(client, col_b, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")
    deck_id = await _create_deck(
        client, owner_id=account_id, suggestion_collection_ids=[col_a, col_b]
    )

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert {"Sol Ring", "Doubling Season"}.issubset(names)


async def test_request_collection_ids_override_deck_selection(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "Override")
    deck_col = await _create_collection(client, account_id, "Deck")
    override_col = await _create_collection(client, account_id, "Override")
    await _add_to_collection(client, deck_col, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")
    await _add_to_collection(client, override_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    deck_id = await _create_deck(client, owner_id=account_id, suggestion_collection_ids=[deck_col])

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "collection_ids": [override_col]},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert names == {"Sol Ring"}


async def test_empty_request_collection_ids_disables_filter(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    await _set_tags(db_pool, SOL_RING_SCRYFALL_ID, ["ramp"])
    await _set_tags(db_pool, DOUBLING_SEASON_SCRYFALL_ID, ["ramp"])

    account_id = await create_test_account(client, "EmptyOverride")
    deck_col = await _create_collection(client, account_id, "Deck")
    await _add_to_collection(client, deck_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    deck_id = await _create_deck(client, owner_id=account_id, suggestion_collection_ids=[deck_col])

    # Passing an explicit empty list overrides the deck's stored filter.
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "collection_ids": []},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert {"Sol Ring", "Doubling Season"}.issubset(names)
