"""Authenticated application orchestration; slow AI never owns ordinary browsing."""

import asyncio
import hashlib
import json
import logging
from uuid import UUID

import asyncpg

from mtg_helper.models.recommendations import (
    DiscoverSetup,
    GenerateRequest,
    PilotFeedback,
    QueryPage,
    QueryPreview,
    RunView,
    StrategyDraftRequest,
    TermSuggestionRequest,
    TermSuggestionRun,
)
from mtg_helper.services import feature_flag_service
from mtg_helper.services.recommendations import (
    artwork,
    budget,
    pipeline,
    strategy,
    term_selection,
    views,
)
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
from mtg_helper.services.recommendations.term_catalog import suggestion_catalog

_log = logging.getLogger(__name__)


def leader_for_deck(deck: asyncpg.Record, cards: Card) -> Card:
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

    async def preview(self, owner: Owner, deck_id: UUID, request: QueryPreview) -> QueryPage:
        async with self.pool.acquire() as conn:
            deck = await owned_deck(conn, owner, deck_id)
            hidden = await exclusions(conn, deck_id)
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
            page = await asyncio.to_thread(
                views.browse, sources, leader_for_deck(deck, sources.cards), hidden, request
            )
            async with self.pool.acquire() as conn:
                await artwork.attach(conn, page.cards)
            return page
        except ValueError as exc:
            raise DiscoveryError(str(exc), 422) from exc

    async def draft_strategy(
        self, owner: Owner, deck_id: UUID, request: StrategyDraftRequest
    ) -> tuple[UUID, Work | None]:
        """Reserve one source-only draft request, independently of card generation."""
        goal = GenerateRequest(
            request_key=request.request_key, goal="Draft a commander-only strategy"
        )
        return await self._create(
            owner, deck_id, goal, profile=budget.STRATEGY_VERSION, reuse_latest=request.reuse_latest
        )

    async def suggest_terms(
        self, owner: Owner, deck_id: UUID, request: TermSuggestionRequest
    ) -> tuple[UUID, Work | None]:
        """Reserve one explicit, catalog-bounded term selection without saving it."""
        async with (
            self.pool.acquire() as conn,
            conn.transaction(isolation="repeatable_read", readonly=True),
        ):
            deck = await owned_deck(conn, owner, deck_id)
            cards = await conn.fetchrow(
                "SELECT source_sha256 FROM new_card_catalog_state WHERE singleton"
            )
            assert cards is not None
            tag_hash = await conn.fetchval(
                "SELECT tag_sha256 FROM scryfall_tag_state WHERE singleton"
            )
            saved = await conn.fetchrow(
                "SELECT revision FROM discover_strategies WHERE deck_id=$1 AND account_id=$2",
                deck_id,
                owner.account_id,
            )
            if (saved["revision"] if saved else None) != request.strategy_revision:
                raise DiscoveryError(
                    "Strategy changed elsewhere; reload before requesting terms", 409
                )
            commander_rows = await conn.fetch(
                "SELECT n.source_facts FROM cards c JOIN new_card_catalog n "
                "ON n.oracle_id=c.oracle_id "
                "JOIN new_card_catalog_state s ON s.generation=n.generation "
                "WHERE c.id=ANY($1::uuid[]) ORDER BY c.id",
                [deck["commander_id"]] + ([deck["partner_id"]] if deck["partner_id"] else []),
            )
            expected = 2 if deck["partner_id"] else 1
            if len(commander_rows) != expected:
                raise DiscoveryError("Commander source facts are unavailable; sync cards", 503)
            commanders = [value(row["source_facts"]) for row in commander_rows]
            catalog = await suggestion_catalog(conn, commanders, request.prose)
        _, rules_hash = await self.sources.current()
        context = {
            "prose": request.prose,
            "strategy_revision": str(request.strategy_revision)
            if request.strategy_revision
            else None,
            "source_hash": cards["source_sha256"],
            "tag_source_hash": tag_hash,
            "oracle_tags": [tag | {"id": str(tag["id"])} for tag in catalog.oracle_tags],
            "printed_keywords": catalog.printed_keywords,
            "commanders": commanders,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json", exclude={"request_key", "reuse_latest"}),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return await self.runs.create(
            NewRun(
                owner=owner,
                deck_id=deck_id,
                request_key=request.request_key,
                request_hash=fingerprint,
                source_hash=cards["source_sha256"],
                rules_hash=rules_hash,
                context=context,
                profile=budget.BOUNDED_TERMS_VERSION,
                reuse_latest=request.reuse_latest,
            )
        )

    async def _create(
        self,
        owner: Owner,
        deck_id: UUID,
        request: GenerateRequest,
        *,
        profile: str,
        reuse_latest: bool = False,
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
            hidden = await exclusions(conn, deck_id)
            leader = leader_for_deck(deck, sources.cards)
            commanders = self._strategy_commanders(deck, leader, sources.cards, profile)
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
        if profile == budget.STRATEGY_VERSION:
            context["commanders"] = commanders
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
                reuse_latest=reuse_latest,
            )
        )

    @staticmethod
    def _strategy_commanders(
        deck: asyncpg.Record, leader: Card, cards: Card, profile: str
    ) -> list[Card]:
        if profile != budget.STRATEGY_VERSION or not deck["partner_id"]:
            return [leader]
        partner = cards.get(str(deck["partner_oracle_id"]))
        if partner is None or partner["legalities"].get("commander") != "legal":
            raise DiscoveryError("Commander source facts unavailable; sync cards", 503)
        return [leader, partner]

    async def run(self, work: Work) -> None:
        """Execute each checkpoint once, preserving receipts independently of output validity."""
        try:
            workflow = await self._workflow(work)
            data: Card = {}
            for phase, bound in budget.bounds(work.profile).items():
                updated = await self._run_phase(work, workflow, phase, bound, data=data)
                if updated is None:
                    return
                data = updated
        except Exception as exc:
            # Provider/validation errors can contain private prompt fragments; report type only.
            _log.error("Discover stopped (%s)", type(exc).__name__)
            await self.runs.stop(
                work,
                "We couldn't prepare this strategy. Try again or edit your strategy; "
                "your saved cards and strategy are unchanged.",
            )

    async def _run_phase(
        self,
        work: Work,
        workflow: strategy.Workflow | term_selection.Workflow,
        phase: str,
        bound: tuple[int, int],
        *,
        data: Card,
    ) -> Card | None:
        if not await feature_flag_service.is_enabled(
            self.pool, "recommendations", work.owner.account_id, False
        ):
            await self.runs.stop(work, "Discover capability was disabled; run stopped")
            return None
        payload = await asyncio.to_thread(workflow.payload, phase, data)
        fixed = pipeline.check_request(phase, payload, profile=work.profile)
        frozen = request_payload(phase, payload, fixed)
        if not await self.runs.checkpoint(work, phase, frozen):
            return None
        receipt, price = await self._call(frozen, bound)
        await self.runs.receipt(work, phase, receipt, price)
        if price is None and receipt.get("status") != "completed":
            await self.runs.stop(
                work,
                "AI couldn't finish this request. Try again or write your own strategy.",
                unknown=True,
            )
            return None
        if receipt.get("status") != "completed":
            raise ValueError("Provider response incomplete; no dependent request sent")
        accepted = await asyncio.to_thread(workflow.accept, phase, receipt["output"], data)
        if not await self._publishable(work):
            await self.runs.stop(work, "Strategy or Scryfall sources changed; request terms again")
            return None
        return accepted if await self.runs.publish(work, phase, accepted) else None

    async def setup(self, owner: Owner, deck_id: UUID) -> DiscoverSetup:
        """Recover the latest applicable setup work without starting a model call."""
        await self.runs.expire(owner)
        async with self.pool.acquire() as conn:
            await owned_deck(conn, owner, deck_id)
            rows = await conn.fetch(
                "SELECT DISTINCT ON (profile) * FROM recommendation_runs "
                "WHERE account_id=$1 AND deck_id=$2 AND profile=ANY($3::text[]) "
                "ORDER BY profile,created_at DESC,id DESC",
                owner.account_id,
                deck_id,
                [budget.STRATEGY_VERSION, budget.BOUNDED_TERMS_VERSION],
            )
        result = DiscoverSetup()
        for row in rows:
            work = self._stored_work(row, owner)
            if not await self._terms_current(work):
                continue
            if row["profile"] == budget.STRATEGY_VERSION:
                result.draft = await self.view(owner, deck_id, row["id"])
            else:
                result.suggestion = await self.terms_view(owner, deck_id, row["id"])
                result.prose = work.context["prose"]
        return result

    @staticmethod
    def _stored_work(row: asyncpg.Record, owner: Owner) -> Work:
        return Work(
            id=row["id"],
            token=row["token"],
            owner=owner,
            deck_id=row["deck_id"],
            source_hash=row["source_hash"],
            rules_hash=row["rules_hash"],
            context=value(row["context"]),
            profile=row["profile"],
        )

    async def _workflow(self, work: Work) -> strategy.Workflow | term_selection.Workflow:
        if work.profile == budget.BOUNDED_TERMS_VERSION:
            if not await self._terms_current(work):
                raise DiscoveryError(
                    "Strategy or Scryfall sources changed; request terms again", 409
                )
            return term_selection.Workflow(context=work.context)
        if work.profile == budget.STRATEGY_VERSION:
            return strategy.Workflow(context=work.context)
        raise DiscoveryError("This historical card-generation workflow is retired", 410)

    async def _publishable(self, work: Work) -> bool:
        return await self._terms_current(work)

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

    async def terms_view(self, owner: Owner, deck_id: UUID, run_id: UUID) -> TermSuggestionRun:
        """Return editable, source-validated suggestions for one owner-scoped work item."""
        await self.runs.expire(owner)
        async with self.pool.acquire() as conn:
            row = await owned_run(conn, owner, deck_id, run_id)
        if row["profile"] not in {budget.TERMS_VERSION, budget.BOUNDED_TERMS_VERSION}:
            raise DiscoveryError("Discover term suggestion not found", 404)
        data = value(row["data"])
        revision = data.get("strategy_revision")
        current = await self._terms_current(self._stored_work(row, owner))
        return TermSuggestionRun(
            id=row["id"],
            status=row["status"] if current else "interrupted",
            error=row["error"]
            if current
            else "Strategy or Scryfall sources changed; request terms again",
            queries=data.get("queries", []) if current else [],
            strategy_revision=UUID(revision) if revision else None,
            source_hash=data.get("source_hash"),
        )

    async def _terms_current(self, work: Work) -> bool:
        async with self.pool.acquire() as conn:
            cards = await conn.fetchrow(
                "SELECT source_sha256 FROM new_card_catalog_state WHERE singleton"
            )
            tags = await conn.fetchrow(
                "SELECT source_sha256,tag_sha256 FROM scryfall_tag_state WHERE singleton"
            )
            if cards is None or tags is None or cards["source_sha256"] != work.source_hash:
                return False
            if tags["source_sha256"] != work.source_hash:
                return False
            if work.context.get("tag_source_hash", tags["tag_sha256"]) != tags["tag_sha256"]:
                return False
            deck = await owned_deck(conn, work.owner, work.deck_id)
            current_commanders = {str(deck["commander_oracle_id"])}
            if deck["partner_oracle_id"]:
                current_commanders.add(str(deck["partner_oracle_id"]))
            expected = work.context.get("commanders", [work.context.get("commander", {})])
            if {str(card.get("oracle_id")) for card in expected} != current_commanders:
                return False
            if work.profile not in {budget.TERMS_VERSION, budget.BOUNDED_TERMS_VERSION}:
                return True
            revision = work.context.get("strategy_revision")
            current = await conn.fetchval(
                "SELECT revision::text FROM discover_strategies WHERE deck_id=$1 AND account_id=$2",
                work.deck_id,
                work.owner.account_id,
            )
            return current == revision

    async def view(self, owner: Owner, deck_id: UUID, run_id: UUID) -> RunView:
        await self.runs.expire(owner)
        async with self.pool.acquire() as conn:
            row = await owned_run(conn, owner, deck_id, run_id)
            if row["profile"] in {
                budget.TERMS_VERSION,
                budget.LEGACY_TERMS_VERSION,
                budget.BOUNDED_TERMS_VERSION,
            }:
                raise DiscoveryError("Use the term-suggestion status for this run", 404)
            deck = await owned_deck(conn, owner, deck_id)
            current = await conn.fetchval("SELECT source_sha256 FROM new_card_catalog_state")
            view = views.run_view(
                dict(row),
                await exclusions(conn, deck_id),
                commander_id=str(deck["commander_oracle_id"]),
                source_hash=current,
            )
            await artwork.attach(conn, view.candidates)
            return view

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
