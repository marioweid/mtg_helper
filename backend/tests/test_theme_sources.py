"""Unit coverage for source-neutral theme helpers and Archidekt parsing."""

import asyncpg
import httpx
import pytest

from mtg_helper.services.archidekt_tag_service import _sample_deck_ids, fetch_tags
from mtg_helper.services.theme_service import assign_member, normalize_slug, score_themes


def test_normalize_slug_handles_counter_names() -> None:
    assert normalize_slug("+1/+1 Counters") == "plus_1_plus_1_counters"
    assert normalize_slug("-1/-1 Counters") == "minus_1_minus_1_counters"


@pytest.mark.asyncio
async def test_fetch_tags_parses_unique_public_links() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tags"
        return httpx.Response(
            200,
            text=(
                '<a href="/tags/plus-counters">+1/+1 Counters</a>'
                '<a href="/tags/plus-counters">+1/+1 Counters</a>'
                '<a href="/tags/blink">Blink</a>'
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tags = await fetch_tags(client=client)

    assert [(tag.slug, tag.tag, tag.name) for tag in tags] == [
        ("plus-counters", "plus_counters", "+1/+1 Counters"),
        ("blink", "blink", "Blink"),
    ]


@pytest.mark.asyncio
async def test_sample_deck_ids_deduplicates_and_caps() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<a href="/decks/10/first">One</a>'
                '<a href="/decks/10/first">Duplicate</a>'
                '<a href="/decks/11/second">Two</a>'
                '<a href="/decks/12/third">Three</a>'
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ids = await _sample_deck_ids(client, "/tags/blink", 2)

    assert ids == ["10", "11"]


@pytest.mark.asyncio
async def test_fetch_tags_rejects_empty_catalog() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, text="<html></html>"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="empty tag catalog"):
            await fetch_tags(client=client)


@pytest.mark.asyncio
async def test_assign_member_moves_source_tag_between_groups(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO moxfield_hubs (id, slug, tag, name)
               VALUES (990001, 'test-theme', 'test_theme', 'Test Theme')"""
        )
        first = await conn.fetchval(
            "INSERT INTO theme_groups (slug, label) VALUES ('first-test', 'First') RETURNING id"
        )
        second = await conn.fetchval(
            "INSERT INTO theme_groups (slug, label) VALUES ('second-test', 'Second') RETURNING id"
        )

    await assign_member(db_pool, first, "moxfield", 990001)
    await assign_member(db_pool, second, "moxfield", 990001)

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT group_id FROM theme_group_members WHERE moxfield_hub_id = 990001"
        )
    assert [row["group_id"] for row in rows] == [second]


@pytest.mark.asyncio
async def test_score_themes_uses_strongest_source(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        card_id = await conn.fetchval("SELECT id FROM cards WHERE name = 'Sol Ring'")
        await conn.execute(
            """INSERT INTO moxfield_hubs (id, slug, tag, name)
               VALUES (990002, 'shared-mox', 'shared_mox', 'Shared Mox')"""
        )
        arch_id = await conn.fetchval(
            """INSERT INTO archidekt_tags (slug, tag, name)
               VALUES ('shared-arch', 'shared_arch', 'Shared Arch') RETURNING id"""
        )
        group_id = await conn.fetchval(
            """INSERT INTO theme_groups (slug, label)
               VALUES ('shared-test', 'Shared Test') RETURNING id"""
        )
        await conn.execute(
            """INSERT INTO theme_group_members (group_id, source, moxfield_hub_id)
               VALUES ($1, 'moxfield', 990002)""",
            group_id,
        )
        await conn.execute(
            """INSERT INTO theme_group_members (group_id, source, archidekt_tag_id)
               VALUES ($1, 'archidekt', $2)""",
            group_id,
            arch_id,
        )
        await conn.execute(
            """INSERT INTO moxfield_hub_card_stats VALUES
               (990002, $1, 5, 1, .5, .1, .4, 10, 10, now())""",
            card_id,
        )
        await conn.execute(
            """INSERT INTO archidekt_tag_card_stats VALUES
               ($1, $2, 7, 1, .7, .1, .6, 10, 10, now())""",
            arch_id,
            card_id,
        )

    scores = await score_themes(db_pool, ["shared-test"], [])
    assert scores[card_id] == pytest.approx(0.6)
