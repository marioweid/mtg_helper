"""Commander Coach routing agent.

This lightweight agent decides whether a user turn should read/write memory,
delete memory, run Deck Doctor, or receive a lightweight chat response.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from mtg_helper.models.ai import CommanderCoachRequest
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.agents._model import make_google_model

_log = logging.getLogger(__name__)

RouteKind = Literal[
    "memory_read",
    "memory_write",
    "memory_delete",
    "doctor",
    "targeted_replacement",
    "chat",
]

_SYSTEM_PROMPT = """You are the Commander Coach front-door router for an MTG deck helper.
Classify the user's latest turn. Do not give deck recommendations here.

Routes:
- memory_read: user asks what you remember / what is in memory.
- memory_write: user states a stable preference, deck interpretation, avoid rule,
  protected engine, or asks you to remember something. Examples: "I hate
  counterspells", "Yuna cares about all counters", "protect the food engine".
- memory_delete: user asks you to forget/remove/delete a remembered preference.
- doctor: user asks for whole-deck changes/recommendations/analysis: cuts,
  adds, swaps, upgrade, fix mana, improve deck, weak cards, what should I change.
- targeted_replacement: user asks what to replace one specific card with, or
  asks for alternatives to a named card. Extract target_card_name exactly.
- chat: casual talk, clarification, or anything that should not call a specialist.

Memory writes should be concise imperative or factual notes useful on future deck
recommendations. Preserve names and mechanics. If uncertain between memory_write
and chat, choose chat. If uncertain between doctor and chat, choose chat.
"""


class CoachRoute(BaseModel):
    """Structured routing decision for one Coach turn."""

    route: RouteKind
    confidence: float = Field(ge=0.0, le=1.0)
    memory_note: str | None = None
    delete_query: str | None = None
    chat_reply: str | None = None
    target_card_name: str | None = None
    reason: str


@dataclass(frozen=True)
class RouterDeps:
    """Routing context."""

    deck: DeckDetailResponse
    memory_notes: str


def _latest_user_text(message: str) -> str:
    marker = "\nUser:"
    if marker in message:
        return message.rsplit(marker, maxsplit=1)[-1].strip()
    return message.strip()


def _deck_context(deck: DeckDetailResponse, memory_notes: str) -> dict[str, object]:
    commander = deck.commander_card
    return {
        "deck_name": deck.name,
        "commander": commander.name if commander else None,
        "partner": deck.partner_card.name if deck.partner_card else None,
        "archetype_tags": list(deck.archetype_tags or []),
        "memory_notes": memory_notes,
    }


def _build_agent() -> Agent[RouterDeps, CoachRoute]:
    return Agent[RouterDeps, CoachRoute](
        model=make_google_model(),
        deps_type=RouterDeps,
        output_type=CoachRoute,
        system_prompt=_SYSTEM_PROMPT,
        model_settings={"temperature": 0.0, "max_tokens": 512},
        retries=1,
    )


_AGENT: Agent[RouterDeps, CoachRoute] | None = None


def _get_agent() -> Agent[RouterDeps, CoachRoute]:
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


async def route_message(
    deck: DeckDetailResponse,
    request: CommanderCoachRequest,
) -> CoachRoute:
    """Route the latest user turn with a small structured-output agent."""
    memory = request.coach_memory_notes or ""
    payload = {
        "latest_user_message": _latest_user_text(request.message),
        "conversation": request.message[-4000:],
        "deck": _deck_context(deck, memory),
    }
    try:
        result = await asyncio.wait_for(
            _get_agent().run(json.dumps(payload, default=str), deps=RouterDeps(deck, memory)),
            timeout=20.0,
        )
        route = result.output
    except Exception:  # noqa: BLE001 - routing failure should not trigger heavy specialists
        _log.exception("Commander Coach router failed")
        route = CoachRoute(
            route="chat",
            confidence=0.0,
            chat_reply="I couldn't confidently route that. Could you rephrase what you want?",
            reason="router failure",
        )
    actionable = {"doctor", "memory_write", "memory_delete", "targeted_replacement"}
    if route.confidence < 0.45 and route.route in actionable:
        return CoachRoute(
            route="chat",
            confidence=route.confidence,
            chat_reply=(
                "I am not sure whether you want memory edited or deck recommendations. "
                "Can you clarify?"
            ),
            reason=f"low confidence: {route.reason}",
        )
    return route
