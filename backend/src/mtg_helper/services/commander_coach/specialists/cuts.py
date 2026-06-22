"""Cut recommendation specialist for the Commander Coach pipeline."""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent

from mtg_helper.models.ai import (
    CoachCurveReport,
    CoachCutCandidate,
    CoachCutReport,
    CoachManaReport,
    DeckIdentityReport,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.agents._model import make_google_model
from mtg_helper.services.commander_coach import pipeline

_log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 35.0
_SYSTEM_PROMPT = """You are the Cut Recommendation Agent for a Commander deck coach.
Rank cards that are reasonable cuts for the identified deck plan.

Rules:
- Only name cards from the provided deck_cards list.
- Do not cut lands unless the mana report says too many lands.
- Preserve must_preserve_themes unless a card is a weak/off-plan version.
- Prefer cards with low synergy, redundant roles, high mana value, slow impact,
  bracket mismatch, or conflict with the deck identity.
- Give card-specific reasons based on type/oracle text/tags.
- Return 6-12 candidates when possible.
"""


@dataclass(frozen=True)
class CutDeps:
    """Dependencies for cut recommendation."""

    deck: DeckDetailResponse


def _build_agent() -> Agent[CutDeps, CoachCutReport]:
    return Agent[CutDeps, CoachCutReport](
        model=make_google_model(),
        deps_type=CutDeps,
        output_type=CoachCutReport,
        system_prompt=_SYSTEM_PROMPT,
        model_settings={"temperature": 0.25, "max_tokens": 4096},
        retries=1,
    )


_AGENT: Agent[CutDeps, CoachCutReport] | None = None


def _get_agent() -> Agent[CutDeps, CoachCutReport]:
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


async def recommend_cuts(
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    mana: CoachManaReport,
    curve: CoachCurveReport,
) -> CoachCutReport:
    """Run cut specialist and filter output to actual deck cards."""
    payload = _payload(deck, identity, mana, curve)
    try:
        result = await asyncio.wait_for(
            _get_agent().run(json.dumps(payload, default=str), deps=CutDeps(deck)),
            timeout=_TIMEOUT_SECONDS,
        )
        return _filter_report(deck, result.output)
    except Exception:  # noqa: BLE001 - Coach should still return analysis
        _log.exception("Cut Recommendation Agent failed")
        return fallback_cuts(deck)


def fallback_cuts(deck: DeckDetailResponse) -> CoachCutReport:
    """Use weak-card heuristics when the LLM cut specialist fails."""
    candidates = []
    for index, row in enumerate(pipeline.weak_cards(deck, 10)):
        candidates.append(
            CoachCutCandidate(
                card_name=row["name"],
                cut_score=max(4.0, 8.5 - index * 0.35),
                reason="Low theme/role overlap in the current deck profile.",
                tags=["low_synergy"],
            )
        )
    return CoachCutReport(summary="Heuristic low-synergy cut shortlist.", candidates=candidates)


def _payload(
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    mana: CoachManaReport,
    curve: CoachCurveReport,
) -> dict[str, Any]:
    return {
        "identity": identity.model_dump(),
        "mana_report": mana.model_dump(),
        "curve_report": curve.model_dump(),
        "deck_cards": pipeline.compact_card_rows(deck),
        "weak_card_shortlist": pipeline.weak_cards(deck, 16),
    }


def _filter_report(deck: DeckDetailResponse, report: CoachCutReport) -> CoachCutReport:
    names = {card.name for card in deck.cards}
    seen: set[str] = set()
    candidates: list[CoachCutCandidate] = []
    for candidate in report.candidates:
        if candidate.card_name not in names or candidate.card_name in seen:
            continue
        seen.add(candidate.card_name)
        candidates.append(candidate)
    return CoachCutReport(summary=report.summary, candidates=candidates[:12])
