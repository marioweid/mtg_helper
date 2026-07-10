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
    CoachRoleBudgetReport,
    CoachSignalReport,
    CoachSynergyReport,
    CoachUpgradeCandidate,
    CoachUpgradeReport,
    DeckIdentityReport,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.agents._model import make_google_model
from mtg_helper.services.card_search_tool import search_cards
from mtg_helper.services.commander_coach import pipeline, signal_lanes, synergy_scoring

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
- Do not use top-deck lists or any decklist-copying source.
- For casual Bracket 2-3 decks, avoid pushing into tutor/combo/staple soup unless requested.
- Prefer cards that connect to core signal lanes or repair thin lanes.
- Return a diverse package mix: do not fill every candidate slot from one lane.
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
    roles: CoachRoleBudgetReport | None = None,
    synergy: CoachSynergyReport | None = None,
    signals: CoachSignalReport | None = None,
) -> CoachUpgradeReport:
    """Run the tool-using upgrade specialist, with non-decklist fallback searches."""
    signals = signals or signal_lanes.analyze_signals(deck, roles=roles, synergy=synergy)
    deps = UpgradeDeps(
        pool=pool,
        deck=deck,
        deck_color_identity=pipeline.deck_colors(deck),
        deck_card_names=_existing_names(deck),
    )
    try:
        report = await _run_agent(deps, deck, identity, mana, curve, cuts, roles, synergy, signals)
    except (UsageLimitExceeded, TimeoutError):
        _log.warning("Upgrade Finder Agent exceeded limits")
        report = CoachUpgradeReport(summary="Upgrade agent exceeded limits.")
    except Exception:  # noqa: BLE001 - Coach should still return grounded search results
        _log.exception("Upgrade Finder Agent failed")
        report = CoachUpgradeReport(summary="Upgrade agent failed; using grounded search.")
    return await _with_general_search_candidates(
        pool, deck, identity, cuts, report, roles, synergy, signals
    )


async def _run_agent(
    deps: UpgradeDeps,
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    mana: CoachManaReport,
    curve: CoachCurveReport,
    cuts: CoachCutReport,
    roles: CoachRoleBudgetReport | None,
    synergy: CoachSynergyReport | None,
    signals: CoachSignalReport,
) -> CoachUpgradeReport:
    result = await asyncio.wait_for(
        _get_agent().run(
            json.dumps(
                _payload(deck, identity, mana, curve, cuts, roles, synergy, signals),
                default=str,
            ),
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
    roles: CoachRoleBudgetReport | None,
    synergy: CoachSynergyReport | None,
    signals: CoachSignalReport,
) -> dict[str, Any]:
    return {
        "identity": identity.model_dump(),
        "mana_report": mana.model_dump(),
        "curve_report": curve.model_dump(),
        "cut_report": cuts.model_dump(),
        "deck_bracket": deck.bracket,
        "archetype_tags": list(deck.archetype_tags or []),
        "role_budget": roles.model_dump() if roles else None,
        "synergy_report": synergy.model_dump() if synergy else None,
        "signal_lanes": signals.model_dump(),
    }


def _filter_report(deck: DeckDetailResponse, report: CoachUpgradeReport) -> CoachUpgradeReport:
    names = set(_existing_names(deck))
    seen: set[str] = set()
    candidates = []
    for candidate in report.candidates:
        name = candidate.card.name
        if name in names or name in seen or _is_land(candidate.card):
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
    roles: CoachRoleBudgetReport | None,
    synergy: CoachSynergyReport | None,
    signals: CoachSignalReport,
) -> CoachUpgradeReport:
    """Add local-card-search candidates without using external decklists."""
    report = report.model_copy(
        update={"candidates": _govern_candidates(report.candidates, roles, signals)}
    )
    if len(report.candidates) >= _MIN_CANDIDATES:
        return report
    candidates = await _general_search_candidates(
        pool,
        deck,
        identity,
        cuts,
        roles,
        synergy,
        signals,
    )
    merged = _govern_candidates(
        _merge_candidates(deck, candidates, report.candidates),
        roles,
        signals,
    )
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
    roles: CoachRoleBudgetReport | None,
    synergy: CoachSynergyReport | None,
    signals: CoachSignalReport,
) -> list[CoachUpgradeCandidate]:
    scored = await synergy_scoring.discover_scored_upgrades(
        pool,
        deck,
        identity,
        roles,
        synergy,
        limit=16,
    )
    candidates = [_scored_to_candidate(item, cuts) for item in scored]
    if len(candidates) >= 8:
        return candidates
    fallback = await _query_search_candidates(pool, deck, identity, cuts, roles, synergy, signals)
    return _merge_candidate_lists(candidates, fallback)


async def _query_search_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    cuts: CoachCutReport,
    roles: CoachRoleBudgetReport | None,
    synergy: CoachSynergyReport | None,
    signals: CoachSignalReport,
) -> list[CoachUpgradeCandidate]:
    queries = _identity_queries(identity, deck, roles, synergy, signals)
    out: list[CoachUpgradeCandidate] = []
    seen: set[str] = set()
    for query, role in queries:
        hits = await search_cards(
            pool,
            deck_color_identity=pipeline.deck_colors(deck),
            inp=CardSearchInput(text_query=query, max_cmc=6, limit=6),
            exclude_names=_existing_names(deck),
        )
        out.extend(_hits_to_candidates(hits, role, cuts, seen))
        if len(out) >= 12:
            break
    return out


def _scored_to_candidate(
    item: synergy_scoring.ScoredUpgrade,
    cuts: CoachCutReport,
) -> CoachUpgradeCandidate:
    cut_names = [candidate.card_name for candidate in cuts.candidates[:4]]
    return CoachUpgradeCandidate(
        card=item.card,
        reason=synergy_scoring.reason_for_score(item),
        role=item.role_matches[0] if item.role_matches else "synergy_upgrade",
        replaces=cut_names[:1],
    )


def _merge_candidate_lists(
    first: list[CoachUpgradeCandidate],
    second: list[CoachUpgradeCandidate],
) -> list[CoachUpgradeCandidate]:
    seen: set[str] = set()
    out: list[CoachUpgradeCandidate] = []
    for candidate in [*first, *second]:
        if candidate.card.name in seen:
            continue
        seen.add(candidate.card.name)
        out.append(candidate)
    return out


def _identity_queries(
    identity: DeckIdentityReport,
    deck: DeckDetailResponse,
    roles: CoachRoleBudgetReport | None,
    synergy: CoachSynergyReport | None,
    signals: CoachSignalReport | None = None,
) -> list[tuple[str, str]]:
    text = " ".join(
        [
            identity.archetype,
            identity.main_plan,
            " ".join(identity.must_preserve_themes),
            " ".join(deck.archetype_tags or []),
        ]
    ).lower()
    weak = set(synergy.weak_packages if synergy else [])
    priority = set(roles.priority_roles if roles else [])
    signal_queries = _signal_queries(signals)
    if "x" in text and ("hydra" in text or "zaxara" in text):
        queries = [
            ("X spell hydra", "x_spell_payoff"),
            ("mana value X draw", "x_spell_card_advantage"),
            ("counter hydra", "hydra_scaling"),
            ("destroy exile removal", "interaction"),
            ("creature draw", "card_advantage"),
        ]
        return _prioritize_queries(signal_queries + queries, weak, priority)
    if {"food", "squirrel", "aristocrat", "sacrifice"} & set(text.split()):
        queries = [
            ("Food token sacrifice", "food_engine"),
            ("Squirrel token", "squirrel_engine"),
            ("creature dies drain", "aristocrats_payoff"),
            ("sacrifice draw", "sacrifice_value"),
            ("destroy exile removal", "interaction"),
        ]
        return _prioritize_queries(signal_queries + queries, weak, priority)
    return _prioritize_queries(
        signal_queries
        + [
            (identity.archetype, "theme_upgrade"),
            (identity.main_plan, "plan_upgrade"),
            ("card draw removal", "generic_commander_role"),
        ],
        weak,
        priority,
    )


def _prioritize_queries(
    queries: list[tuple[str, str]],
    weak_packages: set[str],
    priority_roles: set[str],
) -> list[tuple[str, str]]:
    def score(item: tuple[str, str]) -> int:
        query, role = item
        blob = f"{query} {role}".lower()
        return sum(term in blob for term in weak_packages | priority_roles)

    return sorted(queries, key=score, reverse=True)


def _signal_queries(signals: CoachSignalReport | None) -> list[tuple[str, str]]:
    if signals is None:
        return []
    queries: list[tuple[str, str]] = []
    for lane in signals.lanes:
        if lane.strength == "present":
            continue
        query = " ".join(lane.terms[:3]) or lane.name.replace("_", " ")
        queries.append((query, lane.name))
    return queries[:8]


def _hits_to_candidates(
    hits: list[CardSearchHit],
    role: str,
    cuts: CoachCutReport,
    seen: set[str],
) -> list[CoachUpgradeCandidate]:
    cut_names = [candidate.card_name for candidate in cuts.candidates[:4]]
    out: list[CoachUpgradeCandidate] = []
    for hit in hits:
        if hit.name in seen or _should_skip_hit(hit, role):
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


def _should_skip_hit(hit: CardSearchHit, role: str) -> bool:
    text = " ".join([hit.type_line or "", hit.oracle_text or ""]).lower()
    if _is_land(hit):
        return True
    if role not in {"ramp", "commander_mana_engine"} and "add one mana" in text:
        return True
    return False


def _govern_candidates(
    candidates: list[CoachUpgradeCandidate],
    roles: CoachRoleBudgetReport | None,
    signals: CoachSignalReport | None = None,
) -> list[CoachUpgradeCandidate]:
    ramp_allowed = 0 if roles and "ramp" in roles.blocked_roles else 1
    ramp_seen = 0
    lane_counts: dict[str, int] = {}
    core = set(signals.core_lanes if signals else [])
    out: list[CoachUpgradeCandidate] = []
    for candidate in candidates:
        if _is_land(candidate.card):
            continue
        if _is_ramp(candidate.card):
            if ramp_seen >= ramp_allowed:
                continue
            ramp_seen += 1
        lane = _candidate_lane(candidate, signals)
        max_for_lane = 3 if lane in core else 2
        if lane and lane_counts.get(lane, 0) >= max_for_lane:
            continue
        if lane:
            lane_counts[lane] = lane_counts.get(lane, 0) + 1
        out.append(candidate)
    return out


def _candidate_lane(
    candidate: CoachUpgradeCandidate,
    signals: CoachSignalReport | None,
) -> str | None:
    if signals is None:
        return candidate.role
    text = _card_text(candidate.card)
    for lane in signals.lanes:
        if any(term.lower() in text for term in lane.terms):
            return lane.name
    return candidate.role


def _is_land(card: CardSearchHit) -> bool:
    return "land" in (card.type_line or "").lower()


def _is_ramp(card: CardSearchHit) -> bool:
    text = _card_text(card)
    return "add one mana" in text or "search your library for a land" in text or "ramp" in text


def _card_text(card: CardSearchHit) -> str:
    return " ".join(
        [card.type_line or "", card.oracle_text or "", " ".join(card.tags or [])]
    ).lower()


def _merge_candidates(
    deck: DeckDetailResponse,
    first: list[CoachUpgradeCandidate],
    second: list[CoachUpgradeCandidate],
) -> list[CoachUpgradeCandidate]:
    seen = set(_existing_names(deck))
    merged: list[CoachUpgradeCandidate] = []
    for candidate in [*first, *second]:
        if candidate.card.name in seen:
            continue
        seen.add(candidate.card.name)
        merged.append(candidate)
    return merged


def _existing_names(deck: DeckDetailResponse) -> list[str]:
    names = [card.name for card in deck.cards]
    if deck.commander_card is not None:
        names.append(deck.commander_card.name)
    if deck.partner_card is not None:
        names.append(deck.partner_card.name)
    return names


def _search_reason(hit: CardSearchHit, role: str) -> str:
    text = hit.oracle_text or hit.type_line or ""
    snippet = " ".join(text.split())[:180]
    return f"Fits the {role.replace('_', ' ')} role from local card search. {snippet}"
