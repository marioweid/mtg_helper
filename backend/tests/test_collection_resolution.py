"""Tests for deck-level suggestion_collection_ids resolution."""

from uuid import UUID

import asyncpg
from httpx import AsyncClient

from tests.conftest import (
    DOUBLING_SEASON_ORACLE_ID,
    DOUBLING_SEASON_SCRYFALL_ID,
    HAZEL_SCRYFALL_ID,
    SOL_RING_ORACLE_ID,
    SOL_RING_SCRYFALL_ID,
    create_test_account,
)

SOURCE_TAG_ID = UUID("10000000-0000-0000-0000-000000000011")


async def _seed_source_membership(pool: asyncpg.Pool) -> None:
    """Give the suggestion fixtures a single direct Scryfall source membership."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO scryfall_tags (id, slug, metadata) VALUES ($1, 'test-source', $2)",
            SOURCE_TAG_ID,
            '{"label":"Test source"}',
        )
        await conn.execute(
            "INSERT INTO scryfall_tag_descendants (ancestor_id, descendant_id) VALUES ($1, $1)",
            SOURCE_TAG_ID,
        )
        await conn.executemany(
            "INSERT INTO scryfall_tag_memberships "
            "(tag_id, oracle_id, details) VALUES ($1, $2, '{}')",
            [(SOURCE_TAG_ID, SOL_RING_ORACLE_ID), (SOURCE_TAG_ID, DOUBLING_SEASON_ORACLE_ID)],
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
    archetype_tags: list[str] | None = None,
    name: str = "Resolution Deck",
) -> str:
    payload: dict = {
        "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
        "name": name,
    }
    if suggestion_collection_ids is not None:
        payload["suggestion_collection_ids"] = suggestion_collection_ids
    if archetype_tags is not None:
        payload["archetype_tags"] = archetype_tags
    resp = await client.post("/api/v1/decks", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def test_no_deck_filter_no_request_override_returns_unfiltered(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    await _seed_source_membership(db_pool)
    account_id = await create_test_account(client, "NoFilter")
    deck_id = await _create_deck(client, owner_id=account_id, archetype_tags=[str(SOURCE_TAG_ID)])

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert {"Sol Ring", "Doubling Season"}.issubset(names)


async def test_deck_suggestion_collection_ids_restricts_suggestions(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    await _seed_source_membership(db_pool)
    account_id = await create_test_account(client, "DeckFilter")
    col = await _create_collection(client, account_id, "Mine")
    await _add_to_collection(client, col, SOL_RING_SCRYFALL_ID, "c19", "255")
    deck_id = await _create_deck(
        client,
        owner_id=account_id,
        suggestion_collection_ids=[col],
        archetype_tags=[str(SOURCE_TAG_ID)],
    )

    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert names == {"Sol Ring"}


async def test_multiple_collections_form_union(client: AsyncClient, db_pool: asyncpg.Pool) -> None:
    await _seed_source_membership(db_pool)
    account_id = await create_test_account(client, "Union")
    col_a = await _create_collection(client, account_id, "A")
    col_b = await _create_collection(client, account_id, "B")
    await _add_to_collection(client, col_a, SOL_RING_SCRYFALL_ID, "c19", "255")
    await _add_to_collection(client, col_b, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")
    deck_id = await _create_deck(
        client,
        owner_id=account_id,
        suggestion_collection_ids=[col_a, col_b],
        archetype_tags=[str(SOURCE_TAG_ID)],
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
    await _seed_source_membership(db_pool)
    account_id = await create_test_account(client, "Override")
    deck_col = await _create_collection(client, account_id, "Deck")
    override_col = await _create_collection(client, account_id, "Override")
    await _add_to_collection(client, deck_col, DOUBLING_SEASON_SCRYFALL_ID, "rav", "262")
    await _add_to_collection(client, override_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    deck_id = await _create_deck(
        client,
        owner_id=account_id,
        suggestion_collection_ids=[deck_col],
        archetype_tags=[str(SOURCE_TAG_ID)],
    )

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
    await _seed_source_membership(db_pool)
    account_id = await create_test_account(client, "EmptyOverride")
    deck_col = await _create_collection(client, account_id, "Deck")
    await _add_to_collection(client, deck_col, SOL_RING_SCRYFALL_ID, "c19", "255")
    deck_id = await _create_deck(
        client,
        owner_id=account_id,
        suggestion_collection_ids=[deck_col],
        archetype_tags=[str(SOURCE_TAG_ID)],
    )

    # Passing an explicit empty list overrides the deck's stored filter.
    resp = await client.post(
        f"/api/v1/decks/{deck_id}/suggest",
        json={"prompt": "ramp", "count": 10, "collection_ids": []},
    )
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["data"]["suggestions"]}
    assert {"Sol Ring", "Doubling Season"}.issubset(names)
