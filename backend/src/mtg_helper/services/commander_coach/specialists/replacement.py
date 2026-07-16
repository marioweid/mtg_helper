"""Targeted replacement specialist for one card in a Commander deck."""

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
    ReplacementOption,
    TargetedReplacementResponse,
)
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.services.agents._model import google_model_settings, make_google_model
from mtg_helper.services.card_search_tool import search_cards
from mtg_helper.services.commander_coach.replacement_candidate_service import (
    ReplacementCandidate,
    get_replacement_candidates,
)

_log = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 8
_REQUEST_LIMIT = _MAX_TOOL_CALLS + 3
_WALL_CLOCK_SECONDS = 45.0
_TEMPERATURE = 0.25
_MAX_OUTPUT_TOKENS = 4096

_SYSTEM_PROMPT = """You are a targeted Commander card replacement specialist.
The user wants advice about replacing exactly one card already in the deck.
Do not doctor the whole deck. Do not suggest broad packages.

Your job:
1. Understand the target card's current role from oracle text, type, categories,
   tags, commander, theme, and Coach memory.
2. Search for grounded alternatives with `card_search` before recommending.
3. Consider two replacement lanes:
   - Direct replacements: cards that do the same job better or more efficiently.
   - Slot-fit replacements: cards that may not be 1:1, but fit the same deck slot
     by improving the commander/theme/game plan, adding board presence, ETB/LTB
     value, resilience, recursion, draw, or other flexible Commander utility.
4. Return 3-5 options unless the card should likely be kept.
5. Include a clear best pick when possible.
6. Explain tradeoffs. If replacing changes role, say so explicitly and explain
   why the slot-fit upside is worth considering.
7. Respect deck color identity, current deck contents, theme, and memory.
8. Only suggest exact cards returned by tools.

Do not get trapped looking only for a clone of the target card. A great answer
can be: "I don't love a direct replacement, but this card fits the slot better
because it advances your theme while providing useful Commander flexibility."
Prefer same-role or role-upgrade replacements when they are clearly good, but
include strong theme-upgrade or role-change options when they are better fits for
this deck. If the target is already excellent, say to keep it and give only niche
alternatives.
"""


@dataclass
class ReplacementDeps:
    """Per-run state for targeted replacement."""

    pool: asyncpg.Pool
    deck: DeckDetailResponse
    target: DeckCardItem
    deck_color_identity: list[str]
    deck_card_names: list[str] = field(default_factory=list)
    tool_call_count: list[int] = field(default_factory=lambda: [0])


def _deck_colors(deck: DeckDetailResponse) -> list[str]:
    return [c for c in (deck.commander_color_identity or []) if c in {"W", "U", "B", "R", "G"}]


def _find_target(deck: DeckDetailResponse, target_card_name: str) -> DeckCardItem | None:
    wanted = target_card_name.strip().lower()
    for card in deck.cards:
        if card.name.lower() == wanted:
            return card
    for card in deck.cards:
        if wanted in card.name.lower() or card.name.lower() in wanted:
            return card
    return None


def _card_tags(card: DeckCardItem) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tag in [*(card.tags or []), *(card.categories or []), *(card.qualifying_stages or [])]:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _snippet(text: str | None, limit: int = 360) -> str | None:
    if not text:
        return None
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _candidate_rows(candidates: list[ReplacementCandidate]) -> list[dict[str, Any]]:
    return [
        {
            "lane": candidate.lane,
            "score": round(candidate.score, 2),
            "signals": candidate.signals,
            "card": candidate.card.model_dump(mode="json"),
        }
        for candidate in candidates
    ]


def _brief_payload(
    deck: DeckDetailResponse,
    target: DeckCardItem,
    memory: str | None,
    candidates: list[ReplacementCandidate],
) -> dict[str, Any]:
    commander = deck.commander_card
    return {
        "target_card": {
            "name": target.name,
            "mana_cost": target.mana_cost,
            "cmc": float(target.cmc) if target.cmc is not None else None,
            "type_line": target.type_line,
            "oracle_text": _snippet(target.oracle_text),
            "categories": list(target.categories or []),
            "tags": _card_tags(target),
        },
        "deck": {
            "name": deck.name,
            "commander": commander.model_dump() if commander else None,
            "partner": deck.partner_card.model_dump() if deck.partner_card else None,
            "bracket": deck.bracket,
            "archetype_tags": list(deck.archetype_tags or []),
            "coach_memory_notes": memory or "",
            "card_names": [card.name for card in deck.cards],
        },
        "curated_candidates": _candidate_rows(candidates),
    }


def _hit_from_deck_card(card: DeckCardItem) -> CardSearchHit:
    return CardSearchHit(
        scryfall_id=card.scryfall_id,
        name=card.name,
        mana_cost=card.mana_cost,
        cmc=float(card.cmc) if card.cmc is not None else None,
        type_line=card.type_line,
        oracle_text=card.oracle_text,
        color_identity=list(card.color_identity or []),
        tags=_card_tags(card),
        price_eur_cents=card.price_eur_cents,
    )


def _build_agent() -> Agent[ReplacementDeps, TargetedReplacementResponse]:
    agent = Agent[ReplacementDeps, TargetedReplacementResponse](
        model=make_google_model(),
        deps_type=ReplacementDeps,
        output_type=TargetedReplacementResponse,
        system_prompt=_SYSTEM_PROMPT,
        model_settings=google_model_settings(
            max_tokens=_MAX_OUTPUT_TOKENS,
            temperature=_TEMPERATURE,
            thinking="low",
        ),
        retries=1,
    )

    @agent.tool
    async def card_search(
        ctx: RunContext[ReplacementDeps],
        inp: CardSearchInput,
    ) -> list[CardSearchHit]:
        """Search legal replacement candidates for the target card's role."""
        ctx.deps.tool_call_count[0] += 1
        started = time.monotonic()
        hits = await search_cards(
            ctx.deps.pool,
            deck_color_identity=ctx.deps.deck_color_identity,
            inp=inp,
            exclude_names=ctx.deps.deck_card_names,
        )
        _log.info(
            "replacement card_search #%d returned %d hits in %.2fs for %s",
            ctx.deps.tool_call_count[0],
            len(hits),
            time.monotonic() - started,
            ctx.deps.target.name,
        )
        return hits

    return agent


_AGENT: Agent[ReplacementDeps, TargetedReplacementResponse] | None = None


def _get_agent() -> Agent[ReplacementDeps, TargetedReplacementResponse]:
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


def _not_found_response(target_card_name: str) -> TargetedReplacementResponse:
    return TargetedReplacementResponse(
        target_card_name=target_card_name,
        summary=f"I couldn't find {target_card_name} in this deck, so I can't replace it yet.",
        keep_reason=None,
        best_pick=None,
        options=[],
        tool_call_count=0,
    )


def _fallback_response(target: DeckCardItem, message: str) -> TargetedReplacementResponse:
    return TargetedReplacementResponse(
        target_card_name=target.name,
        summary=message,
        keep_reason="I could not complete a grounded replacement search right now.",
        best_pick=None,
        options=[],
        tool_call_count=0,
    )


async def recommend_replacements(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    target_card_name: str,
    coach_memory_notes: str | None = None,
    complaint: str | None = None,
) -> TargetedReplacementResponse:
    """Recommend focused replacements for one card in the deck."""
    target = _find_target(deck, target_card_name)
    if target is None:
        return _not_found_response(target_card_name)
    deps = ReplacementDeps(
        pool=pool,
        deck=deck,
        target=target,
        deck_color_identity=_deck_colors(deck),
        deck_card_names=[card.name for card in deck.cards],
    )
    candidates = await get_replacement_candidates(pool, deck, target, complaint or target_card_name)
    payload = json.dumps(_brief_payload(deck, target, coach_memory_notes, candidates), default=str)
    try:
        result = await asyncio.wait_for(
            _get_agent().run(
                        "Recommend replacements for the target card only. First consider the "
                "curated_candidates list, which already mixes direct replacements, "
                "theme upgrades, and flexible utility slot-fits. Use card_search only "
                "if the curated candidates are missing an obvious lane.\n"
                + payload,
                deps=deps,
                usage_limits=UsageLimits(request_limit=_REQUEST_LIMIT),
            ),
            timeout=_WALL_CLOCK_SECONDS,
        )
    except UsageLimitExceeded:
        _log.warning("Replacement specialist hit usage limit")
        return _fallback_response(target, "Replacement specialist hit its tool budget.")
    except TimeoutError:
        _log.warning("Replacement specialist timed out")
        return _fallback_response(target, "Replacement specialist timed out.")
    output = result.output
    output.target_card_name = target.name
    output.tool_call_count = deps.tool_call_count[0]
    if output.best_pick is None and output.options:
        output.best_pick = output.options[0].card
    # If model accidentally returns the target as an option, drop it.
    output.options = [opt for opt in output.options if opt.card.name.lower() != target.name.lower()]
    return output


__all__ = ["recommend_replacements"]
