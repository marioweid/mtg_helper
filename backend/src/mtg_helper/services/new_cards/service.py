"""Explicit, bounded analysis and planning with PostgreSQL-owned leases and cached results."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import asyncpg

from mtg_helper.models.new_cards import NewCardsResponse
from mtg_helper.services.new_cards import repository
from mtg_helper.services.new_cards.completion import validate_addition
from mtg_helper.services.new_cards.evaluator import Assessment, EvidenceRequest, NewCardEvaluator
from mtg_helper.services.new_cards.repository import Candidate, NewCardsError, Owner, json_value
from mtg_helper.services.planned_change_service import InvalidPlanError

_log = logging.getLogger(__name__)
DAILY_BATCH_LIMIT = 30


@dataclass(slots=True)
class Work:
    owner: Owner
    deck_id: UUID
    token: UUID
    candidates: list[Candidate]
    request: EvidenceRequest


class NewCardsService:
    """Own the discovery workflow; endpoint handlers only authenticate and delegate."""

    def __init__(self, pool: asyncpg.Pool, evaluator: NewCardEvaluator) -> None:
        self.pool = pool
        self.evaluator = evaluator

    async def view(self, owner: Owner, deck_id: UUID) -> NewCardsResponse:
        """Read one consistent snapshot, rechecking ownership even on a cache hit."""
        async with self.pool.acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                deck = await repository.owned_deck(conn, owner, deck_id)
                state = await repository.load(conn, owner, deck)
                return state.response()

    async def claim(self, owner: Owner, deck_id: UUID) -> Work | None:
        """Claim at most eight candidates; repeated concurrent clicks never spawn duplicate work."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await repository.owned_deck(conn, owner, deck_id, lock=True)
            state = await repository.load(conn, owner, deck)
            if not state.ready:
                raise NewCardsError("Run Admin card sync before analyzing New Cards.", 503)
            candidates = state.pending()[:8]
            if not candidates:
                return None
            request = EvidenceRequest(
                state.context, [c.facts.model_dump(mode="json") for c in candidates]
            )
            try:
                request.payload()  # Check bounds before consuming a quota slot.
            except ValueError as exc:
                raise NewCardsError(str(exc)) from exc
            token = await _claim_lease(conn, owner, deck_id)
            return Work(owner, deck_id, token, candidates, request) if token else None

    async def run(self, work: Work) -> None:
        """Execute one no-retry call and publish only if the lease and all input versions match."""
        try:
            async with asyncio.timeout(90):
                assessments = await self.evaluator.evaluate(work.request)
            await self._publish(work, assessments)
        except NewCardsError as exc:
            await self._fail(work, str(exc))
        except Exception as exc:
            # No exception body/traceback: provider errors may echo private prompt fragments.
            _log.error("New Cards analysis failed (%s)", type(exc).__name__)
            await self._fail(
                work,
                "Analysis failed or did not pass evidence checks. "
                "Cached suggestions are retained; retry or report this issue.",
            )

    async def _publish(self, work: Work, assessments: list[Assessment]) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await repository.owned_deck(conn, work.owner, work.deck_id, lock=True)
            lease = await conn.fetchrow(
                "SELECT * FROM new_card_jobs WHERE account_id = $1 AND token = $2 "
                "AND lease_until > now() FOR UPDATE",
                work.owner.account_id,
                work.token,
            )
            if lease is None:
                return  # A later claimant owns publication; this worker cannot overwrite it.
            state = await repository.load(conn, work.owner, deck)
            current = {candidate.oracle_id: candidate.input_hash for candidate in state.candidates}
            if any(current.get(c.oracle_id) != c.input_hash for c in work.candidates):
                raise NewCardsError(
                    "Deck, plans, preferences or source changed. Analyze again.", 409
                )
            pairs = list(zip(work.candidates, assessments, strict=True))
            await conn.executemany(
                """
                INSERT INTO new_card_assessments
                    (deck_id, account_id, oracle_id, input_hash, assessment, assessed_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, now())
                ON CONFLICT (deck_id, account_id, oracle_id) DO UPDATE SET
                    input_hash = EXCLUDED.input_hash, assessment = EXCLUDED.assessment,
                    assessed_at = EXCLUDED.assessed_at
                """,
                [
                    (
                        work.deck_id,
                        work.owner.account_id,
                        c.oracle_id,
                        c.input_hash,
                        assessment.model_dump_json(),
                    )
                    for c, assessment in pairs
                ],
            )
            await conn.execute(
                "UPDATE new_card_jobs SET token = NULL, lease_until = NULL, error = NULL, "
                "finished_at = now() WHERE account_id = $1 AND token = $2",
                work.owner.account_id,
                work.token,
            )

    async def _fail(self, work: Work, message: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE new_card_jobs SET token = NULL, lease_until = NULL, error = $3, "
                "finished_at = now() WHERE account_id = $1 AND token = $2",
                work.owner.account_id,
                work.token,
                message,
            )

    async def dismiss(self, owner: Owner, deck_id: UUID, oracle_id: UUID, *, undo: bool) -> None:
        """Persist or undo one deck-local dismissal without altering a user's deck or plans."""
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
                "SELECT EXISTS(SELECT 1 FROM new_card_catalog WHERE oracle_id = $1)",
                oracle_id,
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
        """Idempotently plan one guarded addition, never a physical card."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await repository.owned_deck(conn, owner, deck_id, lock=True)
            planned = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM deck_card_plans p JOIN cards c ON c.id = p.card_id "
                "WHERE p.deck_id = $1 AND p.direction = 'addition' AND c.oracle_id = $2)",
                deck_id,
                oracle_id,
            )
            if planned:
                return
            await conn.execute("SELECT pg_advisory_xact_lock_shared(71382041)")
            state = await repository.load(conn, owner, deck)
            candidate = next((c for c in state.candidates if c.oracle_id == oracle_id), None)
            if candidate is None or not state.valid(candidate):
                raise NewCardsError(
                    "Suggestion is no longer current. Refresh and analyze again.", 409
                )
            assessment = Assessment.model_validate(
                json_value(state.cached[oracle_id]["assessment"])
            )
            if assessment.label == "reject":
                raise NewCardsError("This card is not a suggested addition.", 409)
            try:
                await validate_addition(conn, deck_id, candidate.row["id"], 1)
            except InvalidPlanError as exc:
                raise NewCardsError(str(exc)) from exc
            await conn.execute(
                """
                INSERT INTO deck_card_plans
                    (deck_id, card_id, direction, quantity,
                     added_by, ai_reasoning, new_cards_origin)
                VALUES ($1, $2, 'addition', 1, 'user', $3, true)
                ON CONFLICT (deck_id, card_id) DO NOTHING
                """,
                deck_id,
                candidate.row["id"],
                "Experimental New Cards suggestion (unverified): " + assessment.reason,
            )


async def _claim_lease(conn: asyncpg.Connection, owner: Owner, deck_id: UUID) -> UUID | None:
    await conn.execute(
        "INSERT INTO new_card_jobs (account_id) VALUES ($1) ON CONFLICT DO NOTHING",
        owner.account_id,
    )
    job = await conn.fetchrow(
        "SELECT * FROM new_card_jobs WHERE account_id = $1 FOR UPDATE",
        owner.account_id,
    )
    now = datetime.now(UTC)
    if job["token"] and job["lease_until"] > now:
        if job["deck_id"] != deck_id:
            raise NewCardsError(
                "Another deck's New Cards analysis is running. Try again shortly.", 409
            )
        return None
    calls = job["calls"] if job["quota_day"] == now.date() else 0
    if calls >= DAILY_BATCH_LIMIT:
        raise NewCardsError(
            "Daily New Cards limit reached (30 batches). Try again tomorrow UTC.", 429
        )
    token = uuid4()
    await conn.execute(
        "UPDATE new_card_jobs SET deck_id = $2, token = $3, "
        "lease_until = now() + interval '2 minutes', "
        "quota_day = $4, calls = $5, error = NULL WHERE account_id = $1",
        owner.account_id,
        deck_id,
        token,
        now.date(),
        calls + 1,
    )
    return token
