"""Real source/target database checks for the narrow local export."""

from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg
import pytest

from scripts.copy_new_cards_local import copy_local, validate_target
from tests.conftest import TEST_DB_URL, create_test_deck

SOURCE_HASH = "a" * 64


def _database_url(database: str) -> str:
    parts = urlsplit(TEST_DB_URL)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", "", ""))


async def _new_target() -> tuple[str, str]:
    database = f"new_cards_export_{uuid4().hex}_test"
    admin = await asyncpg.connect(_database_url("postgres"))
    try:
        await admin.execute(f'CREATE DATABASE "{database}"')
    finally:
        await admin.close()
    return database, _database_url(database)


async def _drop_target(database: str) -> None:
    admin = await asyncpg.connect(_database_url("postgres"))
    try:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database}"')
    finally:
        await admin.close()


async def _seed_matching_generations(pool) -> None:
    now = datetime.now(UTC)
    generation = uuid4()
    await pool.execute(
        "INSERT INTO recommendation_sources (sha256, kind, payload) VALUES ($1, 'cards', $2) "
        "ON CONFLICT DO NOTHING",
        SOURCE_HASH,
        b"source",
    )
    await pool.execute(
        "INSERT INTO new_card_catalog_state "
        "(generation, started_at, published_at, card_count, source_sha256) "
        "VALUES ($1, $2, $2, 0, $3)",
        generation,
        now,
        SOURCE_HASH,
    )
    await pool.execute(
        "INSERT INTO scryfall_tag_state "
        "(source_sha256, tag_sha256, archive_sha256, manifest, started_at, published_at, "
        "tag_count, membership_count) VALUES ($1, $1, $1, '{}'::jsonb, $2, $2, 1000, 1000)",
        SOURCE_HASH,
        now,
    )


@pytest.mark.no_db
def test_rejects_encoded_or_routed_copy_targets() -> None:
    with pytest.raises(ValueError, match="must not identify"):
        validate_target(
            "postgresql://user:secret@local%68ost:5432/source",
            "postgresql://user:secret@127.0.0.1:5432/source",
        )
    with pytest.raises(ValueError, match="query"):
        validate_target(
            "postgresql://user:secret@localhost:5432/source",
            "postgresql://user:secret@localhost:5432/local_copy?options=-c%20search_path%3Dpublic",
        )
    with pytest.raises(ValueError, match="must not identify"):
        validate_target(
            "postgresql://user:secret@localhost.:5432/source",
            "postgresql://user:secret@127.0.0.1:5432/source",
        )


@pytest.mark.asyncio
async def test_copy_is_read_only_and_keeps_only_linked_owner_data(client, db_pool) -> None:
    deck_id = UUID(await create_test_deck(client))
    owner = await db_pool.fetchrow(
        "SELECT id, email FROM accounts WHERE email = $1", "default@test.local"
    )
    assert owner is not None
    await _seed_matching_generations(db_pool)
    sol_ring = await db_pool.fetchval("SELECT id FROM cards WHERE name = 'Sol Ring'")
    doubling_season = await db_pool.fetchval("SELECT id FROM cards WHERE name = 'Doubling Season'")
    assert sol_ring is not None and doubling_season is not None
    await db_pool.execute(
        "INSERT INTO deck_cards (deck_id, card_id, quantity, categories) VALUES ($1, $2, 2, $3)",
        deck_id,
        sol_ring,
        ["Mana"],
    )
    collection_id = await db_pool.fetchval(
        "INSERT INTO collections (account_id, name) VALUES ($1, 'Plan source') RETURNING id",
        owner["id"],
    )
    await db_pool.execute(
        "INSERT INTO collection_cards (collection_id, card_id, quantity) VALUES ($1, $2, 3)",
        collection_id,
        doubling_season,
    )
    await db_pool.execute(
        "INSERT INTO deck_card_plans (deck_id, card_id, direction, quantity, collection_id, "
        "categories, new_cards_origin) VALUES ($1, $2, 'addition', 3, $3, $4, true)",
        deck_id,
        doubling_season,
        collection_id,
        ["Ramp"],
    )
    other = await db_pool.fetchrow(
        "INSERT INTO accounts (display_name, email) "
        "VALUES ('Other', 'other@example.test') RETURNING *"
    )
    assert other is not None
    await db_pool.execute(
        "INSERT INTO decks (owner_email, name, commander_id) VALUES ($1, 'Other deck', $2)",
        other["email"],
        sol_ring,
    )
    await db_pool.execute(
        "INSERT INTO collections (account_id, name) VALUES ($1, 'Other collection')",
        other["id"],
    )
    await db_pool.execute(
        "INSERT INTO new_card_assessments (deck_id, account_id, oracle_id, input_hash, assessment) "
        "VALUES ($1, $2, (SELECT oracle_id FROM cards WHERE id = $3), 'history', '{}'::jsonb)",
        deck_id,
        owner["id"],
        sol_ring,
    )
    source_before = await db_pool.fetch(
        "SELECT (SELECT count(*) FROM accounts), (SELECT count(*) FROM decks), "
        "(SELECT count(*) FROM deck_card_plans), (SELECT count(*) FROM new_card_assessments)"
    )
    database, target = await _new_target()
    try:
        counts = await copy_local(TEST_DB_URL, target, owner["email"])
        copied = await asyncpg.connect(target)
        try:
            assert counts["decks"] == 1
            assert await copied.fetchval("SELECT count(*) FROM accounts") == 1
            assert await copied.fetchval("SELECT count(*) FROM decks") == 1
            assert await copied.fetchval("SELECT categories FROM deck_cards") == ["Mana"]
            assert await copied.fetchval("SELECT quantity FROM deck_card_plans") == 3
            assert await copied.fetchval("SELECT categories FROM deck_card_plans") == ["Ramp"]
            assert await copied.fetchval("SELECT count(*) FROM collections") == 0
            assert await copied.fetchval("SELECT count(*) FROM collection_cards") == 0
            assert await copied.fetchval("SELECT collection_id FROM deck_card_plans") is None
            assert await copied.fetchval("SELECT suggestion_collection_ids FROM decks") == []
            assert await copied.fetchval("SELECT count(*) FROM new_card_assessments") == 0
            assert (
                await copied.fetchval("SELECT last_error FROM new_card_runs WHERE singleton")
                is None
            )
        finally:
            await copied.close()
        assert (
            await db_pool.fetch(
                "SELECT (SELECT count(*) FROM accounts), (SELECT count(*) FROM decks), "
                "(SELECT count(*) FROM deck_card_plans), "
                "(SELECT count(*) FROM new_card_assessments)"
            )
            == source_before
        )
    finally:
        await _drop_target(database)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE FUNCTION marker() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
        "CREATE TYPE marker AS ENUM ('reserved')",
    ],
)
async def test_copy_rejects_function_or_type_only_targets(client, db_pool, ddl) -> None:
    await _seed_matching_generations(db_pool)
    database, target = await _new_target()
    conn = await asyncpg.connect(target)
    try:
        await conn.execute(ddl)
        with pytest.raises(ValueError, match="empty"):
            await copy_local(TEST_DB_URL, target, "default@test.local")
        assert await conn.fetchval("SELECT to_regclass('public.accounts')") is None
    finally:
        await conn.close()
        await _drop_target(database)


@pytest.mark.asyncio
@pytest.mark.parametrize("routed", [False, True])
async def test_alias_never_mutates_an_empty_source(routed) -> None:
    database, target = await _new_target()
    parts = urlsplit(target)
    source = urlunsplit(parts._replace(netloc=parts.netloc.replace("127.0.0.1", "localhost.")))
    if routed:
        source = urlunsplit(parts._replace(path="", query=f"database={database}"))
    conn = await asyncpg.connect(target)
    try:
        with pytest.raises(ValueError, match="source database"):
            await copy_local(source, target, "default@test.local")
        assert await conn.fetchval("SELECT to_regclass('public.accounts')") is None
    finally:
        await conn.close()
        await _drop_target(database)


@pytest.mark.asyncio
async def test_copy_refuses_nonempty_targets_and_mismatched_generations(client, db_pool) -> None:
    owner = await db_pool.fetchrow(
        "SELECT id, email FROM accounts WHERE email = $1", "default@test.local"
    )
    assert owner is not None
    await _seed_matching_generations(db_pool)
    database, target = await _new_target()
    try:
        existing = await asyncpg.connect(target)
        try:
            await existing.execute("CREATE TABLE profiles (id integer PRIMARY KEY)")
            await existing.execute("INSERT INTO profiles VALUES (1)")
        finally:
            await existing.close()
        with pytest.raises(ValueError, match="empty"):
            await copy_local(TEST_DB_URL, target, owner["email"])
    finally:
        await _drop_target(database)

    await db_pool.execute(
        "INSERT INTO recommendation_sources (sha256, kind, payload) VALUES ($1, 'cards', $2) "
        "ON CONFLICT DO NOTHING",
        "b" * 64,
        b"mismatch",
    )
    await db_pool.execute("UPDATE scryfall_tag_state SET source_sha256 = $1", "b" * 64)
    database, target = await _new_target()
    try:
        with pytest.raises(ValueError, match="matching generations"):
            await copy_local(TEST_DB_URL, target, owner["email"])
        copied = await asyncpg.connect(target)
        try:
            assert await copied.fetchval("SELECT count(*) FROM accounts") == 0
        finally:
            await copied.close()
    finally:
        await _drop_target(database)
