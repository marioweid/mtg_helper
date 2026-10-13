"""Real PostgreSQL publication/rollback checks; only the external HTTP source is mocked."""

import gzip
from datetime import UTC, datetime, timedelta
from functools import partial
from uuid import UUID

import asyncpg
import httpx
import pytest

from mtg_helper.services import scryfall, scryfall_tag_repository
from mtg_helper.services.new_cards import catalog
from mtg_helper.services.recommendations import source_repository
from mtg_helper.services.scryfall_exports import EXPORT_KINDS, BulkExport
from tests.test_scryfall_exports import json_response, receipt
from tests.test_scryfall_tags import CARD, GRANDCHILD, OTHER, PARENT, archive, hierarchy, tag


def source_cards() -> list[dict]:
    result = []
    for number in range(1000):
        identity = CARD if number == 0 else OTHER if number == 1 else str(UUID(int=20000 + number))
        result.append(
            {
                "object": "card",
                "id": str(UUID(int=30000 + number)),
                "oracle_id": identity,
                "name": f"Source Card {number}",
                "type_line": "Creature — Elf",
                "oracle_text": "Flying",
                "mana_cost": "{G}",
                "cmc": 1.0,
                "color_identity": ["G"],
                "colors": ["G"],
                "keywords": ["Flying"],
                "legalities": {"commander": "legal"},
                "games": ["paper"],
                "layout": "normal",
                "released_at": "2026-01-01",
                "set_type": "expansion",
                "set": "tst",
                "rarity": "common",
                "reprint": False,
            }
        )
    return result


def source_tags(*, extra: int = 1000) -> list[dict]:
    return hierarchy() + [
        tag(
            str(UUID(int=number)),
            taggings=[{"oracle_id": CARD, "weight": "median"}],
        )
        for number in range(100, 100 + extra)
    ]


def prepared_tags(rows: list[dict] | None = None) -> scryfall_tag_repository.TagPublication:
    cards = source_cards()
    source = source_repository.prepare(cards)
    return scryfall_tag_repository.prepare(
        archive(rows if rows is not None else source_tags()),
        source.digest,
        {UUID(card["oracle_id"]) for card in cards},
        card_export=BulkExport.model_validate(receipt("oracle_cards")),
        tag_export=BulkExport.model_validate(receipt("oracle_tags")),
    )


async def publish_generation(
    conn: asyncpg.Connection, prepared: scryfall_tag_repository.TagPublication
) -> None:
    started = datetime.now(UTC)
    assert await catalog.lock_generation(conn, started, 1000)
    await catalog.publish(conn, source_cards(), {}, started)
    await scryfall_tag_repository.publish(conn, prepared, started)


async def test_publication_preserves_metadata_direct_labels_and_transitive_queries(
    db_pool: asyncpg.Pool,
) -> None:
    prepared = prepared_tags()
    async with db_pool.acquire() as conn, conn.transaction():
        await publish_generation(conn, prepared)
    state = await db_pool.fetchrow("SELECT * FROM scryfall_tag_state")
    assert state["tag_sha256"] == prepared.digest
    assert state["source_sha256"] == prepared.cards_hash
    assert state["archive_sha256"] == prepared.archive_hash
    assert state["tag_count"] == 1004
    assert state["membership_count"] == 1002
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM scryfall_tag_memberships WHERE tag_id = $1", UUID(PARENT)
        )
        == 0
    )
    assert (
        await db_pool.fetchval(
            "SELECT details->>'annotation' FROM scryfall_tag_memberships WHERE tag_id = $1",
            UUID(GRANDCHILD),
        )
        == "note"
    )
    rows = await db_pool.fetch(
        "SELECT DISTINCT m.oracle_id FROM scryfall_tag_descendants d "
        "JOIN scryfall_tag_memberships m ON m.tag_id = d.descendant_id "
        "WHERE d.ancestor_id = $1",
        UUID(PARENT),
    )
    assert {row["oracle_id"] for row in rows} == {UUID(CARD)}
    blob = await db_pool.fetchval(
        "SELECT payload FROM recommendation_sources WHERE sha256 = $1", prepared.digest
    )
    restored = scryfall_tag_repository.restore(blob, prepared.digest, prepared.cards_hash)
    assert restored.members(UUID(PARENT)) == {UUID(CARD)}
    assert restored.tags[UUID(PARENT)].aliases == ["original-alias"]


async def test_admin_reports_receipts_and_detects_a_mismatched_generation(
    db_pool: asyncpg.Pool, client: httpx.AsyncClient
) -> None:
    async with db_pool.acquire() as conn, conn.transaction():
        await publish_generation(conn, prepared_tags())
    status = (await client.get("/api/v1/admin/status")).json()["scryfall_sources"]
    assert status["status"] == "current"
    assert status["published_at"]
    assert status["tag_count"] == 1004
    assert status["manifest"]["oracle_tags"]["updated_at"] == "2026-10-12T00:00:00Z"
    await db_pool.execute("UPDATE new_card_catalog_state SET source_sha256 = NULL")
    status = (await client.get("/api/v1/admin/status")).json()["scryfall_sources"]
    assert status["status"] == "mismatched"


async def test_interrupted_publication_retains_last_good_cards_tags_and_snapshot(
    db_pool: asyncpg.Pool,
) -> None:
    original = prepared_tags()
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await publish_generation(conn, original)
        before = await conn.fetchrow("SELECT * FROM scryfall_tag_state")
        changed = source_tags()
        changed[2]["taggings"][0]["annotation"] = "new annotation"
        replacement = prepared_tags(changed)
        with pytest.raises(RuntimeError, match="interrupted"):
            async with conn.transaction():
                await publish_generation(conn, replacement)
                raise RuntimeError("interrupted")
        assert await conn.fetchrow("SELECT * FROM scryfall_tag_state") == before
        assert (
            await conn.fetchval(
                "SELECT details->>'annotation' FROM scryfall_tag_memberships WHERE tag_id = $1",
                UUID(GRANDCHILD),
            )
            == "note"
        )
        assert not await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM recommendation_sources WHERE sha256 = $1)",
            replacement.digest,
        )


async def test_reader_snapshot_keeps_old_memberships_during_a_new_publication(
    db_pool: asyncpg.Pool,
) -> None:
    async with db_pool.acquire() as writer:
        async with writer.transaction():
            await publish_generation(writer, prepared_tags())
    changed = source_tags()
    changed[2]["taggings"][0]["annotation"] = "replacement note"
    replacement = prepared_tags(changed)
    query = "SELECT details->>'annotation' FROM scryfall_tag_memberships WHERE tag_id = $1"
    async with db_pool.acquire() as reader:
        async with reader.transaction(isolation="repeatable_read"):
            assert await reader.fetchval(query, UUID(GRANDCHILD)) == "note"
            async with db_pool.acquire() as writer, writer.transaction():
                await publish_generation(writer, replacement)
            assert await reader.fetchval(query, UUID(GRANDCHILD)) == "note"
            assert (
                await reader.fetchval("SELECT tag_sha256 FROM scryfall_tag_state")
                != replacement.digest
            )
        assert await reader.fetchval(query, UUID(GRANDCHILD)) == "replacement note"
        assert (
            await reader.fetchval("SELECT tag_sha256 FROM scryfall_tag_state") == replacement.digest
        )


@pytest.mark.parametrize("mode", ["tags", "memberships", "initial"])
async def test_suspiciously_partial_publication_keeps_previous_generation(
    db_pool: asyncpg.Pool, mode: str
) -> None:
    async with db_pool.acquire() as conn:
        if mode != "initial":
            original = prepared_tags(source_tags(extra=2000))
            async with conn.transaction():
                await publish_generation(conn, original)
        before = await conn.fetchrow("SELECT * FROM scryfall_tag_state")
        rows = source_tags(extra=1 if mode == "initial" else 1000)
        if mode == "memberships":
            rows = source_tags(extra=2000)
            for row in rows[4:1200]:
                row["taggings"] = []
        with pytest.raises(ValueError, match="shrank unexpectedly"):
            async with conn.transaction():
                await publish_generation(conn, prepared_tags(rows))
        assert await conn.fetchrow("SELECT * FROM scryfall_tag_state") == before


async def test_publication_requires_matching_card_hash_and_sync_start(
    db_pool: asyncpg.Pool,
) -> None:
    prepared = prepared_tags()
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await publish_generation(conn, prepared)
        prepared.cards_hash = "a" * 64
        with pytest.raises(ValueError, match="generation mismatch"):
            async with conn.transaction():
                await scryfall_tag_repository.publish(conn, prepared, datetime.now(UTC))
        prepared.cards_hash = prepared_tags().cards_hash
        with pytest.raises(ValueError, match="generation mismatch"):
            async with conn.transaction():
                await scryfall_tag_repository.publish(conn, prepared, datetime.now(UTC))
        with pytest.raises(ValueError, match="enclosing card transaction"):
            await scryfall_tag_repository.publish(conn, prepared, datetime.now(UTC))


def install_http_source(
    monkeypatch: pytest.MonkeyPatch, *, tag_content: bytes | None = None, failure: str = ""
) -> None:
    cards = archive(source_cards())
    tags = tag_content if tag_content is not None else archive(source_tags())

    def response(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/bulk-data":
            return json_response({"data": [receipt(kind) for kind in EXPORT_KINDS]})
        if "oracle_tags" in request.url.path:
            if failure == "network":
                raise httpx.ConnectError("tag source offline", request=request)
            return httpx.Response(200, stream=httpx.ByteStream(tags))
        return httpx.Response(200, stream=httpx.ByteStream(cards))

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        partial(httpx.AsyncClient, transport=httpx.MockTransport(response)),
    )


async def test_sync_publishes_all_sources_together_and_preserves_personal_data(
    db_pool: asyncpg.Pool, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import create_test_deck

    deck = await create_test_deck(client)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE decks SET description = $1, archetype_tags = $2 WHERE id = $3",
            "My personal plan",
            ["old_personal_intent"],
            UUID(deck),
        )
        await conn.execute(
            "INSERT INTO deck_cards (deck_id, card_id, quantity, categories) "
            "SELECT $1, id, 2, ARRAY['My category'] FROM cards WHERE name = 'Forest'",
            UUID(deck),
        )
        before_deck = await conn.fetchrow("SELECT * FROM decks WHERE id = $1", UUID(deck))
        before_cards = await conn.fetch("SELECT * FROM deck_cards WHERE deck_id = $1", UUID(deck))
    install_http_source(monkeypatch)
    result = await scryfall.run_sync(db_pool)
    assert result["cards_processed"] == 1000
    assert result["oracle_tags_processed"] == 1004
    assert result["oracle_memberships_processed"] == 1002
    assert result["tag_source_sha256"] == prepared_tags().digest
    assert await db_pool.fetchrow("SELECT * FROM decks WHERE id = $1", UUID(deck)) == before_deck
    assert (
        await db_pool.fetch("SELECT * FROM deck_cards WHERE deck_id = $1", UUID(deck))
        == before_cards
    )
    assert await db_pool.fetchval(
        "SELECT keywords FROM cards WHERE oracle_id = $1", UUID(CARD)
    ) == ["Flying"]


@pytest.mark.parametrize("failure", ["network", "malformed", "partial"])
async def test_failed_sync_preserves_complete_last_good_generation(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    async with db_pool.acquire() as conn, conn.transaction():
        await publish_generation(conn, prepared_tags())
    before = await db_pool.fetchrow("SELECT * FROM scryfall_tag_state")
    old_count = await db_pool.fetchval("SELECT count(*) FROM cards")
    content = b"broken gzip" if failure == "malformed" else archive(source_tags(extra=1))
    install_http_source(monkeypatch, tag_content=content, failure=failure)
    with pytest.raises((ValueError, httpx.ConnectError)):
        await scryfall.run_sync(db_pool)
    assert await db_pool.fetchrow("SELECT * FROM scryfall_tag_state") == before
    assert await db_pool.fetchval("SELECT count(*) FROM cards") == old_count
    assert (
        await db_pool.fetchval("SELECT source_sha256 FROM new_card_catalog_state")
        == before["source_sha256"]
    )


async def test_older_sync_cannot_replace_newer_tag_generation(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with db_pool.acquire() as conn, conn.transaction():
        await publish_generation(conn, prepared_tags())
        await conn.execute(
            "UPDATE new_card_catalog_state SET started_at = $1",
            datetime.now(UTC) + timedelta(days=1),
        )
    before = await db_pool.fetchrow("SELECT * FROM scryfall_tag_state")
    install_http_source(monkeypatch)
    result = await scryfall.run_sync(db_pool)
    assert result["superseded"] is True
    assert await db_pool.fetchrow("SELECT * FROM scryfall_tag_state") == before


@pytest.mark.no_db
def test_unknown_membership_identity_does_not_get_dropped() -> None:
    rows = source_tags()
    rows[2]["taggings"][0]["oracle_id"] = str(UUID(int=999999))
    with pytest.raises(ValueError, match="absent Oracle identities"):
        prepared_tags(rows)


@pytest.mark.no_db
def test_replaying_wrong_card_generation_or_corrupted_tags_is_rejected() -> None:
    prepared = prepared_tags()
    with pytest.raises(ValueError, match="snapshot mismatch"):
        scryfall_tag_repository.restore(prepared.blob, prepared.digest, "a" * 64)
    with pytest.raises(ValueError, match="size/hash mismatch"):
        scryfall_tag_repository.restore(gzip.compress(b"{}"), prepared.digest, prepared.cards_hash)
