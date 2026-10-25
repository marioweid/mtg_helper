"""Shared test fixtures."""

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

# Set required env vars before importing any app module that reads config at import time.
os.environ.setdefault("DATABASE_URL", "postgresql://mtg:mtg_dev@localhost:5432/mtg_helper")
os.environ.setdefault("OPENAI_API_KEY", "test")
# Never send test traffic to a developer's configured Assay instance.
os.environ.update(ASSAY_ENDPOINT="", ASSAY_API_KEY="", ASSAY_APPLICATION="")

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from mtg_helper.main import app

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://mtg:mtg_dev@localhost:5432/mtg_helper_test"
)


SCHEMA_PATH = Path(__file__).parent.parent / "src/mtg_helper/sql/schema.sql"

# Known test cards (scryfall_id, name, color_identity, legality)
_TEST_CARDS = [
    {
        "scryfall_id": "1d7b8d2c-36f5-40e7-91de-9c8c1b44da67",
        "oracle_id": "1d7b8d2c-aaaa-40e7-91de-9c8c1b44da67",
        "name": "Doubling Season",
        "color_identity": ["G"],
        "oracle_text": "If an effect would put one or more tokens into play under your control, "
        "it puts twice that many of those tokens into play instead.",
        "type_line": "Enchantment",
        "cmc": 5,
        "mana_cost": "{4}{G}",
        "rarity": "rare",
        "set_code": "rav",
        "legalities": {"commander": "legal"},
        "prices": {"eur": "45.00"},
    },
    {
        "scryfall_id": "2d7b8d2c-36f5-40e7-91de-9c8c1b44da67",
        "oracle_id": "2d7b8d2c-aaaa-40e7-91de-9c8c1b44da67",
        "name": "Rhystic Study",
        "color_identity": ["U"],
        "oracle_text": "Whenever an opponent casts a spell, you may draw a card "
        "unless that player pays {1}.",
        "type_line": "Enchantment",
        "cmc": 3,
        "mana_cost": "{2}{U}",
        "rarity": "common",
        "set_code": "pcy",
        "legalities": {"commander": "legal"},
        "prices": {"eur": "12.00"},
    },
    {
        "scryfall_id": "3d7b8d2c-36f5-40e7-91de-9c8c1b44da67",
        "oracle_id": "3d7b8d2c-aaaa-40e7-91de-9c8c1b44da67",
        "name": "Sol Ring",
        "color_identity": [],
        "oracle_text": "{T}: Add {C}{C}.",
        "type_line": "Artifact",
        "cmc": 1,
        "mana_cost": "{1}",
        "rarity": "uncommon",
        "set_code": "lea",
        "legalities": {"commander": "legal"},
        "prices": {"eur": "0.20"},
    },
    {
        "scryfall_id": "4d7b8d2c-36f5-40e7-91de-9c8c1b44da67",
        "oracle_id": "4d7b8d2c-aaaa-40e7-91de-9c8c1b44da67",
        "name": "Hazel of the Rootbloom",
        "color_identity": ["G", "W"],
        "oracle_text": "Legendary Creature — Elf Druid. Whenever you cast a spell with X "
        "in its mana cost, create X 1/1 token copies.",
        "type_line": "Legendary Creature — Elf Druid",
        "cmc": 4,
        "mana_cost": "{2}{G}{W}",
        "rarity": "rare",
        "set_code": "woe",
        "legalities": {"commander": "legal"},
        "power": "2",
        "toughness": "4",
        "prices": {"eur": "0.15"},
    },
    {
        "scryfall_id": "5d7b8d2c-36f5-40e7-91de-9c8c1b44da67",
        "oracle_id": "5d7b8d2c-aaaa-40e7-91de-9c8c1b44da67",
        "name": "Dockside Extortionist",
        "color_identity": ["R"],
        "oracle_text": "When Dockside Extortionist enters the battlefield, "
        "create X Treasure tokens.",
        "type_line": "Creature — Goblin Pirate",
        "cmc": 2,
        "mana_cost": "{1}{R}",
        "rarity": "rare",
        "set_code": "c19",
        "legalities": {"commander": "legal"},
        "power": "1",
        "toughness": "2",
        # Null EUR: card has no EUR price data.
        "prices": {"usd": "60.00"},
    },
    {
        "scryfall_id": "6d7b8d2c-36f5-40e7-91de-9c8c1b44da67",
        "oracle_id": "6d7b8d2c-aaaa-40e7-91de-9c8c1b44da67",
        "name": "Forest",
        "color_identity": ["G"],
        "oracle_text": "{T}: Add {G}.",
        "type_line": "Basic Land — Forest",
        "cmc": 0,
        "mana_cost": None,
        "rarity": "common",
        "set_code": "lea",
        "legalities": {"commander": "legal"},
        "prices": {"eur": "0.10"},
    },
    {
        "scryfall_id": "7d7b8d2c-36f5-40e7-91de-9c8c1b44da67",
        "oracle_id": "7d7b8d2c-aaaa-40e7-91de-9c8c1b44da67",
        "name": "Plains",
        "color_identity": ["W"],
        "oracle_text": "{T}: Add {W}.",
        "type_line": "Basic Land — Plains",
        "cmc": 0,
        "mana_cost": None,
        "rarity": "common",
        "set_code": "lea",
        "legalities": {"commander": "legal"},
        "prices": {"eur": "0.10"},
    },
]


def _validate_test_database() -> None:
    """Reject remote, ambiguous, or application targets before destructive test IO."""
    error = (
        "Unsafe TEST_DATABASE_URL: use a separate local database ending in _test, "
        "with host localhost, 127.0.0.1, ::1, or postgres and no query parameters."
    )
    try:
        target = urlsplit(TEST_DB_URL)
        application = urlsplit(os.environ["DATABASE_URL"])
        target_port = target.port or 5432
        application_port = application.port or 5432
    except ValueError:
        raise ValueError(error) from None
    local_hosts = {"localhost", "127.0.0.1", "::1", "postgres"}
    valid = (
        target.scheme in {"postgres", "postgresql"}
        and target.hostname in local_hosts
        and unquote(target.path).endswith("_test")
        and not target.query
        and not target.fragment
    )
    if not valid:
        raise ValueError(error)
    application_is_local = application.hostname in local_hosts
    same_database = unquote(target.path) == unquote(application.path)
    if application_is_local and same_database and target_port == application_port:
        raise ValueError(error)


async def _setup_schema() -> None:
    """Drop, recreate, and seed the test database schema."""
    _validate_test_database()
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    try:
        await conn.execute(
            "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO mtg;"
        )
        await conn.execute(SCHEMA_PATH.read_text())
        for card in _TEST_CARDS:
            await conn.execute(
                """
                INSERT INTO cards (scryfall_id, oracle_id, name, color_identity, oracle_text,
                    type_line, cmc, mana_cost, rarity, set_code, legalities,
                    power, toughness, colors, keywords, prices, is_canonical)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                        $15, $16, true)
                ON CONFLICT (scryfall_id) DO NOTHING
                """,
                card["scryfall_id"],
                card["oracle_id"],
                card["name"],
                card["color_identity"],
                card["oracle_text"],
                card["type_line"],
                card.get("cmc"),
                card.get("mana_cost"),
                card.get("rarity"),
                card.get("set_code"),
                json.dumps(card["legalities"]),
                card.get("power"),
                card.get("toughness"),
                card["color_identity"],
                [],
                json.dumps(card.get("prices") or {}),
            )
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _init_db(request: pytest.FixtureRequest) -> None:
    """Initialize the test database schema once per session (synchronous entry point)."""
    if all(item.get_closest_marker("no_db") is not None for item in request.session.items):
        return
    asyncio.run(_setup_schema())


@pytest_asyncio.fixture(autouse=True)
async def _reset_db(request: pytest.FixtureRequest, _init_db: None) -> None:
    """Reset mutable database state before every test."""
    if request.node.get_closest_marker("no_db") is not None:
        return
    _validate_test_database()
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    try:
        await conn.execute(
            """
            TRUNCATE new_card_shared_assessments, new_card_claims, new_card_constellations,
                new_card_catalog, new_card_catalog_state, new_card_assessment_history,
                scryfall_tag_state, scryfall_tag_memberships,
                scryfall_tag_descendants, scryfall_tags,
                feature_flags, moxfield_commander_recs, moxfield_hub_card_stats,
                moxfield_hubs,
                collection_cards, collections, account_ranking_weights,
                deck_snapshot_cards, deck_snapshots, deck_coach_memory,
                deck_feedback, preferences, deck_cards, decks, accounts,
                theme_group_suggestions, theme_group_members, theme_groups,
                archidekt_tag_card_stats, archidekt_tags CASCADE
            """
        )
        await conn.execute(
            "UPDATE new_card_runs SET manual_active = false, "
            "automatic_active = false, cancelled = false, last_catalog_generation = NULL, "
            "last_error = NULL, "
            "active_token = NULL, active_lease_until = NULL, updated_at = now() WHERE singleton"
        )
        await conn.execute(
            """
            DELETE FROM cards
            WHERE scryfall_id <> ALL($1::uuid[])
            """,
            [str(card["scryfall_id"]) for card in _TEST_CARDS],
        )
        await conn.execute("UPDATE cards SET tags = ARRAY[]::text[], hub_tags = ARRAY[]::text[]")
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    """Clear the in-memory rate-limit buckets before each test."""
    from mtg_helper.services import rate_limit_service

    rate_limit_service.reset()


@pytest_asyncio.fixture
async def db_pool(_init_db: None) -> AsyncGenerator[asyncpg.Pool]:
    """Create a fresh asyncpg pool for each test (avoids cross-loop issues)."""
    _validate_test_database()
    pool = await asyncpg.create_pool(dsn=TEST_DB_URL)
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def client(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[AsyncClient]:
    """HTTP test client with the real FastAPI app and test DB pool.

    Installs a default `get_current_account` override returning a freshly
    inserted account so endpoints gated by the auth dep work without bearer
    tokens. Tests that need a different account use `create_test_account` or
    `set_current_account` to swap the override.
    """
    from mtg_helper.auth import (
        get_current_account,
        get_current_admin,
        require_admin_or_internal,
    )
    from mtg_helper.models.accounts import AccountResponse
    from mtg_helper.services import deck_service
    from mtg_helper.services.admin_jobs import JobRegistry

    async def _skip_recommendation_refresh(*_args: object) -> None:
        return None

    monkeypatch.setattr(deck_service, "_safe_moxfield_refresh", _skip_recommendation_refresh)

    app.state.db_pool = db_pool
    app.state.admin_jobs = JobRegistry()
    app.state.optimizer_jobs = {}
    app.state.coach_jobs = {}

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO accounts (display_name, email)
            VALUES ($1, $2)
            ON CONFLICT (lower(email)) WHERE email IS NOT NULL
            DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING *
            """,
            "Default Test User",
            "default@test.local",
        )
    default_account = AccountResponse(
        id=row["id"],
        display_name=row["display_name"],
        email=row["email"],
        created_at=row["created_at"],
    )

    app.dependency_overrides[get_current_account] = lambda: default_account
    app.dependency_overrides[get_current_admin] = lambda: default_account
    app.dependency_overrides[require_admin_or_internal] = lambda: None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


def set_current_account(account: object) -> None:
    """Override the auth dependency to return `account` (an AccountResponse).

    Use inside tests that need to switch identities (e.g. rate-limit tests
    that exercise per-account buckets).
    """
    from mtg_helper.auth import (
        get_current_account,
        get_current_admin,
        require_admin_or_internal,
    )

    app.dependency_overrides[get_current_account] = lambda: account
    app.dependency_overrides[get_current_admin] = lambda: account
    app.dependency_overrides[require_admin_or_internal] = lambda: None


# Convenience UUIDs for tests
HAZEL_SCRYFALL_ID = UUID("4d7b8d2c-36f5-40e7-91de-9c8c1b44da67")
SOL_RING_SCRYFALL_ID = UUID("3d7b8d2c-36f5-40e7-91de-9c8c1b44da67")
DOUBLING_SEASON_SCRYFALL_ID = UUID("1d7b8d2c-36f5-40e7-91de-9c8c1b44da67")
RHYSTIC_STUDY_SCRYFALL_ID = UUID("2d7b8d2c-36f5-40e7-91de-9c8c1b44da67")
DOCKSIDE_SCRYFALL_ID = UUID("5d7b8d2c-36f5-40e7-91de-9c8c1b44da67")

HAZEL_ORACLE_ID = UUID("4d7b8d2c-aaaa-40e7-91de-9c8c1b44da67")
SOL_RING_ORACLE_ID = UUID("3d7b8d2c-aaaa-40e7-91de-9c8c1b44da67")
DOUBLING_SEASON_ORACLE_ID = UUID("1d7b8d2c-aaaa-40e7-91de-9c8c1b44da67")
RHYSTIC_STUDY_ORACLE_ID = UUID("2d7b8d2c-aaaa-40e7-91de-9c8c1b44da67")
DOCKSIDE_ORACLE_ID = UUID("5d7b8d2c-aaaa-40e7-91de-9c8c1b44da67")


async def create_test_account(client: AsyncClient, display_name: str = "Test User") -> str:
    """Insert an account directly and switch the auth override to it.

    Subsequent requests in the same test see this account from
    `get_current_account`. Returns the new account's UUID as a string.
    """
    from mtg_helper.models.accounts import AccountResponse

    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO accounts (display_name, email) VALUES ($1, $2) RETURNING *",
            display_name,
            f"{display_name.lower().replace(' ', '.')}@test.local",
        )
    account = AccountResponse(
        id=row["id"],
        display_name=row["display_name"],
        email=row["email"],
        created_at=row["created_at"],
    )
    set_current_account(account)
    return str(account.id)


async def create_test_deck(
    client: AsyncClient,
    *,
    name: str = "Test Deck",
    owner_id: str | None = None,  # noqa: ARG001 — kept for backwards-compat with callers
) -> str:
    """Helper: create a deck owned by the current authenticated account.

    The ``owner_id`` argument is kept for caller compatibility but ignored;
    server now derives ownership from the auth dependency. Tests that need a
    specific owner should call ``create_test_account`` first to switch the
    auth override.
    """
    payload: dict = {
        "commander_scryfall_id": str(HAZEL_SCRYFALL_ID),
        "name": name,
    }
    resp = await client.post("/api/v1/decks", json=payload)
    assert resp.status_code == 201
    return resp.json()["data"]["id"]
