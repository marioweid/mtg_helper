"""Inactive personalization records survive schema maintenance and new reads."""

from typing import Any, cast
from uuid import UUID

import asyncpg

from mtg_helper.services.new_cards import repository
from mtg_helper.services.new_cards.service import NewCardsService
from tests.conftest import SCHEMA_PATH, create_test_deck

_LEGACY_TABLES = (
    "preferences",
    "account_ranking_weights",
    "deck_feedback",
    "deck_coach_memory",
)


class GuardedConnection:
    """Reject application access to inactive personalization tables."""

    def __init__(self, connection: asyncpg.Connection) -> None:
        self.connection = connection

    def transaction(self, **kwargs: object) -> Any:
        return self.connection.transaction(**kwargs)

    async def fetch(self, query: str, *args: object) -> list[asyncpg.Record]:
        self._check(query)
        return await self.connection.fetch(query, *args)

    async def fetchrow(self, query: str, *args: object) -> asyncpg.Record | None:
        self._check(query)
        return await self.connection.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: object) -> Any:
        self._check(query)
        return await self.connection.fetchval(query, *args)

    def _check(self, query: str) -> None:
        lowered = query.lower()
        assert not any(table in lowered for table in _LEGACY_TABLES)


class GuardedAcquire:
    """Adapt a real pool acquire context to guarded application queries."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.acquire = pool.acquire()

    async def __aenter__(self) -> GuardedConnection:
        return GuardedConnection(await self.acquire.__aenter__())

    async def __aexit__(self, *args: object) -> bool | None:
        return await self.acquire.__aexit__(*args)


class GuardedPool:
    """Provide the pool surface New Cards uses while observing its SQL."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    def acquire(self) -> GuardedAcquire:
        return GuardedAcquire(self.pool)


async def test_schema_reapply_retains_legacy_and_unrelated_rows(
    client, db_pool: asyncpg.Pool
) -> None:
    """Applying schema twice preserves snapshots and new reads ignore legacy tables."""
    deck_id = UUID(await create_test_deck(client))
    async with db_pool.acquire() as conn:
        account = await conn.fetchrow(
            "SELECT id FROM accounts WHERE email = $1", "default@test.local"
        )
        card_id = await conn.fetchval("SELECT id FROM cards WHERE name = $1", "Sol Ring")
        assert account is not None
        account_id = account["id"]
        await conn.execute(
            "INSERT INTO preferences (account_id, preference_type, description) "
            "VALUES ($1, $2, $3)",
            account_id,
            "general",
            "Historical preference",
        )
        await conn.execute(
            "INSERT INTO account_ranking_weights (account_id, semantic, personal) "
            "VALUES ($1, $2, $3)",
            account_id,
            0.91,
            0.07,
        )
        await conn.execute(
            "INSERT INTO deck_feedback (deck_id, card_id, feedback, reason) "
            "VALUES ($1, $2, $3, $4)",
            deck_id,
            card_id,
            "reject",
            "Historical feedback",
        )
        await conn.execute(
            "INSERT INTO deck_coach_memory (deck_id, account_id, notes) VALUES ($1, $2, $3)",
            deck_id,
            account_id,
            "Historical assistant note",
        )
        await conn.execute(
            "INSERT INTO collections (account_id, name) VALUES ($1, $2)",
            account_id,
            "Unrelated collection",
        )
        before = await _snapshot(conn, deck_id, account_id)
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        await conn.execute(schema)
        await conn.execute(schema)
        assert await _snapshot(conn, deck_id, account_id) == before

        owner = repository.Owner(account_id, "default@test.local")
        service = NewCardsService(cast(asyncpg.Pool, GuardedPool(db_pool)))
        assert (await service.view(owner, deck_id)).eligible_count == 0
        assert (await service.view(owner, deck_id)).eligible_count == 0


async def _snapshot(
    conn: asyncpg.Connection, deck_id: UUID, account_id: UUID
) -> dict[str, list[dict[str, object]]]:
    """Return a stable, narrow snapshot of records retirement must leave untouched."""
    result: dict[str, list[dict[str, object]]] = {}
    queries = {
        "preferences": ("SELECT * FROM preferences WHERE account_id = $1", account_id),
        "account_ranking_weights": (
            "SELECT * FROM account_ranking_weights WHERE account_id = $1",
            account_id,
        ),
        "deck_feedback": ("SELECT * FROM deck_feedback WHERE deck_id = $1", deck_id),
        "deck_coach_memory": ("SELECT * FROM deck_coach_memory WHERE deck_id = $1", deck_id),
        "collections": ("SELECT * FROM collections WHERE account_id = $1", account_id),
        "decks": ("SELECT * FROM decks WHERE id = $1", deck_id),
        "accounts": ("SELECT * FROM accounts WHERE id = $1", account_id),
    }
    for table, (query, value) in queries.items():
        result[table] = [dict(row) for row in await conn.fetch(query, value)]
    return result
