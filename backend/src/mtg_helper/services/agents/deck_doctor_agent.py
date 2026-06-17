"""Commander deck doctor agent.

The doctor uses a bounded research loop: inspect a compact deck profile, call
search tools for grounded additions, then return structured cuts/adds/swaps.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import asyncpg
from pydantic_ai import Agent, RunContext, UsageLimitExceeded, UsageLimits

from mtg_helper.models.ai import CardSearchHit, CardSearchInput, DeckDoctorResponse
from mtg_helper.models.decks import DeckDetailResponse, DeckCardItem
from mtg_helper.services.agents._model import make_google_model
from mtg_helper.services.card_search_tool import search_cards
from mtg_helper.services.retrieval_service import card_qualifying_stages

_log = logging.getLogger(__name__)

_MAX_TOOL_CALLS = 14
_REQUEST_LIMIT = _MAX_TOOL_CALLS + 3
_WALL_CLOCK_SECONDS = 75.0
_TEMPERATURE = 0.45
_MAX_OUTPUT_TOKENS = 8192

_SYSTEM_PROMPT = """You are a peak Commander deck doctor for Magic: The Gathering.
Your job is to deeply analyze an existing Commander deck and recommend precise,
evidence-backed improvements. Be opinionated, but never invent cards or facts.

WORKFLOW DISCIPLINE:
1. First inspect the deck profile: commander, bracket, tags, role counts, curve,
   type counts, protected theme-engine cards, and notable cards.
2. Identify the deck's real game plan from the commander first, then the deck tags.
3. Before recommending additions, use `card_search` to find grounded candidates.
4. Use `weak_cards` to inspect low-synergy/off-role cards before naming cuts.
5. Pair cuts and adds only when the roles line up. Do not swap a land for a
   nonland unless the finding is explicitly about land count.
6. Preserve the deck's engine. Theme-engine cards are cuttable, but only when
   the replacement preserves or improves the same engine role.
7. For every cut, read the card's oracle text and give a card-specific reason.
   Do not call a card low-impact unless you can explain why its actual text is
   weak for this commander.
8. Prefer a small number of high-conviction recommendations over a giant list.

COMMANDER FUNDAMENTALS TO CHECK:
- mana base and curve pressure
- ramp/draw/interaction density
- commander synergy first: bad standalone cards may be premium with this commander
- theme density and commander synergy
- win conditions and closing power
- redundancy without dilution
- bracket-appropriate card quality and speed

OUTPUT RULES:
- Summary: 2-4 sentences.
- Game plan: one concise paragraph.
- Findings: concrete issues with evidence from the profile.
- Cuts: only cards in the deck. If cutting a theme-engine card, explain why the
  replacement preserves or upgrades that engine role.
- Adds: only exact cards returned by tools.
- Swaps: strongest practical packages, normally 3-8. Avoid broad multi-cut
  bundles unless each removed card is individually justified.
- Every swap must be validated against the commander text: if the cut card
  enables the commander, the add must preserve or upgrade that interaction.
- If evidence is weak, mark confidence low/medium instead of overstating.
- Do not mention hidden chain-of-thought. Show evidence, not private reasoning."""


@dataclass
class DoctorDeps:
    """Per-run dependencies and bounded mutable tool state."""

    pool: asyncpg.Pool
    deck: DeckDetailResponse
    deck_color_identity: list[str]
    deck_card_names: list[str] = field(default_factory=list)
    tool_call_count: list[int] = field(default_factory=lambda: [0])


def _build_agent() -> Agent[DoctorDeps, DeckDoctorResponse]:
    agent = Agent[DoctorDeps, DeckDoctorResponse](
        model=make_google_model(),
        deps_type=DoctorDeps,
        output_type=DeckDoctorResponse,
        system_prompt=_SYSTEM_PROMPT,
        model_settings={"temperature": _TEMPERATURE, "max_tokens": _MAX_OUTPUT_TOKENS},
        retries=1,
    )

    @agent.tool
    async def card_search(ctx: RunContext[DoctorDeps], inp: CardSearchInput) -> list[CardSearchHit]:
        """Search legal replacement/addition candidates for this deck.

        Results are filtered to commander color identity and exclude cards
        already in the deck except basic lands.
        """
        ctx.deps.tool_call_count[0] += 1
        started = time.monotonic()
        hits = await search_cards(
            ctx.deps.pool,
            deck_color_identity=ctx.deps.deck_color_identity,
            inp=inp,
            exclude_names=ctx.deps.deck_card_names,
        )
        _log.info(
            "doctor card_search #%d returned %d hits in %.2fs (query=%r tags=%s)",
            ctx.deps.tool_call_count[0],
            len(hits),
            time.monotonic() - started,
            inp.text_query,
            inp.tags,
        )
        return hits

    @agent.tool
    async def weak_cards(ctx: RunContext[DoctorDeps], limit: int = 12) -> list[dict[str, Any]]:
        """Return likely cut candidates based on low theme/stage overlap.

        This is a heuristic shortlist, not an instruction to cut every card.
        Use it as evidence together with the deck profile.
        """
        ctx.deps.tool_call_count[0] += 1
        return _weak_card_rows(ctx.deps.deck, max(1, min(limit, 20)))

    return agent


_AGENT: Agent[DoctorDeps, DeckDoctorResponse] | None = None


def _get_agent() -> Agent[DoctorDeps, DeckDoctorResponse]:
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


def _deck_colors(deck: DeckDetailResponse) -> list[str]:
    return [c for c in (deck.commander_color_identity or []) if c in {"W", "U", "B", "R", "G"}]


def _card_tags(card: DeckCardItem) -> set[str]:
    return set(card.tags or []) | set(card.categories or []) | set(card.qualifying_stages or [])


def _protected_tag_set(deck: DeckDetailResponse) -> set[str]:
    tags = set(deck.archetype_tags or [])
    protected: set[str] = set(tags)
    if "food_matters" in tags:
        protected.update({"food_matters", "food", "token", "sacrifice"})
    if "squirrel_tribal" in tags:
        protected.update({"squirrel", "token", "anthem"})
    if "aristocrats" in tags or "sacrifice" in tags:
        protected.update({"aristocrats", "sacrifice", "token", "graveyard"})
    if "treasure_matters" in tags:
        protected.update({"treasure_matters", "treasure", "token", "ramp"})
    if "clue_matters" in tags:
        protected.update({"clue_matters", "clue", "token", "draw"})
    return protected


def _protection_reason(card: DeckCardItem, deck: DeckDetailResponse) -> str | None:
    overlap = _card_tags(card) & _protected_tag_set(deck)
    if not overlap:
        return None
    return "theme engine: " + ", ".join(sorted(overlap)[:4])


def _weak_card_rows(deck: DeckDetailResponse, limit: int) -> list[dict[str, Any]]:
    deck_tags = set(deck.archetype_tags or [])
    rows: list[tuple[int, dict[str, Any]]] = []
    for card in deck.cards:
        if "Land" in (card.type_line or ""):
            continue
        tags = _card_tags(card)
        role_count = len(card_qualifying_stages(list(card.tags or []), card.type_line))
        theme_overlap = len(tags & deck_tags)
        added_penalty = 1 if card.added_by == "user" else 0
        score = theme_overlap * 3 + role_count + added_penalty
        row = _card_row(card, deck, theme_overlap=theme_overlap, role_count=role_count)
        rows.append((score, row))
    rows.sort(key=lambda item: (item[0], item[1]["cmc"] or 0), reverse=False)
    return [row for _, row in rows[:limit]]


def _snippet(text: str | None, limit: int = 360) -> str | None:
    if not text:
        return None
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _engine_words(text: str | None) -> list[str]:
    if not text:
        return []
    words = {
        word
        for word in text.lower().replace("/", " ").replace(",", " ").split()
        if len(word) >= 3
    }
    return sorted(words)[:60]


def _card_row(
    card: DeckCardItem, deck: DeckDetailResponse, *, theme_overlap: int, role_count: int
) -> dict[str, Any]:
    return {
        "name": card.name,
        "mana_cost": card.mana_cost,
        "cmc": float(card.cmc) if card.cmc is not None else None,
        "type_line": card.type_line,
        "oracle_text": _snippet(card.oracle_text),
        "quantity": card.quantity,
        "categories": list(card.categories or []),
        "tags": list(card.tags or [])[:8],
        "theme_overlap": theme_overlap,
        "role_count": role_count,
        "added_by": card.added_by,
        "theme_engine_role": _protection_reason(card, deck),
    }


def _role_counts(deck: DeckDetailResponse) -> dict[str, int]:
    counts: dict[str, int] = {}
    for card in deck.cards:
        stages = card.categories or card.qualifying_stages or []
        for stage in stages:
            counts[stage] = counts.get(stage, 0) + (card.quantity or 1)
    return counts


def _type_counts(deck: DeckDetailResponse) -> dict[str, int]:
    counts: dict[str, int] = {}
    for card in deck.cards:
        q = card.quantity or 1
        tl = card.type_line or "Unknown"
        key = "Land" if "Land" in tl else tl.split(" — ", maxsplit=1)[0]
        counts[key] = counts.get(key, 0) + q
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _curve(deck: DeckDetailResponse) -> dict[str, int]:
    counts = {str(i): 0 for i in range(7)} | {"7+": 0}
    for card in deck.cards:
        if "Land" in (card.type_line or ""):
            continue
        cmc = int(card.cmc or 0)
        key = "7+" if cmc >= 7 else str(cmc)
        counts[key] += card.quantity or 1
    return counts


def _brief_payload(deck: DeckDetailResponse) -> dict[str, Any]:
    commander = deck.commander_card
    cards = sorted(deck.cards, key=lambda c: (c.cmc or 0, c.name))
    return {
        "commander": commander.model_dump() if commander else None,
        "partner": deck.partner_card.model_dump() if deck.partner_card else None,
        "bracket": deck.bracket,
        "archetype_tags": list(deck.archetype_tags or []),
        "commander_engine_words": _engine_words(commander.oracle_text if commander else None),
        "stage_targets": dict(deck.stage_targets or {}),
        "role_counts": _role_counts(deck),
        "type_counts": _type_counts(deck),
        "mana_curve": _curve(deck),
        "card_count": sum(c.quantity for c in deck.cards),
        "cards": [_card_row(c, deck, theme_overlap=0, role_count=0) for c in cards],
        "protected_cards": [
            {"name": c.name, "reason": reason}
            for c in deck.cards
            if (reason := _protection_reason(c, deck)) is not None
        ],
        "weak_card_shortlist": _weak_card_rows(deck, 12),
    }


def _fallback_response(message: str) -> DeckDoctorResponse:
    return DeckDoctorResponse(
        summary=message,
        game_plan="Unable to complete a grounded deck doctor pass right now.",
        findings=[],
        cuts=[],
        adds=[],
        swaps=[],
        tool_call_count=0,
    )


async def doctor_deck(
    pool: asyncpg.Pool, deck: DeckDetailResponse, validator_feedback: str | None = None
) -> DeckDoctorResponse:
    """Run the Commander deck doctor agent against an existing deck."""
    deps = DoctorDeps(
        pool=pool,
        deck=deck,
        deck_color_identity=_deck_colors(deck),
        deck_card_names=[c.name for c in deck.cards],
    )
    payload = json.dumps(_brief_payload(deck), default=str)
    try:
        instruction = "Doctor this Commander deck. Use tools before recommending additions.\n"
        if validator_feedback:
            instruction += "Validator feedback to obey in this revision:\n"
            instruction += validator_feedback + "\n"
        result = await asyncio.wait_for(
            _get_agent().run(
                instruction + payload,
                deps=deps,
                usage_limits=UsageLimits(request_limit=_REQUEST_LIMIT),
            ),
            timeout=_WALL_CLOCK_SECONDS,
        )
    except UsageLimitExceeded:
        _log.warning("Deck doctor hit usage limit")
        return _fallback_response("Deck doctor hit its tool budget before finishing.")
    except TimeoutError:
        _log.warning("Deck doctor timed out")
        return _fallback_response("Deck doctor timed out before finishing.")
    output = result.output
    output.tool_call_count = deps.tool_call_count[0]
    return output
