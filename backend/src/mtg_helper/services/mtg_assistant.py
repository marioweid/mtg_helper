"""Single tool-using conversational MTG Assistant."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, UsageLimitExceeded, UsageLimits

from mtg_helper.config import settings
from mtg_helper.models.ai import (
    CommanderCoachRequest,
    CommanderCoachResponse,
    DeckDoctorResponse,
    DoctorAdd,
    DoctorCut,
    DoctorSwap,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.agents._model import make_google_model
from mtg_helper.services.mtg_assistant_tools import (
    BracketReport,
    DeckAnalysis,
    LegalityReport,
    ThemeMatch,
)
from mtg_helper.services.mtg_assistant_tools import (
    analyze_deck as analyze_deck_service,
)
from mtg_helper.services.mtg_assistant_tools import (
    check_bracket as check_bracket_service,
)
from mtg_helper.services.mtg_assistant_tools import (
    check_legality as check_legality_service,
)
from mtg_helper.services.mtg_assistant_tools import (
    search_themes as search_themes_service,
)
from mtg_helper.services.mtg_card_search import (
    AssistantCardSearchInput,
    CardSearchCandidate,
    CardSearchResult,
)
from mtg_helper.services.mtg_card_search import search_cards as search_cards_service

ProgressCb = Callable[[str, str], Awaitable[None]]

_log = logging.getLogger(__name__)
_MAX_TOOL_CALLS = 6
_REQUEST_LIMIT = 8
_TIMEOUT_SECONDS = 45.0

_SYSTEM_PROMPT = """You are MTG Assistant, a concise conversational Magic: The Gathering helper.
You have one job: answer the user's current request using deterministic tools whenever facts about
their deck or cards are required.

Rules:
- Never invent a card, legality result, bracket rule, theme membership, or score.
- Any recommended card MUST come from search_cards in this run. Return its exact scryfall_id.
- For a thematic request, call search_themes before search_cards and pass only returned theme tags.
- Express explicit requirements with search_cards fields; never filter a broad result in prose.
- mana_cost_symbols matches symbols in the printed mana cost, not symbols or X in oracle text.
- Distinguish mana cost from mana value, card type from subtype, and theme from constraints.
- Do not invent numeric meanings for words such as cheap; ask or omit the numeric filter.
- If search_cards reports global_fallback, tell the user the selected theme had no matching cards.
- Call analyze_deck for deck diagnosis, cuts, or swaps.
- Call check_legality for legality questions and check_bracket for bracket questions.
- Treat brackets as table guidance, not format legality.
- Prefer a few strong, deck-specific recommendations over generic lists.
- If search_themes is ambiguous or empty, ask one focused clarification question.
- Rules-document lookup is not available yet; be transparent when an official rules citation is
  required.
- Do not mention internal agents or pipelines.
"""


class AssistantRecommendation(BaseModel):
    """A grounded recommendation referencing a tool-returned card."""

    scryfall_id: UUID
    reason: str = Field(max_length=500)
    replaces: list[str] = Field(default_factory=list, max_length=3)


class AssistantCut(BaseModel):
    """A proposed cut from the current deck."""

    card_name: str
    reason: str = Field(max_length=500)


class AssistantAnswer(BaseModel):
    """Structured final output from the single assistant run."""

    mode: Literal["chat", "doctor", "replacement"] = "chat"
    reply: str
    recommendations: list[AssistantRecommendation] = Field(default_factory=list, max_length=8)
    cuts: list[AssistantCut] = Field(default_factory=list, max_length=8)


@dataclass
class AssistantDeps:
    """Runtime dependencies and grounding state for one assistant turn."""

    pool: asyncpg.Pool
    deck: DeckDetailResponse
    retrieved: dict[UUID, CardSearchCandidate] = field(default_factory=dict)
    tool_calls: int = 0

    def allow_tool(self) -> bool:
        """Consume one deterministic tool call when budget remains."""
        if self.tool_calls >= _MAX_TOOL_CALLS:
            return False
        self.tool_calls += 1
        return True


def _build_agent() -> Agent[AssistantDeps, AssistantAnswer]:
    model_settings: dict[str, object] = {"max_tokens": 2048}
    if "gemini-3.5" not in settings.chat_model.lower():
        model_settings["temperature"] = 0.15
    return Agent[AssistantDeps, AssistantAnswer](
        model=make_google_model(),
        deps_type=AssistantDeps,
        output_type=AssistantAnswer,
        system_prompt=_SYSTEM_PROMPT,
        model_settings=model_settings,
        retries=1,
        tools=[
            search_themes,
            search_cards,
            analyze_deck,
            check_legality,
            check_bracket,
        ],
    )


async def search_themes(ctx: RunContext[AssistantDeps], query: str) -> list[ThemeMatch]:
    """Find relevant theme ids and descriptions for a strategy phrase."""
    if not ctx.deps.allow_tool():
        return []
    return await search_themes_service(ctx.deps.pool, query)


async def search_cards(
    ctx: RunContext[AssistantDeps],
    filters: AssistantCardSearchInput,
) -> CardSearchResult:
    """Apply typed filters to a theme-first or global legal card search."""
    if not ctx.deps.allow_tool():
        return CardSearchResult(evidence_source="none", message="Tool-call budget exhausted.")
    result = await search_cards_service(ctx.deps.pool, ctx.deps.deck, filters)
    for candidate in result.candidates:
        if candidate.card.scryfall_id is not None:
            ctx.deps.retrieved[candidate.card.scryfall_id] = candidate
    return result


async def analyze_deck(ctx: RunContext[AssistantDeps]) -> DeckAnalysis | None:
    """Calculate mana, curve, roles, theme density, and weak-fit cards."""
    if not ctx.deps.allow_tool():
        return None
    return analyze_deck_service(ctx.deps.deck)


async def check_legality(ctx: RunContext[AssistantDeps]) -> LegalityReport | None:
    """Check Commander legality in code, including bans and color identity."""
    if not ctx.deps.allow_tool():
        return None
    return await check_legality_service(ctx.deps.pool, ctx.deps.deck)


async def check_bracket(ctx: RunContext[AssistantDeps]) -> BracketReport | None:
    """Evaluate the deck against the project's versioned bracket rules."""
    if not ctx.deps.allow_tool():
        return None
    return check_bracket_service(ctx.deps.deck)


_AGENT: Agent[AssistantDeps, AssistantAnswer] | None = None


def get_agent() -> Agent[AssistantDeps, AssistantAnswer]:
    """Return the process-wide assistant instance."""
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


async def run_assistant(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    request: CommanderCoachRequest,
    progress: ProgressCb | None = None,
) -> CommanderCoachResponse:
    """Run one bounded assistant turn and return the legacy-compatible envelope."""
    if progress is not None:
        await progress("assistant_thinking", "MTG Assistant is selecting deterministic tools")
    deps = AssistantDeps(pool=pool, deck=deck)
    payload = _prompt_payload(deck, request)
    try:
        result = await asyncio.wait_for(
            get_agent().run(
                json.dumps(payload, default=str),
                deps=deps,
                usage_limits=UsageLimits(
                    request_limit=_REQUEST_LIMIT,
                    tool_calls_limit=_MAX_TOOL_CALLS,
                    input_tokens_limit=16_000,
                    output_tokens_limit=4_000,
                ),
            ),
            timeout=_TIMEOUT_SECONDS,
        )
        output = result.output
        usage = result.usage()
        _log.info(
            "MTG Assistant completed: tools=%d requests=%d input_tokens=%d output_tokens=%d",
            deps.tool_calls,
            usage.requests,
            usage.input_tokens,
            usage.output_tokens,
        )
    except (TimeoutError, UsageLimitExceeded):
        _log.warning("MTG Assistant exceeded its bounded run budget")
        return CommanderCoachResponse(
            mode="chat",
            reply="I hit the assistant's tool or time limit before I could verify an answer.",
        )
    except Exception:  # noqa: BLE001 - return a recoverable assistant response
        _log.exception("MTG Assistant run failed")
        return CommanderCoachResponse(
            mode="chat",
            reply="I couldn't complete a verified answer. Please try the request again.",
        )
    if progress is not None:
        await progress("assistant_grounding", "Validating retrieved cards and deck evidence")
    return _to_response(output, deps)


def _prompt_payload(deck: DeckDetailResponse, request: CommanderCoachRequest) -> dict[str, object]:
    commander = deck.commander_card
    return {
        "latest_request": request.message[-4000:],
        "deck": {
            "name": deck.name,
            "commander": commander.name if commander else None,
            "commander_text": commander.oracle_text if commander else None,
            "colors": deck.commander_color_identity,
            "bracket": deck.bracket,
            "themes": deck.archetype_tags,
            "card_count": sum(card.quantity for card in deck.cards),
        },
        "preferences": (request.coach_memory_notes or "")[-2000:],
    }


def _to_response(output: AssistantAnswer, deps: AssistantDeps) -> CommanderCoachResponse:
    existing = {card.name for card in deps.deck.cards}
    cuts = [cut for cut in output.cuts if cut.card_name in existing]
    recommendations = [
        (item, deps.retrieved[item.scryfall_id])
        for item in output.recommendations
        if item.scryfall_id in deps.retrieved
    ]
    if not recommendations and not cuts:
        return CommanderCoachResponse(mode="chat", reply=output.reply)
    doctor_cuts = [
        DoctorCut(card_name=cut.card_name, reason=cut.reason, confidence="medium") for cut in cuts
    ]
    doctor_adds = [
        DoctorAdd(card=candidate.card, reason=item.reason, confidence="medium")
        for item, candidate in recommendations
    ]
    swaps = [
        DoctorSwap(
            remove=[name for name in item.replaces if name in existing],
            add=[candidate.card],
            reason=item.reason,
        )
        for item, candidate in recommendations
        if any(name in existing for name in item.replaces)
    ]
    doctor = DeckDoctorResponse(
        summary=output.reply,
        game_plan=_game_plan(deps.deck),
        cuts=doctor_cuts,
        adds=doctor_adds,
        swaps=swaps,
        tool_call_count=deps.tool_calls,
    )
    mode = "replacement" if output.mode == "replacement" else "doctor"
    return CommanderCoachResponse(mode=mode, reply=output.reply, doctor=doctor)


def _game_plan(deck: DeckDetailResponse) -> str:
    if deck.description:
        return deck.description[:500]
    themes = ", ".join(tag.replace("_", " ") for tag in deck.archetype_tags[:4])
    commander = deck.commander_card.name if deck.commander_card else deck.name
    return f"Build around {commander}" + (f" using {themes}." if themes else ".")
