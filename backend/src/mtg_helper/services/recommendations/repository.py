"""Owner-scoped read/action helpers; source advice never grants deck access."""

import json
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from mtg_helper.services.recommendations.source import Card


class DiscoveryError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Owner:
    account_id: UUID
    email: str


def value(raw: object) -> Card:
    decoded = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(decoded, dict):
        raise ValueError("Expected a stored JSON object")
    return decoded


async def owned_deck(
    conn: asyncpg.Connection,
    owner: Owner,
    deck_id: UUID,
    *,
    lock: bool = False,
) -> asyncpg.Record:
    sql = "SELECT d.*, c.oracle_id AS commander_oracle_id FROM decks d "
    sql += "JOIN cards c ON c.id = d.commander_id WHERE d.id = $1 AND lower(d.owner_email) = $2"
    if lock:
        sql += " FOR UPDATE OF d"
    row = await conn.fetchrow(sql, deck_id, owner.email.strip().lower())
    if row is None:
        raise DiscoveryError("Deck not found", 404)
    return row


async def exclusions(conn: asyncpg.Connection, owner: Owner, deck_id: UUID) -> set[str]:
    rows = await conn.fetch(
        "SELECT c.oracle_id FROM cards c JOIN deck_cards d ON d.card_id = c.id "
        "WHERE d.deck_id = $1 UNION SELECT c.oracle_id FROM cards c "
        "JOIN deck_card_plans p ON p.card_id = c.id "
        "WHERE p.deck_id = $1 AND p.direction = 'addition' "
        "UNION SELECT c.oracle_id FROM cards c JOIN preferences p ON p.card_id = c.id "
        "WHERE p.account_id = $2 AND p.preference_type = 'avoid_card'",
        deck_id,
        owner.account_id,
    )
    return {str(row["oracle_id"]) for row in rows if row["oracle_id"]}


async def owned_run(
    conn: asyncpg.Connection,
    owner: Owner,
    deck_id: UUID,
    run_id: UUID,
) -> asyncpg.Record:
    await owned_deck(conn, owner, deck_id)
    row = await conn.fetchrow(
        "SELECT * FROM recommendation_runs WHERE id = $1 AND account_id = $2 AND deck_id = $3",
        run_id,
        owner.account_id,
        deck_id,
    )
    if row is None:
        raise DiscoveryError("Discover run not found", 404)
    return row
