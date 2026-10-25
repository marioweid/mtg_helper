"""Read-only Scryfall tag matching and explicit deck-local actions."""

from uuid import UUID

import asyncpg

from mtg_helper.models.new_cards import NewCardsResponse
from mtg_helper.services.new_cards import repository
from mtg_helper.services.new_cards.completion import validate_addition
from mtg_helper.services.new_cards.repository import NewCardsError, Owner
from mtg_helper.services.planned_change_service import InvalidPlanError


class NewCardsService:
    """Keep New Cards matching, ownership, and plan guards behind one module interface."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def view(self, owner: Owner, deck_id: UUID) -> NewCardsResponse:
        """Read one source-consistent result without external calls or database writes."""
        async with self.pool.acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                deck = await repository.owned_deck(conn, owner, deck_id)
                return (await repository.load(conn, owner, deck)).response()

    async def dismiss(self, owner: Owner, deck_id: UUID, oracle_id: UUID, *, undo: bool) -> None:
        """Persist or undo one deck-local dismissal without changing any physical card."""
        async with self.pool.acquire() as conn, conn.transaction():
            await repository.owned_deck(conn, owner, deck_id, lock=True)
            if undo:
                await conn.execute(
                    "DELETE FROM new_card_dismissals WHERE deck_id = $1 "
                    "AND account_id = $2 AND oracle_id = $3",
                    deck_id,
                    owner.account_id,
                    oracle_id,
                )
                return
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM new_card_catalog WHERE oracle_id = $1)", oracle_id
            )
            if not exists:
                raise NewCardsError("Card not found", 404)
            await conn.execute(
                "INSERT INTO new_card_dismissals (deck_id, account_id, oracle_id) "
                "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                deck_id,
                owner.account_id,
                oracle_id,
            )

    async def plan(self, owner: Owner, deck_id: UUID, oracle_id: UUID) -> None:
        """Idempotently save a currently visible match as a pending addition."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await repository.owned_deck(conn, owner, deck_id, lock=True)
            state = await repository.load(conn, owner, deck)
            candidate = next(
                (item for item in state.candidates if item.oracle_id == oracle_id), None
            )
            if state.status != "ready" or candidate is None:
                raise NewCardsError("Tag match is no longer current. Refresh New Cards.", 409)
            planned = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM deck_card_plans p JOIN cards c ON c.id = p.card_id "
                "WHERE p.deck_id = $1 AND p.direction = 'addition' AND c.oracle_id = $2)",
                deck_id,
                oracle_id,
            )
            if planned:
                return
            try:
                await validate_addition(conn, deck_id, candidate.row["id"], 1)
            except InvalidPlanError as exc:
                raise NewCardsError(str(exc)) from exc
            await conn.execute(
                "INSERT INTO deck_card_plans (deck_id, card_id, direction, quantity, added_by, "
                "ai_reasoning, new_cards_origin) VALUES ($1, $2, 'addition', 1, "
                "'user', NULL, true) ON CONFLICT (deck_id, card_id) DO NOTHING",
                deck_id,
                candidate.row["id"],
            )
