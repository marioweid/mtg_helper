"""Application-route checks for the Scryfall-only label cutover."""

import json
from uuid import UUID

import asyncpg
import pytest
from httpx import AsyncClient

from tests.conftest import SOL_RING_ORACLE_ID

PARENT = UUID("10000000-0000-0000-0000-000000000001")
CHILD = UUID("10000000-0000-0000-0000-000000000002")


async def _seed_tags(pool: asyncpg.Pool) -> None:
    """Seed a direct child membership and its parent query expansion."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO scryfall_tags (id, slug, metadata) VALUES ($1, $2, $3), ($4, $5, $6)",
            PARENT,
            "parent",
            json.dumps({"label": "Parent"}),
            CHILD,
            "child",
            json.dumps({"label": "Child"}),
        )
        await conn.execute(
            "INSERT INTO scryfall_tag_descendants (ancestor_id, descendant_id) "
            "VALUES ($1, $1), ($1, $2), ($2, $2)",
            PARENT,
            CHILD,
        )
        await conn.execute(
            "INSERT INTO scryfall_tag_memberships (tag_id, oracle_id, details) "
            "VALUES ($1, $2, '{}')",
            CHILD,
            SOL_RING_ORACLE_ID,
        )


@pytest.mark.asyncio
async def test_ac04_card_route_returns_direct_scryfall_tags(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    await _seed_tags(db_pool)
    response = await client.get("/api/v1/cards/3d7b8d2c-36f5-40e7-91de-9c8c1b44da67")
    assert response.status_code == 200
    assert response.json()["data"]["oracle_tags"] == [
        {"id": str(CHILD), "slug": "child", "label": "Child"}
    ]


@pytest.mark.asyncio
async def test_ac05_parent_source_id_finds_child_memberships(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    await _seed_tags(db_pool)
    response = await client.get(f"/api/v1/cards/search?oracle_tag_ids={PARENT}")
    assert response.status_code == 200
    assert [card["name"] for card in response.json()["data"]] == ["Sol Ring"]


@pytest.mark.asyncio
async def test_ac05_invalid_source_id_is_an_actionable_error(client: AsyncClient) -> None:
    response = await client.get("/api/v1/cards/search?oracle_tag_ids=not-a-source-id")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_ORACLE_TAG"
