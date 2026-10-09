"""Authenticated application orchestration; slow AI never owns ordinary browsing."""

import asyncio
import hashlib
import json
import logging
from uuid import UUID

import asyncpg

from mtg_helper.models.recommendations import (
    DiscoveryStatus,
    GenerateRequest,
    PilotFeedback,
    QueryPage,
    QueryPreview,
    RunView,
    StrategyDraftRequest,
)
from mtg_helper.services import feature_flag_service
from mtg_helper.services.recommendations import budget, pipeline, strategy, views
from mtg_helper.services.recommendations.planning import Planner
from mtg_helper.services.recommendations.provider import Provider
from mtg_helper.services.recommendations.repository import (
    DiscoveryError,
    Owner,
    exclusions,
    owned_deck,
    owned_run,
    value,
)
from mtg_helper.services.recommendations.run_repository import NewRun, RunRepository, Work
from mtg_helper.services.recommendations.source import Card
from mtg_helper.services.recommendations.source_repository import SourceRepository

_log = logging.getLogger(__name__)


def leader_for_deck(deck: asyncpg.Record, cards: Card) -> Card:
    if deck["partner_id"]:
        raise DiscoveryError("Partner/background decks are unsupported in this first pilot", 409)
    leader = cards.get(str(deck["commander_oracle_id"]))
    if leader is None or leader["legalities"].get("commander") != "legal":
        raise DiscoveryError("Commander source facts unavailable; sync cards", 503)
    return leader


def request_payload(phase: str, payload: Card, fixed: pipeline.profiles.Stage) -> Card:
    return {
        "model": budget.MODEL,
        "service_tier": "default",
        "instructions": fixed.prompt,
        "input": json.dumps(payload, ensure_ascii=False),
        "max_output_tokens": fixed.output_limit,
        "store": False,
        "reasoning": {"effort": "low"},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "strict": True,
                "name": f"discover_{phase}",
                "schema": fixed.schema.model_json_schema(),
            },
        },
    }


class DiscoveryService:
    """Own source readiness, immutable runs, bounded execution and explicit owner actions."""

    def __init__(self, pool: asyncpg.Pool, sources: SourceRepository, provider: Provider) -> None:
        self.pool = pool
        self.sources = sources
        self.provider = provider
        self.runs = RunRepository(pool)
        self.planner = Planner(pool)

    async def status(self, owner: Owner, deck_id: UUID) -> DiscoveryStatus:
        async with self.pool.acquire() as conn:
            deck = await owned_deck(conn, owner, deck_id)
        await self.runs.expire(owner)
        status = DiscoveryStatus(goal_seed=deck["description"] or "")
        try:
            cards_hash, rules_hash = await self.sources.current()
            sources = await self.sources.load(cards_hash, rules_hash)
            leader_for_deck(deck, sources.cards)
            status.ready = True
            status.source_hash, status.rules_hash = cards_hash, rules_hash
        except (OSError, ValueError) as exc:
            status.reason = str(exc)
        async with self.pool.acquire() as conn:
            status.catalog_updated_at = await conn.fetchval(
                "SELECT published_at FROM new_card_catalog_state"
            )
            rows = await conn.fetch(
                "SELECT DISTINCT ON (profile = $3) * FROM recommendation_runs "
                "WHERE account_id = $1 AND deck_id = $2 "
                "ORDER BY (profile = $3), created_at DESC",
                owner.account_id,
                deck_id,
                budget.STRATEGY_VERSION,
            )
            for row in rows:
                view = views.run_view(
                    dict(row),
                    await exclusions(conn, owner, deck_id),
                    commander_id=str(deck["commander_oracle_id"]),
                    source_hash=status.source_hash,
                )
                if row["profile"] == budget.STRATEGY_VERSION:
                    status.strategy_run = view
                else:
                    status.run = view
        return status

    async def preview(self, owner: Owner, deck_id: UUID, request: QueryPreview) -> QueryPage:
        async with self.pool.acquire() as conn:
            deck = await owned_deck(conn, owner, deck_id)
            hidden = await exclusions(conn, owner, deck_id)
        try:
            cards_hash, rules_hash = await self.sources.current()
            sources = await self.sources.load(
                request.snapshot_hash or cards_hash, request.rules_hash or rules_hash
            )
        except (OSError, ValueError) as exc:
            status = 410 if request.snapshot_hash or request.rules_hash else 503
            raise DiscoveryError(
                "Pinned sources unavailable; restart or ask Admin to sync", status
            ) from exc
        try:
            return await asyncio.to_thread(
                views.browse, sources, leader_for_deck(deck, sources.cards), hidden, request
            )
        except ValueError as exc:
            raise DiscoveryError(str(exc), 422) from exc

    async def generate(
        self, owner: Owner, deck_id: UUID, request: GenerateRequest
    ) -> tuple[UUID, Work | None]:
        return await self._create(owner, deck_id, request, profile=budget.VERSION)

    async def draft_strategy(
        self, owner: Owner, deck_id: UUID, request: StrategyDraftRequest
    ) -> tuple[UUID, Work | None]:
        """Reserve one source-only draft request, independently of card generation."""
        goal = GenerateRequest(
            request_key=request.request_key, goal="Draft a commander-only strategy"
        )
        return await self._create(owner, deck_id, goal, profile=budget.STRATEGY_VERSION)

    async def _create(
        self, owner: Owner, deck_id: UUID, request: GenerateRequest, *, profile: str
    ) -> tuple[UUID, Work | None]:
        async with self.pool.acquire() as conn:
            await owned_deck(conn, owner, deck_id)
        try:
            cards_hash, rules_hash = await self.sources.current()
            sources = await self.sources.load(cards_hash, rules_hash)
        except (OSError, ValueError) as exc:
            raise DiscoveryError(
                "Complete sources unavailable; ask Admin to sync cards", 503
            ) from exc
        async with self.pool.acquire() as conn, conn.transaction(isolation="repeatable_read"):
            deck = await owned_deck(conn, owner, deck_id)
            if deck["suggestion_collection_ids"]:
                raise DiscoveryError(
                    "Collection-scoped discovery is not supported yet; "
                    "clear that scope explicitly or use Community Picks",
                    409,
                )
            hidden = await exclusions(conn, owner, deck_id)
            leader = leader_for_deck(deck, sources.cards)
        if request.constraint:
            try:
                pipeline.validate_query(request.constraint)
            except ValueError as exc:
                raise DiscoveryError(f"Unsupported literal constraint: {exc}", 422) from exc
        signature = request.model_dump(mode="json", exclude={"request_key"}) | {
            "deck_id": str(deck_id)
        }
        if profile == budget.STRATEGY_VERSION:
            signature["purpose"] = "strategy_draft"
        fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        context = {
            "commander": leader,
            "goal": request.goal,
            "constraint": request.constraint.model_dump() if request.constraint else None,
            "excluded_ids": sorted(hidden | {str(i) for i in request.excluded_ids}),
            "seed": f"{cards_hash}|{fingerprint}|{profile}",
        }
        return await self.runs.create(
            NewRun(
                owner=owner,
                deck_id=deck_id,
                request_key=request.request_key,
                request_hash=fingerprint,
                source_hash=cards_hash,
                rules_hash=rules_hash,
                context=context,
                profile=profile,
            )
        )

    async def run(self, work: Work) -> None:
        """Execute each checkpoint once; record unknown billing before stopping dependent work."""
        try:
            sources = await self.sources.load(work.source_hash, work.rules_hash)
            workflow = (
                strategy.Workflow(context=work.context)
                if work.profile == budget.STRATEGY_VERSION
                else pipeline.Workflow(sources=sources, context=work.context)
            )
            data: Card = {}
            for phase, bound in budget.bounds(work.profile).items():
                if not await feature_flag_service.is_enabled(
                    self.pool, "recommendations", work.owner.account_id, False
                ):
                    await self.runs.stop(work, "Discover capability was disabled; run stopped")
                    return
                payload = await asyncio.to_thread(workflow.payload, phase, data)
                fixed = pipeline.check_request(phase, payload, profile=work.profile)
                frozen = request_payload(phase, payload, fixed)
                if not await self.runs.checkpoint(work, phase, frozen):
                    return
                receipt, price = await self._call(frozen, bound)
                await self.runs.receipt(work, phase, receipt, price)
                if price is None:
                    await self.runs.stop(
                        work,
                        "Unknown billing; no further requests. Ask an admin to reconcile the hold.",
                        unknown=True,
                    )
                    return
                if receipt.get("status") != "completed":
                    raise ValueError("Provider response incomplete; no dependent request sent")
                data = await asyncio.to_thread(workflow.accept, phase, receipt["output"], data)
                if not await self.runs.publish(work, phase, data):
                    return
        except Exception as exc:
            # Provider/validation errors can contain private prompt fragments; report type only.
            _log.error("Discover stopped (%s)", type(exc).__name__)
            await self.runs.stop(
                work,
                "Discovery failed validation or source checks; "
                "inspect your private trace. No retry was sent.",
            )

    async def _call(self, frozen: Card, bound: tuple[int, int]) -> tuple[Card, int | None]:
        try:
            receipt = await self.provider.request(frozen)
        except Exception as exc:
            return {
                "error": type(exc).__name__,
                "request_id": getattr(exc, "request_id", None),
            }, None
        try:
            return receipt, budget.usage_cost(receipt, bound)
        except ValueError:
            return receipt, None

    async def view(self, owner: Owner, deck_id: UUID, run_id: UUID) -> RunView:
        await self.runs.expire(owner)
        async with self.pool.acquire() as conn:
            row = await owned_run(conn, owner, deck_id, run_id)
            deck = await owned_deck(conn, owner, deck_id)
            current = await conn.fetchval("SELECT source_sha256 FROM new_card_catalog_state")
            return views.run_view(
                dict(row),
                await exclusions(conn, owner, deck_id),
                commander_id=str(deck["commander_oracle_id"]),
                source_hash=current,
            )

    async def trace(self, owner: Owner, deck_id: UUID, run_id: UUID) -> Card:
        async with self.pool.acquire() as conn:
            row = await owned_run(conn, owner, deck_id, run_id)
            attempts = await conn.fetch(
                "SELECT phase, status, request, receipt, reservation_microusd, cost_microusd "
                "FROM recommendation_attempts WHERE run_id = $1 ORDER BY attempted_at",
                run_id,
            )
        return {
            "profile": row["profile"],
            "model": budget.MODEL,
            "pricing_url": budget.PRICING_URL,
            "source_hash": row["source_hash"],
            "rules_hash": row["rules_hash"],
            "context": value(row["context"]),
            "data": value(row["data"]),
            "attempts": [
                {
                    k: value(v) if k in {"request", "receipt"} and v else v
                    for k, v in dict(a).items()
                }
                for a in attempts
            ],
        }

    async def feedback(
        self, owner: Owner, deck_id: UUID, run_id: UUID, feedback: PilotFeedback
    ) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            row = await owned_run(conn, owner, deck_id, run_id)
            candidates = value(row["data"]).get("candidates", [])
            if not any(c["oracle_id"] == str(feedback.oracle_id) for c in candidates):
                raise DiscoveryError("Candidate not in this run", 404)
            await conn.execute(
                "INSERT INTO recommendation_feedback (run_id, oracle_id, verdict, note) "
                "VALUES ($1,$2,$3,$4) ON CONFLICT (run_id, oracle_id) DO UPDATE SET "
                "verdict = EXCLUDED.verdict, note = EXCLUDED.note, updated_at = now()",
                run_id,
                feedback.oracle_id,
                feedback.verdict,
                feedback.note,
            )
