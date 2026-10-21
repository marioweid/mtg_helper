"""Explicit, bounded analysis and planning with PostgreSQL-owned leases and cached results."""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg

from mtg_helper.config import settings
from mtg_helper.models.new_cards import NewCardsResponse
from mtg_helper.services import feature_flag_service
from mtg_helper.services.new_cards import repository
from mtg_helper.services.new_cards.completion import validate_addition
from mtg_helper.services.new_cards.evaluator import Assessment, EvidenceRequest, NewCardEvaluator
from mtg_helper.services.new_cards.repository import Candidate, NewCardsError, Owner, json_value
from mtg_helper.services.planned_change_service import InvalidPlanError

_log = logging.getLogger(__name__)
DAILY_BATCH_LIMIT = 100


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

    async def control_status(self) -> dict[str, object]:
        """Return the global control snapshot without triggering source or model work."""
        automatic_enabled = await feature_flag_service.is_enabled(
            self.pool, feature_flag_service.FLAG_NEW_CARDS_AUTOMATIC, None, False
        )
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM new_card_runs WHERE singleton")
            assert row is not None
            counts = await conn.fetchrow(
                "SELECT count(*) FILTER (WHERE error IS NULL) AS waiting, "
                "count(*) FILTER (WHERE error IS NOT NULL) AS failed FROM new_card_claims"
            )
            catalog = await conn.fetchrow(
                "SELECT published_at FROM new_card_catalog_state WHERE singleton"
            )
            return {
                "process_enabled": settings.enable_new_cards_worker,
                "automatic_enabled": automatic_enabled,
                "daily_limit": row["daily_limit"],
                "calls": row["calls"] if row["quota_day"] == datetime.now(UTC).date() else 0,
                "quota_day": row["quota_day"].isoformat(),
                "next_reset": f"{datetime.now(UTC).date() + timedelta(days=1)}T00:00:00Z",
                "manual_active": row["manual_active"],
                "automatic_active": row["automatic_active"],
                "cancelled": row["cancelled"],
                "last_error": row["last_error"],
                "source_updated_at": catalog["published_at"].isoformat() if catalog else None,
                "last_run_at": row["updated_at"].isoformat(),
                "waiting": counts["waiting"] if counts else 0,
                "failed": counts["failed"] if counts else 0,
            }

    async def configure(self, automatic_enabled: bool | None, daily_limit: int | None) -> None:
        """Persist safe global settings; limits never reset consumed quota."""
        if not settings.enable_new_cards_worker:
            raise NewCardsError("New Cards execution is disabled for this process.", 503)
        if daily_limit is not None and daily_limit < 1:
            raise NewCardsError("Daily limit must be a positive integer.")
        if automatic_enabled is not None:
            await feature_flag_service.set_flag(
                self.pool, feature_flag_service.FLAG_NEW_CARDS_AUTOMATIC, automatic_enabled
            )
        async with self.pool.acquire() as conn:
            # Enabling is prospective: an already-published catalog does not create a run.
            if automatic_enabled:
                catalog_day = await conn.fetchval(
                    "SELECT published_at::date FROM new_card_catalog_state WHERE singleton"
                )
                await conn.execute(
                    "UPDATE new_card_runs SET last_catalog_day = $1, updated_at = now() "
                    "WHERE singleton",
                    catalog_day,
                )
            elif automatic_enabled is False:
                await conn.execute(
                    "UPDATE new_card_runs SET automatic_active = false, updated_at = now() "
                    "WHERE singleton"
                )
            await conn.execute(
                "UPDATE new_card_runs SET daily_limit = COALESCE($1, daily_limit), "
                "updated_at = now() WHERE singleton",
                daily_limit,
            )

    async def cancel(self) -> None:
        """Prevent future claims while permitting an already-bound call to finish."""
        if not settings.enable_new_cards_worker:
            raise NewCardsError("New Cards execution is disabled for this process.", 503)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE new_card_runs SET cancelled = true, manual_active = false, "
                "automatic_active = false, updated_at = now() WHERE singleton"
            )

    async def start_manual(self) -> None:
        """Mark one shared manual run active; the worker drains it serially."""
        if not settings.enable_new_cards_worker:
            raise NewCardsError("New Cards execution is disabled for this process.", 503)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE new_card_runs SET manual_active = true, cancelled = false, "
                "last_error = NULL, updated_at = now() WHERE singleton"
            )
            await conn.execute(
                "UPDATE new_card_claims SET error = NULL, attempted_day = NULL "
                "WHERE error IS NOT NULL"
            )

    async def drain_manual(self) -> None:
        """Serially drain currently used constellations for one manual attempt."""
        try:
            while await self._manual_permitted():
                work = await self._next_manual_work()
                if work is None:
                    break
                await self.run(work)
        finally:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE new_card_runs SET manual_active = false, updated_at = now() "
                    "WHERE singleton"
                )

    async def drain_one(self) -> bool:
        """Run one authorized package, if durable state says that work may start."""
        if not settings.enable_new_cards_worker:
            return False
        work = await self._next_manual_work()
        if work is None:
            async with self.pool.acquire() as conn:
                run = await conn.fetchrow("SELECT * FROM new_card_runs WHERE singleton")
                assert run is not None
                active = run["active_token"] and run["active_lease_until"] > datetime.now(UTC)
                if not active:
                    await conn.execute(
                        "UPDATE new_card_runs SET manual_active = false, automatic_active = "
                        "CASE WHEN quota_day = $1 AND calls >= daily_limit THEN automatic_active "
                        "ELSE false END, updated_at = now() WHERE singleton",
                        datetime.now(UTC).date(),
                    )
            return False
        await self.run(work)
        return True

    async def activate_published_day(self) -> None:
        """Durably activate one automatic day after a successful catalog publication."""
        if not settings.enable_new_cards_worker:
            return
        if not await feature_flag_service.is_enabled(
            self.pool, feature_flag_service.FLAG_NEW_CARDS_AUTOMATIC, None, False
        ):
            return
        async with self.pool.acquire() as conn, conn.transaction():
            catalog_day = await conn.fetchval(
                "SELECT published_at::date FROM new_card_catalog_state WHERE singleton"
            )
            if catalog_day is None:
                return
            run = await conn.fetchrow("SELECT * FROM new_card_runs WHERE singleton FOR UPDATE")
            assert run is not None
            if run["last_catalog_day"] == catalog_day:
                return
            await conn.execute(
                "UPDATE new_card_runs SET automatic_active = true, cancelled = false, "
                "last_catalog_day = $1, last_error = NULL, updated_at = now() WHERE singleton",
                catalog_day,
            )
        await self._queue_automatic_constellations()

    async def _manual_permitted(self) -> bool:
        async with self.pool.acquire() as conn:
            run = await conn.fetchrow("SELECT * FROM new_card_runs WHERE singleton")
            assert run is not None
            calls = run["calls"] if run["quota_day"] == datetime.now(UTC).date() else 0
            return bool(
                run["manual_active"] and not run["cancelled"] and calls < run["daily_limit"]
            )

    async def _next_manual_work(self) -> Work | None:
        async with self.pool.acquire() as conn:
            run = await conn.fetchrow("SELECT * FROM new_card_runs WHERE singleton")
            assert run is not None
            automatic_only = run["automatic_active"] and not run["manual_active"]
            rows = await conn.fetch(
                "SELECT d.id, a.id AS account_id, a.email FROM decks d "
                "JOIN accounts a ON lower(a.email) = lower(d.owner_email) ORDER BY d.id"
            )
        for row in rows:
            try:
                if automatic_only and not await self._is_automatic_constellation(row):
                    continue
                work = await self.claim(Owner(row["account_id"], row["email"]), row["id"])
            except NewCardsError as error:
                if error.status == 429:
                    return None
                continue
            if work is not None:
                return work
        return None

    async def _is_automatic_constellation(self, row: asyncpg.Record) -> bool:
        """Allow an automatic day to process only its publication-time snapshot."""
        async with self.pool.acquire() as conn:
            deck = await repository.owned_deck(
                conn, Owner(row["account_id"], row["email"]), row["id"]
            )
            state = await repository.load(conn, Owner(row["account_id"], row["email"]), deck)
            return bool(
                await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM new_card_claims WHERE constellation_key = $1)",
                    state.constellation_key,
                )
            )

    async def _queue_automatic_constellations(self) -> None:
        """Persist the used Commander-Konstellationen at daily publication time."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT d.id, a.id AS account_id, a.email FROM decks d "
                "JOIN accounts a ON lower(a.email) = lower(d.owner_email) ORDER BY d.id"
            )
        for row in rows:
            async with self.pool.acquire() as conn, conn.transaction():
                owner = Owner(row["account_id"], row["email"])
                deck = await repository.owned_deck(conn, owner, row["id"], lock=True)
                state = await repository.load(conn, owner, deck)
                if not state.ready:
                    continue
                await _ensure_constellation(conn, state)
                await conn.execute(
                    "INSERT INTO new_card_claims (constellation_key) VALUES ($1) "
                    "ON CONFLICT DO NOTHING",
                    state.constellation_key,
                )

    async def claim(self, owner: Owner, deck_id: UUID) -> Work | None:
        """Claim globally shared work after an authorized global start."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await repository.owned_deck(conn, owner, deck_id, lock=True)
            state = await repository.load(conn, owner, deck)
            if not settings.enable_new_cards_worker:
                raise NewCardsError("New Cards execution is disabled for this process.", 503)
            if not state.ready:
                raise NewCardsError("Current Commander facts are unavailable.", 503)
            if state.catalog and datetime.now(UTC) - state.catalog["published_at"] > timedelta(
                days=2
            ):
                raise NewCardsError("Card sources are too old to start New Cards.", 503)
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
            await _ensure_constellation(conn, state)
            token = await _claim_lease(conn, state.constellation_key)
            return Work(owner, deck_id, token, candidates, request) if token else None

    async def run(self, work: Work) -> None:
        """Execute one no-retry call and publish only if the lease and all input versions match."""
        try:
            if not await self._execution_permitted(work.token):
                await self._release(work)
                return
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

    async def _execution_permitted(self, token: UUID) -> bool:
        """Recheck process policy and the durable start authorization before a paid call."""
        if not settings.enable_new_cards_worker:
            return False
        async with self.pool.acquire() as conn:
            run = await conn.fetchrow("SELECT * FROM new_card_runs WHERE singleton")
            assert run is not None
            return bool(
                run["active_token"] == token
                and not run["cancelled"]
                and (run["manual_active"] or run["automatic_active"])
            )

    async def _release(self, work: Work) -> None:
        """Release an unstarted lease after a cancellation or process lock change."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE new_card_claims SET token = NULL, lease_until = NULL, updated_at = now() "
                "WHERE token = $1",
                work.token,
            )
            await conn.execute(
                "UPDATE new_card_runs SET active_token = NULL, active_lease_until = NULL, "
                "updated_at = now() WHERE singleton AND active_token = $1",
                work.token,
            )

    async def _publish(self, work: Work, assessments: list[Assessment]) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await repository.owned_deck(conn, work.owner, work.deck_id, lock=True)
            lease = await conn.fetchrow(
                "SELECT * FROM new_card_claims WHERE constellation_key = $1 AND token = $2 "
                "AND lease_until > now() FOR UPDATE",
                (await repository.load(conn, work.owner, deck)).constellation_key,
                work.token,
            )
            if lease is None:
                return  # A later claimant owns publication; this worker cannot overwrite it.
            state = await repository.load(conn, work.owner, deck)
            current = {candidate.oracle_id: candidate.input_hash for candidate in state.candidates}
            if any(current.get(c.oracle_id) != c.input_hash for c in work.candidates):
                raise NewCardsError("Deck, plans, or source changed. Analyze again.", 409)
            pairs = list(zip(work.candidates, assessments, strict=True))
            await conn.executemany(
                """
                INSERT INTO new_card_shared_assessments
                    (constellation_key, oracle_id, input_hash, assessment, assessed_at)
                VALUES ($1, $2, $3, $4::jsonb, now())
                ON CONFLICT (constellation_key, oracle_id) DO UPDATE SET
                    input_hash = EXCLUDED.input_hash, assessment = EXCLUDED.assessment,
                    assessed_at = EXCLUDED.assessed_at
                """,
                [
                    (
                        state.constellation_key,
                        c.oracle_id,
                        c.input_hash,
                        assessment.model_dump_json(),
                    )
                    for c, assessment in pairs
                ],
            )
            await conn.execute(
                "UPDATE new_card_claims SET token = NULL, lease_until = NULL, "
                "attempted_day = NULL, error = NULL, "
                "updated_at = now() WHERE constellation_key = $1 AND token = $2",
                state.constellation_key,
                work.token,
            )
            await conn.execute(
                "UPDATE new_card_runs SET active_token = NULL, active_lease_until = NULL, "
                "updated_at = now() WHERE singleton AND active_token = $1",
                work.token,
            )

    async def _fail(self, work: Work, message: str) -> None:
        async with self.pool.acquire() as conn:
            deck = await repository.owned_deck(conn, work.owner, work.deck_id)
            state = await repository.load(conn, work.owner, deck)
            await conn.execute(
                "UPDATE new_card_claims SET token = NULL, lease_until = NULL, error = $3, "
                "updated_at = now() WHERE constellation_key = $1 AND token = $2",
                state.constellation_key,
                work.token,
                message,
            )
            await conn.execute(
                "UPDATE new_card_runs SET active_token = NULL, active_lease_until = NULL, "
                "last_error = $2, updated_at = now() WHERE singleton AND active_token = $1",
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


async def _archive_superseded_assessments(
    conn: asyncpg.Connection,
    work: Work,
    pairs: list[tuple[Candidate, Assessment]],
) -> None:
    """Retain cache entries when a fresh context replaces their current value."""
    existing = await conn.fetch(
        "SELECT oracle_id, input_hash, assessment, assessed_at FROM new_card_assessments "
        "WHERE deck_id = $1 AND account_id = $2 AND oracle_id = ANY($3::uuid[])",
        work.deck_id,
        work.owner.account_id,
        [candidate.oracle_id for candidate, _ in pairs],
    )
    incoming = {candidate.oracle_id: candidate.input_hash for candidate, _ in pairs}
    archived = [row for row in existing if row["input_hash"] != incoming[row["oracle_id"]]]
    if not archived:
        return
    await conn.executemany(
        "INSERT INTO new_card_assessment_history "
        "(deck_id, account_id, oracle_id, input_hash, assessment, assessed_at) "
        "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING",
        [
            (
                work.deck_id,
                work.owner.account_id,
                row["oracle_id"],
                row["input_hash"],
                row["assessment"],
                row["assessed_at"],
            )
            for row in archived
        ],
    )


async def _ensure_constellation(conn: asyncpg.Connection, state: repository.DeckState) -> None:
    """Store current Commander facts before a shared claim references the constellation."""
    await conn.execute(
        "INSERT INTO new_card_constellations (key, commander_oracle_ids, commander_facts) "
        "VALUES ($1, $2, $3::jsonb) ON CONFLICT (key) DO UPDATE SET "
        "commander_facts = EXCLUDED.commander_facts, updated_at = now()",
        state.constellation_key,
        [UUID(card["oracle_id"]) for card in state.context["commanders"]],
        json.dumps(state.context["commanders"]),
    )


async def _claim_lease(conn: asyncpg.Connection, constellation_key: str) -> UUID | None:
    """Reserve one global package and its daily budget before calling the provider."""
    await conn.execute(
        "INSERT INTO new_card_claims (constellation_key) VALUES ($1) ON CONFLICT DO NOTHING",
        constellation_key,
    )
    job = await conn.fetchrow(
        "SELECT * FROM new_card_claims WHERE constellation_key = $1 FOR UPDATE",
        constellation_key,
    )
    now = datetime.now(UTC)
    if job["attempted_day"] == now.date():
        return None
    run = await conn.fetchrow("SELECT * FROM new_card_runs WHERE singleton FOR UPDATE")
    assert run is not None
    if run["active_token"] and run["active_lease_until"] > now:
        return None
    if run["cancelled"] or not (run["manual_active"] or run["automatic_active"]):
        return None
    calls = run["calls"] if run["quota_day"] == now.date() else 0
    if calls >= run["daily_limit"]:
        raise NewCardsError("Global daily New Cards limit reached. Try again tomorrow UTC.", 429)
    token = uuid4()
    await conn.execute(
        "UPDATE new_card_claims SET token = $2, "
        "lease_until = now() + interval '2 minutes', "
        "attempted_day = $3, error = NULL, updated_at = now() WHERE constellation_key = $1",
        constellation_key,
        token,
        now.date(),
    )
    await conn.execute(
        "UPDATE new_card_runs SET quota_day = $1, calls = $2, active_token = $3, "
        "active_lease_until = now() + interval '2 minutes', updated_at = now() WHERE singleton",
        now.date(),
        calls + 1,
        token,
    )
    return token


class NewCardsWorker:
    """Small application-owned worker that resumes durable New Cards claims."""

    def __init__(self, service: NewCardsService) -> None:
        self._service = service
        self._stopping = False
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the bounded poll loop once application resources are ready."""
        self._task = asyncio.create_task(self._run(), name="new-cards-worker")

    async def stop(self) -> None:
        """Stop claiming new work and wait briefly for the active package to settle."""
        self._stopping = True
        if self._task is None:
            return
        try:
            async with asyncio.timeout(95):
                await self._task
        except TimeoutError:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self._service.activate_published_day()
                worked = await self._service.drain_one()
            except Exception:
                _log.exception("New Cards worker iteration failed")
                worked = False
            await asyncio.sleep(0.05 if worked else 1)
