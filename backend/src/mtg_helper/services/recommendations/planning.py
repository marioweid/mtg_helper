"""Explicit source-backed additions with origin-aware transactional completion guards."""

from uuid import UUID

import asyncpg

from mtg_helper.services.new_cards.completion import validate_addition as validate_legacy_addition
from mtg_helper.services.planned_change_service import InvalidPlanError
from mtg_helper.services.recommendations.repository import (
    DiscoveryError,
    Owner,
    owned_deck,
    value,
)
from mtg_helper.services.recommendations.source import eligibility_error, paper_design


async def validate_addition(
    conn: asyncpg.Connection, deck_id: UUID, card_id: UUID, quantity: int
) -> None:
    """Validate current paper/source eligibility before inventory or physical mutation."""
    await validate_legacy_addition(conn, deck_id, card_id, quantity)
    row = await conn.fetchrow(
        "SELECT n.source_facts FROM cards c JOIN new_card_catalog n ON n.oracle_id = c.oracle_id "
        "JOIN new_card_catalog_state s ON s.generation = n.generation WHERE c.id = $1",
        card_id,
    )
    if row is None or row["source_facts"] is None or not paper_design(value(row["source_facts"])):
        raise InvalidPlanError(
            "Complete eligible paper facts unavailable; sync cards before completion"
        )


class Planner:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def plan(self, owner: Owner, deck_id: UUID, oracle_id: UUID) -> None:
        """Plan one pending copy idempotently, never mutate physical cards or an opposite cut."""
        async with self.pool.acquire() as conn, conn.transaction():
            await self.plan_in_transaction(conn, deck_id, oracle_id, owner=owner)

    async def plan_in_transaction(
        self,
        conn: asyncpg.Connection,
        deck_id: UUID,
        oracle_id: UUID,
        *,
        owner: Owner,
    ) -> None:
        """Keep source/strategy authorization and pending-addition validation in one transaction."""
        if not conn.is_in_transaction():
            raise RuntimeError("Discover planning requires a transaction")
        deck = await owned_deck(conn, owner, deck_id, lock=True)
        await conn.execute("SELECT pg_advisory_xact_lock_shared(71382041)")
        card = await conn.fetchrow(
            "SELECT c.id, n.source_facts FROM cards c "
            "JOIN new_card_catalog n ON n.oracle_id = c.oracle_id "
            "JOIN new_card_catalog_state s ON s.generation = n.generation "
            "WHERE c.oracle_id = $1 AND c.is_canonical",
            oracle_id,
        )
        if card is None or card["source_facts"] is None:
            raise DiscoveryError("Current source card unavailable; sync cards", 409)
        facts = value(card["source_facts"])
        commanders = await conn.fetch(
            "SELECT c.oracle_id, n.source_facts FROM cards c JOIN new_card_catalog n "
            "ON n.oracle_id=c.oracle_id "
            "JOIN new_card_catalog_state s ON s.generation=n.generation "
            "WHERE c.id = ANY($1::uuid[])",
            [deck["commander_id"]] + ([deck["partner_id"]] if deck["partner_id"] else []),
        )
        if len(commanders) != (2 if deck["partner_id"] else 1):
            raise DiscoveryError("Commander source facts are unavailable; sync cards", 409)
        colors = {
            color for row in commanders for color in value(row["source_facts"])["color_identity"]
        }
        error = eligibility_error(facts, colors, str(deck["commander_oracle_id"]))
        if oracle_id in {row["oracle_id"] for row in commanders}:
            error = "commander"
        if error or not paper_design(facts):
            raise DiscoveryError("This source card is not eligible for Discover", 409)
        await self._insert(conn, deck_id, card["id"])

    async def _insert(
        self,
        conn: asyncpg.Connection,
        deck_id: UUID,
        card_id: UUID,
    ) -> None:
        existing = await conn.fetchrow(
            "SELECT direction FROM deck_card_plans WHERE deck_id = $1 AND card_id = $2 FOR UPDATE",
            deck_id,
            card_id,
        )
        if existing:
            if existing["direction"] != "addition":
                raise DiscoveryError(
                    "A planned cut exists; revise it explicitly before adding", 409
                )
            return
        try:
            await validate_addition(conn, deck_id, card_id, 1)
        except InvalidPlanError as exc:
            raise DiscoveryError(str(exc), 409) from exc
        await conn.execute(
            "INSERT INTO deck_card_plans (deck_id, card_id, direction, quantity, "
            "added_by, ai_reasoning, recommendation_origin) "
            "VALUES ($1,$2,'addition',1,'user',$3,true)",
            deck_id,
            card_id,
            "Discover source selection (unassessed)",
        )
