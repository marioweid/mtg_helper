"""Explicit source-backed additions with origin-aware transactional completion guards."""

from uuid import UUID

import asyncpg

from mtg_helper.services.new_cards.completion import validate_addition as validate_legacy_addition
from mtg_helper.services.planned_change_service import InvalidPlanError
from mtg_helper.services.recommendations import budget
from mtg_helper.services.recommendations.repository import (
    DiscoveryError,
    Owner,
    owned_deck,
    owned_run,
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

    async def plan(
        self, owner: Owner, deck_id: UUID, oracle_id: UUID, *, run_id: UUID | None = None
    ) -> None:
        """Plan one pending copy idempotently, never mutate physical cards or an opposite cut."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await owned_deck(conn, owner, deck_id, lock=True)
            await conn.execute("SELECT pg_advisory_xact_lock_shared(71382041)")
            if run_id:
                await self._validate_advice(conn, owner, deck, run_id, oracle_id=oracle_id)
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
            leader = await conn.fetchval(
                "SELECT source_facts FROM new_card_catalog WHERE oracle_id = $1",
                deck["commander_oracle_id"],
            )
            if deck["partner_id"] or leader is None:
                raise DiscoveryError("Discover planning requires supported commander facts", 409)
            error = eligibility_error(
                facts, set(value(leader)["color_identity"]), str(deck["commander_oracle_id"])
            )
            if error or not paper_design(facts):
                raise DiscoveryError("This source card is not eligible for Discover", 409)
            await self._insert(conn, deck_id, card["id"], run_id=run_id)

    async def _insert(
        self,
        conn: asyncpg.Connection,
        deck_id: UUID,
        card_id: UUID,
        *,
        run_id: UUID | None,
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
        reason = "recommendation (unverified)" if run_id else "manual source browse (unassessed)"
        await conn.execute(
            "INSERT INTO deck_card_plans (deck_id, card_id, direction, quantity, "
            "added_by, ai_reasoning, recommendation_origin) "
            "VALUES ($1,$2,'addition',1,'user',$3,true)",
            deck_id,
            card_id,
            f"Discover {reason}",
        )

    async def _validate_advice(
        self,
        conn: asyncpg.Connection,
        owner: Owner,
        deck: asyncpg.Record,
        run_id: UUID,
        *,
        oracle_id: UUID,
    ) -> None:
        run = await owned_run(conn, owner, deck["id"], run_id)
        context, data = value(run["context"]), value(run["data"])
        current_hash = await conn.fetchval("SELECT source_sha256 FROM new_card_catalog_state")
        stale = (
            current_hash != run["source_hash"]
            or run["profile"] != budget.VERSION
            or context["commander"]["oracle_id"] != str(deck["commander_oracle_id"])
        )
        candidate = next(
            (c for c in data.get("candidates", []) if c["oracle_id"] == str(oracle_id)), None
        )
        valid = {
            r["key"]
            for r in data.get("review", {}).get("recommendations", [])
            if r["recommendation_valid"]
        }
        if stale or not candidate or candidate["key"] not in valid:
            raise DiscoveryError(
                "Advice is stale/unvalidated; use explicit manual source planning", 409
            )
