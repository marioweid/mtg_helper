"""Upgrade finder specialist for the Commander Coach pipeline."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import asyncpg
import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession
from pydantic_ai import Agent, RunContext, UsageLimitExceeded, UsageLimits

from mtg_helper.models.ai import (
    CardSearchHit,
    CardSearchInput,
    CoachCurveReport,
    CoachCutReport,
    CoachManaReport,
    CoachUpgradeCandidate,
    CoachUpgradeReport,
    DeckIdentityReport,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services import moxfield_recs_service
from mtg_helper.services.agents._model import make_google_model
from mtg_helper.services.card_search_tool import search_cards
from mtg_helper.services.commander_coach import pipeline

_log = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 10
_REQUEST_LIMIT = _MAX_TOOL_CALLS + 3
_TIMEOUT_SECONDS = 55.0
_SYSTEM_PROMPT = """You are the Upgrade Finder Agent for a Commander deck coach.
Find grounded cards to add, constrained by identity, mana, curve, cuts, bracket,
and current deck contents.

Rules:
- Use card_search before recommending additions.
- Only recommend exact cards returned by card_search.
- Prefer cards that solve needs from identity/mana/curve/cuts.
- Respect commander color identity; the tool enforces this.
- Avoid cards already in the deck; the tool enforces this except basic lands.
- For each upgrade, state the role and likely cut(s) it replaces.
- For casual Bracket 2-3 decks, avoid pushing into tutor/combo/staple soup unless requested.
"""


@dataclass
class UpgradeDeps:
    """Dependencies and mutable tool count for upgrade search."""

    pool: asyncpg.Pool
    deck: DeckDetailResponse
    deck_color_identity: list[str]
    deck_card_names: list[str]
    tool_call_count: list[int] = field(default_factory=lambda: [0])


def _build_agent() -> Agent[UpgradeDeps, CoachUpgradeReport]:
    agent = Agent[UpgradeDeps, CoachUpgradeReport](
        model=make_google_model(),
        deps_type=UpgradeDeps,
        output_type=CoachUpgradeReport,
        system_prompt=_SYSTEM_PROMPT,
        model_settings={"temperature": 0.35, "max_tokens": 6144},
        retries=1,
    )

    @agent.tool
    async def card_search(
        ctx: RunContext[UpgradeDeps],
        inp: CardSearchInput,
    ) -> list[CardSearchHit]:
        """Search legal upgrade candidates for this deck."""
        ctx.deps.tool_call_count[0] += 1
        started = time.monotonic()
        hits = await search_cards(
            ctx.deps.pool,
            deck_color_identity=ctx.deps.deck_color_identity,
            inp=inp,
            exclude_names=ctx.deps.deck_card_names,
        )
        _log.info(
            "upgrade card_search #%d returned %d hits in %.2fs",
            ctx.deps.tool_call_count[0],
            len(hits),
            time.monotonic() - started,
        )
        return hits

    return agent


_AGENT: Agent[UpgradeDeps, CoachUpgradeReport] | None = None


def _get_agent() -> Agent[UpgradeDeps, CoachUpgradeReport]:
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


async def recommend_upgrades(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    mana: CoachManaReport,
    curve: CoachCurveReport,
    cuts: CoachCutReport,
) -> CoachUpgradeReport:
    """Run the tool-using upgrade specialist."""
    deps = UpgradeDeps(
        pool=pool,
        deck=deck,
        deck_color_identity=pipeline.deck_colors(deck),
        deck_card_names=[card.name for card in deck.cards],
    )
    try:
        result = await asyncio.wait_for(
            _get_agent().run(
                json.dumps(_payload(deck, identity, mana, curve, cuts), default=str),
                deps=deps,
                usage_limits=UsageLimits(request_limit=_REQUEST_LIMIT),
            ),
            timeout=_TIMEOUT_SECONDS,
        )
        report = result.output
        report.tool_call_count = deps.tool_call_count[0]
        filtered = _filter_report(deck, report)
        return await _with_moxfield_candidates(pool, deck, identity, cuts, filtered)
    except (UsageLimitExceeded, TimeoutError):
        _log.warning("Upgrade Finder Agent exceeded limits")
    except Exception:  # noqa: BLE001 - Coach should still return analysis
        _log.exception("Upgrade Finder Agent failed")
    fallback = CoachUpgradeReport(summary="No grounded upgrades were found in this run.")
    return await _with_moxfield_candidates(pool, deck, identity, cuts, fallback)


def _payload(
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    mana: CoachManaReport,
    curve: CoachCurveReport,
    cuts: CoachCutReport,
) -> dict[str, Any]:
    return {
        "identity": identity.model_dump(),
        "mana_report": mana.model_dump(),
        "curve_report": curve.model_dump(),
        "cut_report": cuts.model_dump(),
        "deck_bracket": deck.bracket,
        "archetype_tags": list(deck.archetype_tags or []),
    }


def _filter_report(deck: DeckDetailResponse, report: CoachUpgradeReport) -> CoachUpgradeReport:
    names = {card.name for card in deck.cards}
    seen: set[str] = set()
    candidates = []
    for candidate in report.candidates:
        name = candidate.card.name
        if name in names or name in seen:
            continue
        seen.add(name)
        candidates.append(candidate)
    return CoachUpgradeReport(
        summary=report.summary,
        candidates=candidates[:12],
        tool_call_count=report.tool_call_count,
    )


async def _with_moxfield_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    cuts: CoachCutReport,
    report: CoachUpgradeReport,
) -> CoachUpgradeReport:
    """Blend top Moxfield inclusions into upgrade output as grounded candidates."""
    candidates = await _moxfield_candidates(pool, deck, identity, cuts)
    if not candidates:
        return report
    deck_names = {card.name for card in deck.cards}
    seen = set(deck_names)
    merged = []
    for candidate in [*candidates, *report.candidates]:
        if candidate.card.name in seen:
            continue
        seen.add(candidate.card.name)
        merged.append(candidate)
    summary = report.summary
    if report.candidates:
        summary += " Also checked top Moxfield lists for commander-specific staples."
    else:
        summary = "Used top Moxfield Camellia-style lists for grounded upgrade candidates."
    return CoachUpgradeReport(
        summary=summary,
        candidates=merged[:16],
        tool_call_count=report.tool_call_count,
    )


async def _moxfield_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    cuts: CoachCutReport,
) -> list[CoachUpgradeCandidate]:
    payload = await moxfield_recs_service.get_or_refresh(pool, deck.commander_id)
    scores = await moxfield_recs_service.score_inclusion(
        pool,
        payload,
        deck.commander_color_identity,
    )
    if not scores:
        return []
    top_deck_candidates = await _top_deck_missing_candidates(pool, deck, payload, cuts)
    deck_card_ids = {card.card_id for card in deck.cards}
    candidate_ids = [card_id for card_id in scores if card_id not in deck_card_ids]
    if not candidate_ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT scryfall_id, name, mana_cost, cmc, type_line, oracle_text,
                   color_identity, tags,
                   ROUND((prices->>'eur')::numeric * 100)::integer AS price_eur_cents,
                   id
            FROM cards
            WHERE id = ANY($1::uuid[])
            """,
            candidate_ids,
        )
    rows = sorted(rows, key=lambda row: _moxfield_rank(row, scores, identity), reverse=True)
    cut_names = [candidate.card_name for candidate in cuts.candidates[:8]]
    aggregate = [_candidate_from_row(row, scores[row["id"]], cut_names) for row in rows[:12]]
    return [*top_deck_candidates, *aggregate]


async def _top_deck_missing_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    payload: dict[str, Any],
    cuts: CoachCutReport,
) -> list[CoachUpgradeCandidate]:
    """Return cards missing from the most-liked Moxfield list for this commander."""
    deck_id = _top_payload_deck_id(payload)
    if not deck_id:
        return []
    oracle_order = await _top_deck_oracle_order(deck_id)
    if not oracle_order:
        return []
    deck_oracles = await _deck_oracle_ids(pool, deck)
    missing = [oracle_id for oracle_id in oracle_order if oracle_id not in deck_oracles]
    rows = await _rows_by_oracle(pool, missing, deck.commander_color_identity)
    return _top_deck_candidates_from_rows(missing, rows, cuts)


def _top_payload_deck_id(payload: dict[str, Any]) -> str | None:
    decks = payload.get("decks") or []
    if not decks:
        return None
    deck_id = decks[0].get("id")
    return deck_id if isinstance(deck_id, str) else None


async def _top_deck_oracle_order(deck_id: str) -> list[str]:
    try:
        async with CurlAsyncSession(impersonate="chrome", timeout=30) as client:
            entries = await moxfield_recs_service.fetch_deck_card_entries(deck_id, client=client)
        async with httpx.AsyncClient(timeout=30) as client:
            mapping = await moxfield_recs_service._resolve_oracle_ids(
                [entry["scryfall_id"] for entry in entries],
                client=client,
            )
    except Exception:  # noqa: BLE001 - aggregate Moxfield candidates still work
        _log.exception("Failed to fetch top Moxfield deck candidates")
        return []
    oracle_order: list[str] = []
    for entry in entries:
        oracle_id = mapping.get(entry["scryfall_id"].lower())
        if oracle_id and oracle_id not in oracle_order:
            oracle_order.append(oracle_id)
    return oracle_order


def _top_deck_candidates_from_rows(
    missing: list[str],
    rows: list[asyncpg.Record],
    cuts: CoachCutReport,
) -> list[CoachUpgradeCandidate]:
    by_oracle = {str(row["oracle_id"]).lower(): row for row in rows}
    cut_names = [candidate.card_name for candidate in cuts.candidates[:8]]
    out = []
    for oracle_id in missing:
        row = by_oracle.get(oracle_id)
        if row is not None:
            out.append(_top_deck_candidate_from_row(row, cut_names))
    return out[:12]


async def _deck_oracle_ids(pool: asyncpg.Pool, deck: DeckDetailResponse) -> set[str]:
    ids = [card.card_id for card in deck.cards]
    if not ids:
        return set()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT oracle_id::text AS oid FROM cards WHERE id = ANY($1::uuid[])",
            ids,
        )
    return {row["oid"].lower() for row in rows}


async def _rows_by_oracle(
    pool: asyncpg.Pool,
    oracle_ids: list[str],
    color_identity: list[str],
) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT scryfall_id, oracle_id, name, mana_cost, cmc, type_line, oracle_text,
                   color_identity, tags,
                   ROUND((prices->>'eur')::numeric * 100)::integer AS price_eur_cents,
                   id
            FROM cards
            WHERE oracle_id::text = ANY($1::text[])
              AND color_identity <@ $2::text[]
              AND legalities->>'commander' = 'legal'
            """,
            oracle_ids,
            color_identity,
        )


def _top_deck_candidate_from_row(
    row: asyncpg.Record,
    cut_names: list[str],
) -> CoachUpgradeCandidate:
    candidate = _candidate_from_row(row, 1.0, cut_names)
    candidate.reason = "Missing from the most-liked Moxfield list for this commander."
    candidate.role = "top_moxfield_deck_restore"
    return candidate


def _moxfield_rank(
    row: asyncpg.Record,
    scores: dict[object, float],
    identity: DeckIdentityReport,
) -> tuple[float, int, float]:
    text = " ".join(
        [
            row["name"] or "",
            row["type_line"] or "",
            row["oracle_text"] or "",
            " ".join(row["tags"] or []),
        ]
    ).lower()
    identity_terms = set(" ".join(identity.must_preserve_themes).replace("_", " ").split())
    overlap = sum(1 for term in identity_terms if term and term in text)
    cmc = float(row["cmc"] or 0)
    return (scores[row["id"]], overlap, -cmc)


def _candidate_from_row(
    row: asyncpg.Record,
    score: float,
    cut_names: list[str],
) -> CoachUpgradeCandidate:
    card = CardSearchHit(
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=float(row["cmc"]) if row["cmc"] is not None else None,
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        color_identity=list(row["color_identity"] or []),
        tags=list(row["tags"] or []),
        price_eur_cents=row["price_eur_cents"],
    )
    percent = round(score * 100)
    return CoachUpgradeCandidate(
        card=card,
        reason=f"Appears in about {percent}% of top Moxfield lists for this commander.",
        role="commander_popular_upgrade",
        replaces=cut_names[:1],
    )
