"""Upgrade finder specialist for the Commander Coach pipeline."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import asyncpg
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
from mtg_helper.services.agents._model import make_google_model
from mtg_helper.services.card_search_tool import search_cards
from mtg_helper.services.commander_coach import pipeline

_log = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 10
_REQUEST_LIMIT = _MAX_TOOL_CALLS + 3
_TIMEOUT_SECONDS = 55.0
_MIN_CANDIDATES = 8
_SYSTEM_PROMPT = """You are the Upgrade Finder Agent for a Commander deck coach.
Find strong, generally good cards to add, constrained by identity, mana, curve,
cuts, bracket, and current deck contents.

Rules:
- Use card_search before recommending additions.
- Only recommend exact cards returned by card_search.
- Prefer cards that solve needs from identity/mana/curve/cuts.
- Respect commander color identity; the tool enforces this.
- Avoid cards already in the deck; the tool enforces this except basic lands.
- For each upgrade, state the role and likely cut(s) it replaces.
- Do not use Moxfield, EDHREC top-deck lists, or any decklist-copying source.
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
    """Run the tool-using upgrade specialist, with non-decklist fallback searches."""
    deps = UpgradeDeps(
        pool=pool,
        deck=deck,
        deck_color_identity=pipeline.deck_colors(deck),
        deck_card_names=[card.name for card in deck.cards],
    )
    try:
        report = await _run_agent(deps, deck, identity, mana, curve, cuts)
    except (UsageLimitExceeded, TimeoutError):
        _log.warning("Upgrade Finder Agent exceeded limits")
        report = CoachUpgradeReport(summary="Upgrade agent exceeded limits.")
    except Exception:  # noqa: BLE001 - Coach should still return grounded search results
        _log.exception("Upgrade Finder Agent failed")
        report = CoachUpgradeReport(summary="Upgrade agent failed; using grounded search.")
    return await _with_general_search_candidates(pool, deck, identity, cuts, report)


async def _run_agent(
    deps: UpgradeDeps,
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    mana: CoachManaReport,
    curve: CoachCurveReport,
    cuts: CoachCutReport,
) -> CoachUpgradeReport:
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
    return _filter_report(deck, report)


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


async def _with_general_search_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    cuts: CoachCutReport,
    report: CoachUpgradeReport,
) -> CoachUpgradeReport:
    """Add local-card-search candidates without using external decklists."""
    if len(report.candidates) >= _MIN_CANDIDATES:
        return report
    candidates = await _general_search_candidates(pool, deck, identity, cuts)
    merged = _merge_candidates(deck, report.candidates, candidates)
    if not candidates:
        return report
    summary = report.summary
    summary += " Added local card-search candidates based on deck identity, not Moxfield."
    return CoachUpgradeReport(
        summary=summary.strip(),
        candidates=merged[:12],
        tool_call_count=report.tool_call_count,
    )


async def _general_search_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    cuts: CoachCutReport,
) -> list[CoachUpgradeCandidate]:
    queries = _identity_queries(identity, deck)
    out: list[CoachUpgradeCandidate] = []
    seen: set[str] = set()
    for query, role in queries:
        hits = await search_cards(
            pool,
            deck_color_identity=pipeline.deck_colors(deck),
            inp=CardSearchInput(text_query=query, max_cmc=6, limit=6),
            exclude_names=[card.name for card in deck.cards],
        )
        out.extend(_hits_to_candidates(hits, role, cuts, seen))
        if len(out) >= 12:
            break
    return out


def _identity_queries(
    identity: DeckIdentityReport,
    deck: DeckDetailResponse,
) -> list[tuple[str, str]]:
    text = " ".join(
        [
            identity.archetype,
            identity.main_plan,
            " ".join(identity.must_preserve_themes),
            " ".join(deck.archetype_tags or []),
        ]
    ).lower()
    if "x" in text and ("hydra" in text or "zaxara" in text):
        return [
            ("X spell hydra", "x_spell_payoff"),
            ("mana value X draw", "x_spell_card_advantage"),
            ("counter hydra", "hydra_scaling"),
            ("untap add mana", "commander_mana_engine"),
        ]
    if {"food", "squirrel", "aristocrat", "sacrifice"} & set(text.split()):
        return [
            ("Food token sacrifice", "food_engine"),
            ("Squirrel token", "squirrel_engine"),
            ("creature dies drain", "aristocrats_payoff"),
            ("sacrifice draw", "sacrifice_value"),
        ]
    return [
        (identity.archetype, "theme_upgrade"),
        (identity.main_plan, "plan_upgrade"),
        ("card draw ramp removal", "generic_commander_role"),
    ]


def _hits_to_candidates(
    hits: list[CardSearchHit],
    role: str,
    cuts: CoachCutReport,
    seen: set[str],
) -> list[CoachUpgradeCandidate]:
    cut_names = [candidate.card_name for candidate in cuts.candidates[:4]]
    out: list[CoachUpgradeCandidate] = []
    for hit in hits:
        if hit.name in seen:
            continue
        seen.add(hit.name)
        out.append(
            CoachUpgradeCandidate(
                card=hit,
                reason=_search_reason(hit, role),
                role=role,
                replaces=cut_names[:1],
            )
        )
    return out


def _merge_candidates(
    deck: DeckDetailResponse,
    first: list[CoachUpgradeCandidate],
    second: list[CoachUpgradeCandidate],
) -> list[CoachUpgradeCandidate]:
    seen = {card.name for card in deck.cards}
    merged: list[CoachUpgradeCandidate] = []
    for candidate in [*first, *second]:
        if candidate.card.name in seen:
            continue
        seen.add(candidate.card.name)
        merged.append(candidate)
    return merged


def _search_reason(hit: CardSearchHit, role: str) -> str:
    text = hit.oracle_text or hit.type_line or ""
    snippet = " ".join(text.split())[:180]
    return f"Fits the {role.replace('_', ' ')} role from local card search. {snippet}"
