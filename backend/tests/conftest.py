"""Shared test fixtures."""

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import UUID

# Set required env vars before importing any app module that reads config at import time.
os.environ.setdefault("DATABASE_URL", "postgresql://mtg:mtg_dev@localhost:5432/mtg_helper_test")
os.environ.setdefault("GEMINI_API_KEY", "test")

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from mtg_helper.main import app

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://mtg:mtg_dev@localhost:5432/mtg_helper_test"
)


def make_mock_llm_client() -> "object":
    """Build a mock LLMClient with an async ``embed`` method.

    Returns:
        MagicMock whose ``.embed`` returns one 1536-dim zero vector per input.
    """
    from unittest.mock import AsyncMock, MagicMock

    async def _embed(texts: list[str], **_: object) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]

    ai = MagicMock()
    ai.embed = AsyncMock(side_effect=_embed)
    return ai


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


async def _setup_schema() -> None:
    """Drop, recreate, and seed the test database schema."""
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
                    power, toughness, colors, keywords, prices)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
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
def _init_db() -> None:
    """Initialize the test database schema once per session (synchronous entry point)."""
    asyncio.run(_setup_schema())


@pytest_asyncio.fixture(autouse=True)
async def _reset_db(_init_db: None) -> None:
    """Reset mutable database state before every test."""
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    try:
        await conn.execute(
            """
            TRUNCATE feature_flags, edhrec_commander_recs, moxfield_commander_recs,
                collection_cards, collections, account_ranking_weights,
                deck_snapshot_cards, deck_snapshots, deck_coach_memory,
                deck_feedback, preferences, deck_cards, decks, accounts CASCADE
            """
        )
        await conn.execute(
            """
            DELETE FROM cards
            WHERE scryfall_id <> ALL($1::uuid[])
            """,
            [str(card["scryfall_id"]) for card in _TEST_CARDS],
        )
        await conn.execute("UPDATE cards SET tags = ARRAY[]::text[]")
    finally:
        await conn.close()
    from mtg_helper.services import profile_service

    profile_service._cache.clear()


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    """Clear the in-memory rate-limit buckets before each test."""
    from mtg_helper.services import rate_limit_service

    rate_limit_service.reset()


@pytest_asyncio.fixture
async def db_pool(_init_db: None) -> AsyncGenerator[asyncpg.Pool]:
    """Create a fresh asyncpg pool for each test (avoids cross-loop issues)."""
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
    from unittest.mock import AsyncMock, MagicMock

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

    monkeypatch.setattr(deck_service, "_safe_edhrec_refresh", _skip_recommendation_refresh)
    monkeypatch.setattr(deck_service, "_safe_moxfield_refresh", _skip_recommendation_refresh)

    app.state.db_pool = db_pool

    mock_qdrant = MagicMock()
    mock_qdrant.search = AsyncMock(return_value=[])
    app.state.qdrant_client = mock_qdrant
    app.state.ai_client = make_mock_llm_client()
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
