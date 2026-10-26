"""Real database checks for the Scryfall-only retrieval membership boundary."""

from uuid import UUID

import asyncpg

from mtg_helper.services.retrieval_service import _fetch_excluded_source_card_ids, _search_tags


async def test_tag_search_uses_direct_memberships_and_keeps_color_and_collection_filters(
    db_pool: asyncpg.Pool,
) -> None:
    tag = UUID("99999999-0000-4000-8000-000000000001")
    async with db_pool.acquire() as conn:
        member = await conn.fetchval("SELECT id FROM cards WHERE name = 'Doubling Season'")
        nonmember = await conn.fetchval("SELECT id FROM cards WHERE name = 'Rhystic Study'")
        await conn.execute(
            "INSERT INTO scryfall_tags (id, slug, metadata) VALUES ($1, 'test-source', '{}')", tag
        )
        await conn.execute(
            "INSERT INTO scryfall_tag_memberships (tag_id, oracle_id, details) "
            "SELECT $1, oracle_id, '{}' FROM cards WHERE id = $2",
            tag,
            member,
        )
    assert await _search_tags(db_pool, [str(tag)], ["G", "U"], []) == [(member, 1)]
    assert await _search_tags(db_pool, [str(tag)], ["U"], []) == []
    assert await _search_tags(db_pool, [str(tag)], ["G", "U"], [member]) == []
    assert (
        await _search_tags(
            db_pool, [str(tag)], ["G", "U"], [], owned_card_ids=frozenset({nonmember})
        )
        == []
    )
    assert await _fetch_excluded_source_card_ids(
        db_pool, frozenset({str(tag)}), ["G"]
    ) == frozenset({member})
