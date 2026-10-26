"""Application-route checks for the Scryfall-only label cutover."""

import json
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from httpx import AsyncClient

from tests.conftest import HAZEL_SCRYFALL_ID, SOL_RING_ORACLE_ID, SOL_RING_SCRYFALL_ID


def _migration_module() -> object:
    """Load the standalone migration CLI without executing its entry point."""
    path = Path(__file__).parents[1] / "scripts" / "migrate_scryfall_labels.py"
    spec = spec_from_file_location("migrate_scryfall_labels", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Scryfall cutover migration")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
async def test_ac04_deck_route_exposes_oracle_tags_not_legacy_tag_arrays(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Deck detail projects source identities without exposing retired tag arrays."""
    await _seed_tags(db_pool)
    created = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Source deck"},
    )
    deck_id = created.json()["data"]["id"]
    added = await client.post(
        f"/api/v1/decks/{deck_id}/cards", json={"card_scryfall_id": str(SOL_RING_SCRYFALL_ID)}
    )
    assert added.status_code == 201

    response = await client.get(f"/api/v1/decks/{deck_id}")
    assert response.status_code == 200
    card = response.json()["data"]["cards"][0]
    assert card["oracle_tags"] == [{"id": str(CHILD), "slug": "child", "label": "Child"}]
    assert not {"tags", "hub_tags", "mtgjson_tags"} & card.keys()


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


@pytest.mark.asyncio
async def test_ac06_deck_selection_rejects_unknown_source_id(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Deck selection persists only current concrete source identities."""
    await _seed_tags(db_pool)
    response = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
            "name": "Invalid source selection",
            "archetype_tags": ["10000000-0000-0000-0000-000000000099"],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_SOURCE_SELECTION"


@pytest.mark.asyncio
async def test_ac08_apply_removes_retired_storage_and_is_idempotent(
    db_pool: asyncpg.Pool,
) -> None:
    """A populated rehearsal keeps source selections while dropping retired storage."""
    migration = _migration_module()
    source_hash = sha256(b"scryfall-label-cutover-cards").hexdigest()
    tag_hash = sha256(b"scryfall-label-cutover-tags").hexdigest()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO recommendation_sources (sha256, kind, payload) VALUES "
            "($1, 'cards', '\\x00'), ($2, 'oracle_tags', '\\x00')",
            source_hash,
            tag_hash,
        )
        await conn.execute(
            "INSERT INTO new_card_catalog_state "
            "(singleton, generation, started_at, published_at, card_count, source_sha256) "
            "VALUES (true, gen_random_uuid(), now(), now(), 1, $1)",
            source_hash,
        )
        await conn.execute(
            "INSERT INTO scryfall_tag_state "
            "(singleton, source_sha256, tag_sha256, archive_sha256, manifest, started_at, "
            "published_at, tag_count, membership_count) "
            "VALUES (true, $1, $2, $3, '{}', now(), now(), 1000, 1000)",
            source_hash,
            tag_hash,
            source_hash,
        )
        await _seed_tags(db_pool)
        await conn.execute(
            "ALTER TABLE cards ADD COLUMN tags text[] NOT NULL DEFAULT '{}'; "
            "ALTER TABLE cards ADD COLUMN hub_tags text[] NOT NULL DEFAULT '{}'; "
            "ALTER TABLE cards ADD COLUMN mtgjson_tags text[] NOT NULL DEFAULT '{}'; "
            "ALTER TABLE cards ADD COLUMN traits text[] NOT NULL DEFAULT '{}'; "
            "ALTER TABLE cards ADD COLUMN token_types text[] NOT NULL DEFAULT '{}'; "
            "CREATE TABLE mtgjson_keywords (keyword text PRIMARY KEY)"
        )
        deck_id = await conn.fetchval(
            "INSERT INTO decks (name, commander_id, archetype_tags) "
            "SELECT 'Cutover', id, ARRAY['child'] FROM cards WHERE scryfall_id = $1 RETURNING id",
            HAZEL_SCRYFALL_ID,
        )
        aliases, identities = await migration._load_source(conn)
        updates, unresolved = await migration._plan(conn, aliases, identities)
        assert not unresolved
        await migration._apply(conn, updates)
        assert await conn.fetchval("SELECT archetype_tags FROM decks WHERE id = $1", deck_id) == [
            str(CHILD)
        ]
        assert not await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'cards' AND column_name = 'mtgjson_tags')"
        )
        assert not await conn.fetchval("SELECT to_regclass('public.mtgjson_keywords') IS NOT NULL")
        await migration._apply(conn, {})


@pytest.mark.no_db
def test_ac06_rejects_non_uuid_oracle_tag_model_choices() -> None:
    """Model selections must be concrete Scryfall source identities."""
    from mtg_helper.services.keyword_catalog_service import _source_ids

    with pytest.raises(ValueError, match="source UUIDs"):
        _source_ids(["invented-theme"])


@pytest.mark.no_db
def test_ac07_has_no_retired_manual_membership_routes() -> None:
    """Manual Moxfield and Archidekt membership writers are no longer reachable."""
    from mtg_helper.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/admin/sync-moxfield-hub" not in paths
    assert "/api/v1/admin/sync-archidekt-tag" not in paths


@pytest.mark.no_db
def test_ac08_existing_source_uuid_is_preserved_by_the_migration_plan() -> None:
    """A rerun recognizes a saved source identity instead of treating it as unresolved."""
    migration = _migration_module()
    identity = UUID("10000000-0000-0000-0000-000000000002")
    assert migration._source_identity(str(identity), {}, {identity}) == identity


@pytest.mark.no_db
def test_ac09_requires_an_isolated_target_and_private_new_report(tmp_path: Path) -> None:
    """Apply guards reject application, remote, repository, and overwritten report paths."""
    migration = _migration_module()
    assert not migration._is_safe_target("postgresql://mtg:mtg@remote.invalid/production")
    assert migration._is_safe_target("postgresql://mtg:mtg@localhost/rehearsal_test")
    report = tmp_path / "unresolved.json"
    assert migration._private_report_path(report) == report.resolve()
    report.write_text("existing", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        migration._private_report_path(report)


@pytest.mark.no_db
def test_ac09_rejects_loopback_alias_for_application_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loopback aliases identify the same application target, not a safe rehearsal."""
    migration = _migration_module()
    monkeypatch.setenv("DATABASE_URL", "postgresql://mtg@localhost:55451/scryfall_build3_test")
    assert not migration._is_safe_target("postgresql://mtg@127.0.0.1:55451/scryfall_build3_test")


@pytest.mark.no_db
def test_ac11_retired_label_writer_modules_are_not_importable() -> None:
    """Only migration history may name retired global-label writers."""
    from importlib.util import find_spec

    for name in (
        "mtg_helper.services.mtgjson",
        "mtg_helper.services.tag_service",
        "mtg_helper.services.moxfield_hub_service",
        "mtg_helper.services.archidekt_tag_service",
    ):
        assert find_spec(name) is None
