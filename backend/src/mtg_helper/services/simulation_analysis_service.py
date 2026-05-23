"""AI agent that diagnoses a goldfish sim run and proposes card swaps.

Built on `pydantic-ai`: a single ``card_search`` tool grounds the model's
recommendations in our card DB, and ``output_type=SimulationAnalysisResponse``
makes the response shape enforced by the framework — no manual JSON parsing
or truncation fallback. Hard caps on requests (tool calls) and wall clock keep
the loop bounded.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import asyncpg
from pydantic_ai import Agent, RunContext, UsageLimitExceeded, UsageLimits
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from mtg_helper.config import settings
from mtg_helper.models.ai import (
    CardSearchHit,
    CardSearchInput,
    SimulationAnalysisResponse,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.models.playtest import PlaytestStats
from mtg_helper.services.card_search_tool import search_cards
from mtg_helper.services.llm_client import LLMClient

_log = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 10
# request_limit counts every model request (initial + each tool round-trip),
# so leave a margin above _MAX_TOOL_CALLS for the final structured response.
_REQUEST_LIMIT = _MAX_TOOL_CALLS + 2
_WALL_CLOCK_SECONDS = 60.0

_TEMPERATURE = 0.55
_MAX_OUTPUT_TOKENS = 8192

_SYSTEM_PROMPT = """You are a high-level Magic: The Gathering Commander deck-building consultant.
You analyze goldfish simulation telemetry. Your job is honest assessment — affirm a
healthy deck instead of inventing problems; flag real issues with the right weight.

--- BASELINE THRESHOLDS ---
A metric is "breached" when it crosses the CRITICAL line.
- Mana Screw (pct_screw): healthy < 10%, breach if > 12%.
- Mana Flood (pct_flood): healthy < 12%, breach if > 15%.
- Color Screw (pct_color_screw): healthy < 8%, breach if > 10%.
- Average Mulligans (avg_mulligans): healthy < 0.9, breach if > 1.1.
- Kept Hand at 7 (kept_at_7): healthy > 50%, breach if < 45%.
- Commander Cast Rate (pct_ever_cast): healthy > 80%, breach if < 60%.

--- SEVERITY DISCIPLINE ---
- `critical`: ONLY when a baseline threshold is breached. Use sparingly.
- `warn`: a metric is between healthy and breach (clear adverse trend but not failing).
- `info`: optional soft observation, e.g. "color X tends to be the missing pip when
  you screw — not actionable yet but worth watching."

--- HEALTHY-DECK BEHAVIOR ---
If NO baseline threshold is breached and no metric is in the warn band:
- Return ZERO findings and ZERO swap_suggestions.
- Write a 1–2 sentence summary that affirms the deck (e.g. "Deck looks solid —
  consistency and mana base are within healthy targets across all tracked
  metrics."). Optionally add ONE soft `info` note if a metric is trending toward
  the warn band, phrased as a watch-out, not a fix-it.

If only minor (warn-band) issues exist:
- Findings allowed at `warn` or `info`. No `critical`.
- Swap_suggestions OPTIONAL — only include if you actually found a concrete,
  better card via `card_search`. Otherwise leave the swap list empty and phrase
  the finding as "you might look into ..." instead of prescribing a swap.

Only when at least one threshold is breached should swap_suggestions be your
primary output.

--- INTERACTION FLOW ---
1. First, evaluate the metrics against the thresholds above. Decide whether the
   deck is healthy, has minor warn-band issues, or has breaches. That decision
   shapes everything else — DO NOT call tools speculatively when the deck is
   healthy.
2. You have access to the `card_search` tool. Use it ONLY when you have an
   actual breach or warn-band issue that calls for a concrete replacement
   candidate. The tool already excludes cards already in the deck (except
   basic lands), so every hit is real.
3. Budget at most ten calls; each call narrows a specific gap. Healthy decks
   should need zero calls.
4. Return the structured response. `summary` is 1–3 sentences (shorter when
   healthy). `findings` lists real issues at the appropriate severity.
   `swap_suggestions` proposes concrete swaps using exact card names from your
   `card_search` results — only when something actually needs swapping."""


@dataclass
class _AnalysisDeps:
    """Per-run dependencies threaded through the agent's tools."""

    pool: asyncpg.Pool
    deck_color_identity: list[str]
    deck_card_names: list[str] = field(default_factory=list)
    tool_call_count: list[int] = field(default_factory=lambda: [0])


def _build_agent() -> Agent[_AnalysisDeps, SimulationAnalysisResponse]:
    """Construct the analysis agent. Re-built per process (cheap) so the API
    key from settings is captured at the time the app boots.
    """
    provider = GoogleProvider(api_key=settings.gemini_api_key)
    model = GoogleModel(settings.chat_model, provider=provider)
    agent = Agent[_AnalysisDeps, SimulationAnalysisResponse](
        model=model,
        deps_type=_AnalysisDeps,
        output_type=SimulationAnalysisResponse,
        system_prompt=_SYSTEM_PROMPT,
        model_settings={
            "temperature": _TEMPERATURE,
            "max_tokens": _MAX_OUTPUT_TOKENS,
        },
        retries=1,
    )

    @agent.tool
    async def card_search(
        ctx: RunContext[_AnalysisDeps], inp: CardSearchInput
    ) -> list[CardSearchHit]:
        """Search the card pool for replacement candidates. Always filtered
        to the deck's color identity AND excludes cards already in the deck
        (basic lands are allowed through). Provide structural filters; up to
        `limit` matching cards are returned.
        """
        ctx.deps.tool_call_count[0] += 1
        call_idx = ctx.deps.tool_call_count[0]
        call_started = time.monotonic()
        hits = await search_cards(
            ctx.deps.pool,
            deck_color_identity=ctx.deps.deck_color_identity,
            inp=inp,
            exclude_names=ctx.deps.deck_card_names,
        )
        _log.info(
            "card_search #%d returned %d hits in %.2fs (query=%r tags=%s)",
            call_idx,
            len(hits),
            time.monotonic() - call_started,
            inp.text_query,
            inp.tags,
        )
        return hits

    return agent


_AGENT: Agent[_AnalysisDeps, SimulationAnalysisResponse] | None = None


def _get_agent() -> Agent[_AnalysisDeps, SimulationAnalysisResponse]:
    """Lazy singleton — building the provider eagerly at import time fails
    when settings.gemini_api_key is unset (test env).
    """
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


def _deck_colors(deck: DeckDetailResponse) -> list[str]:
    return [c for c in (deck.commander_color_identity or []) if c in {"W", "U", "B", "R", "G"}]


def _brief_payload(deck: DeckDetailResponse, stats: PlaytestStats) -> dict[str, Any]:
    """Compact JSON view of the deck + sim for the model."""
    commander = deck.commander_card
    deck_view = {
        "commander": commander.name if commander else None,
        "commander_cost": commander.mana_cost if commander else None,
        "commander_colors": list(deck.commander_color_identity or []),
        "partner": deck.partner_card.name if deck.partner_card else None,
        "bracket": deck.bracket,
        "archetype_tags": list(deck.archetype_tags or []),
        "max_price_cents": deck.max_price_cents,
        "card_count": sum(c.quantity for c in deck.cards),
        "land_count": sum(c.quantity for c in deck.cards if "Land" in (c.type_line or "")),
    }
    return {
        "deck": deck_view,
        "sim": _stats_summary(stats),
    }


def _stats_summary(stats: PlaytestStats) -> dict[str, Any]:
    return {
        "trials": stats.trials,
        "turns": stats.turns,
        "consistency": {
            "avg_mulligans": round(stats.avg_mulligans, 2),
            "pct_flood": round(stats.pct_flood, 3),
            "pct_screw": round(stats.pct_screw, 3),
            "pct_color_screw": round(stats.color_screw.pct_color_screw, 3),
            "color_shortages": stats.color_screw.shortages_by_color,
            "avg_first_missed_land_turn": round(stats.avg_first_missed_land_turn, 2),
            "kept_at_7": round(stats.opening_hand.pct_kept_7, 3),
        },
        "mulligan_reasons": stats.mulligan_reasons.model_dump(),
        "commander": stats.commander.model_dump() if stats.commander else None,
        "partner": stats.partner.model_dump() if stats.partner else None,
        "cast_rate_by_cmc": stats.cast_rate_by_cmc,
        "top_stuck_cards": [s.model_dump() for s in stats.top_stuck_cards],
        "unpaid_costs": [u.model_dump() for u in stats.unpaid_cost_summary],
        "per_turn_snapshot": [_turn_snapshot(t) for t in stats.per_turn],
        "sample_trials": [s.model_dump() for s in stats.sample_trials],
    }


def _turn_snapshot(turn: Any) -> dict[str, float | int]:
    return {
        "turn": turn.turn,
        "lands": round(turn.avg_lands_in_play, 2),
        "mana": round(turn.avg_mana_available, 2),
        "spent": round(turn.avg_mana_spent, 2),
        "unspent": round(turn.avg_mana_unspent, 2),
        "dead": round(turn.avg_dead_cards, 2),
        "color_dead": round(turn.avg_color_dead_cards, 2),
        "hand": round(turn.avg_cards_in_hand, 2),
    }


def _build_prompt(deck: DeckDetailResponse, stats: PlaytestStats) -> str:
    payload = _brief_payload(deck, stats)
    return "Analyze this deck and simulation. Respond with the structured output.\n\n" + json.dumps(
        payload, indent=2, default=str
    )


# Critical thresholds — must match the numbers in _SYSTEM_PROMPT.
def _critical_breaches(stats: PlaytestStats) -> list[str]:
    breaches: list[str] = []
    if stats.pct_screw > 0.12:
        breaches.append("pct_screw")
    if stats.pct_flood > 0.15:
        breaches.append("pct_flood")
    if stats.color_screw.pct_color_screw > 0.10:
        breaches.append("pct_color_screw")
    if stats.avg_mulligans > 1.1:
        breaches.append("avg_mulligans")
    if stats.opening_hand.pct_kept_7 < 0.45:
        breaches.append("kept_at_7")
    if stats.commander is not None and stats.commander.pct_ever_cast < 0.60:
        breaches.append("commander_cast_rate")
    return breaches


def _enforce_severity_floor(
    output: SimulationAnalysisResponse, stats: PlaytestStats
) -> SimulationAnalysisResponse:
    """Belt-and-suspenders post-filter. The agent is instructed to stay quiet on
    a healthy deck; this guarantees it. If no critical threshold is breached we
    drop fabricated `critical` findings and clear swap_suggestions — soft `warn`
    and `info` notes are kept as hints.
    """
    breaches = _critical_breaches(stats)
    if breaches:
        return output
    cleaned = [f for f in output.findings if f.severity != "critical"]
    if len(cleaned) != len(output.findings) or output.swap_suggestions:
        _log.info(
            "analysis post-filter: no critical breaches — dropped %d critical "
            "findings and %d swap_suggestions",
            len(output.findings) - len(cleaned),
            len(output.swap_suggestions),
        )
    output.findings = cleaned
    output.swap_suggestions = []
    return output


async def analyze_simulation(
    pool: asyncpg.Pool,
    ai_client: LLMClient,  # noqa: ARG001 — kept for caller compatibility
    deck: DeckDetailResponse,
    stats: PlaytestStats,
) -> SimulationAnalysisResponse:
    """Drive the analysis agent. Returns a structured response — may include
    a partial summary if the loop hit the request cap or wall-clock timeout.
    """
    agent = _get_agent()
    deck_card_names = sorted({c.name for c in deck.cards})
    deps = _AnalysisDeps(
        pool=pool,
        deck_color_identity=_deck_colors(deck),
        deck_card_names=deck_card_names,
    )
    prompt = _build_prompt(deck, stats)
    started = time.monotonic()
    _log.info(
        "analysis start: deck=%s cards=%d colors=%s",
        deck.name,
        len(deck_card_names),
        deps.deck_color_identity,
    )
    try:
        result = await asyncio.wait_for(
            agent.run(prompt, deps=deps, usage_limits=UsageLimits(request_limit=_REQUEST_LIMIT)),
            timeout=_WALL_CLOCK_SECONDS,
        )
    except TimeoutError:
        elapsed = time.monotonic() - started
        calls = deps.tool_call_count[0]
        _log.warning("analysis wall-clock timeout: %.1fs elapsed, %d tool calls", elapsed, calls)
        plural = "s" if calls != 1 else ""
        return SimulationAnalysisResponse(
            summary=(
                f"Analysis timed out after {elapsed:.0f}s and {calls} tool "
                f"call{plural}. The agent was still searching when the "
                f"{_WALL_CLOCK_SECONDS:.0f}s cap was reached — try again with "
                "a smaller deck change or a narrower question."
            ),
            tool_call_count=calls,
        )
    except UsageLimitExceeded as exc:
        calls = deps.tool_call_count[0]
        _log.warning("analysis usage cap hit: %s (%d tool calls)", exc, calls)
        return SimulationAnalysisResponse(
            summary=(
                f"Analysis exceeded the tool-call budget ({calls} calls) "
                "before finalizing. The agent kept searching instead of "
                "settling on a recommendation."
            ),
            tool_call_count=calls,
        )
    elapsed = time.monotonic() - started
    output = result.output
    output.tool_call_count = deps.tool_call_count[0]
    output = _enforce_severity_floor(output, stats)
    _log.info(
        "analysis done: %.1fs, %d tool calls, %d findings, %d swaps",
        elapsed,
        output.tool_call_count,
        len(output.findings),
        len(output.swap_suggestions),
    )
    return output
