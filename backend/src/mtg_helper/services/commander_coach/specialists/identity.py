"""Deck identity specialist for the Commander Coach pipeline."""

import asyncio
import json
import logging
from dataclasses import dataclass

from pydantic_ai import Agent

from mtg_helper.models.ai import DeckIdentityReport
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.agents._model import (
    fast_google_model_settings,
    make_fast_google_model,
)
from mtg_helper.services.commander_coach import pipeline, signal_lanes

_log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 25.0
_SYSTEM_PROMPT = """You are the Deck Identity Agent for a Commander deck coach.
Answer one question: what is this deck actually trying to do?

Use commander text first, then deterministic signal lanes, deck tags, role
budgets, memory, and notable cards. Be specific: prefer "Golgari Food Squirrel
Aristocrats" over "midrange".

Output discipline:
- Do not recommend cards.
- Do not list cuts.
- Preserve core signal lanes and user memory.
- Identify tensions later agents should solve.
- If a lane is thin, name it as a tension instead of inventing a new archetype.
"""


@dataclass(frozen=True)
class IdentityDeps:
    """Dependencies for the identity specialist."""

    deck: DeckDetailResponse


def _build_agent() -> Agent[IdentityDeps, DeckIdentityReport]:
    return Agent[IdentityDeps, DeckIdentityReport](
        model=make_fast_google_model(),
        deps_type=IdentityDeps,
        output_type=DeckIdentityReport,
        system_prompt=_SYSTEM_PROMPT,
        model_settings=fast_google_model_settings(max_tokens=1024, temperature=0.2, thinking="low"),
        retries=1,
    )


_AGENT: Agent[IdentityDeps, DeckIdentityReport] | None = None


def _get_agent() -> Agent[IdentityDeps, DeckIdentityReport]:
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


async def identify_deck(
    deck: DeckDetailResponse,
    *,
    coach_memory_notes: str | None = None,
    user_goal: str = "",
    signals: object | None = None,
) -> DeckIdentityReport:
    """Run the identity specialist, falling back to tags if the LLM fails."""
    signal_report = signals or signal_lanes.analyze_signals(deck, memory=coach_memory_notes)
    payload = _payload(deck, coach_memory_notes, user_goal, signal_report)
    try:
        result = await asyncio.wait_for(
            _get_agent().run(json.dumps(payload, default=str), deps=IdentityDeps(deck)),
            timeout=_TIMEOUT_SECONDS,
        )
        return result.output
    except Exception:  # noqa: BLE001 - Coach should degrade gracefully
        _log.exception("Deck Identity Agent failed")
        return fallback_identity(deck)


def fallback_identity(deck: DeckDetailResponse) -> DeckIdentityReport:
    """Derive a conservative identity from existing deck metadata."""
    tags = list(deck.archetype_tags or [])
    commander = deck.commander_card.name if deck.commander_card else "the commander"
    archetype = _archetype_from_tags(tags) or f"{commander} Commander"
    main_plan = f"Use {commander} to execute the deck's tagged themes."
    if tags:
        main_plan = f"Use {commander} to pressure the table through {', '.join(tags[:4])}."
    return DeckIdentityReport(
        archetype=archetype,
        main_plan=main_plan,
        secondary_plan=None,
        power_target=f"Bracket {deck.bracket or 3}",
        deck_tension=[],
        must_preserve_themes=tags[:6],
    )


def _payload(
    deck: DeckDetailResponse,
    coach_memory_notes: str | None,
    user_goal: str,
    signals: object,
) -> dict[str, object]:
    profile = pipeline.deck_profile(deck, coach_memory_notes, user_goal)
    cards = profile["cards"]
    assert isinstance(cards, list)
    return {
        "deck_name": profile["deck_name"],
        "commander": profile["commander"],
        "partner": profile["partner"],
        "bracket": profile["bracket"],
        "archetype_tags": profile["archetype_tags"],
        "coach_memory_notes": profile["coach_memory_notes"],
        "user_goal": profile["user_goal"],
        "signal_lanes": _dump(signals),
        "notable_cards": cards[:24],
    }


def _dump(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump()  # type: ignore[no-any-return, attr-defined]
    return value


def _archetype_from_tags(tags: list[str]) -> str | None:
    if not tags:
        return None
    words = [tag.replace("_", " ").title() for tag in tags[:4]]
    return " / ".join(words)
