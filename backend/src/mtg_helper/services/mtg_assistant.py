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
from pydantic_ai.messages import ModelMessage

from mtg_helper.models.ai import (
    CommanderCoachRequest,
    CommanderCoachResponse,
    DeckDoctorResponse,
    DoctorAdd,
    DoctorCut,
    DoctorSwap,
    ReplacementOption,
    TargetedReplacementResponse,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.agents._history import to_model_messages
from mtg_helper.services.agents._model import make_openai_model, openai_model_settings
from mtg_helper.services.agents._usage import log_run_usage
from mtg_helper.services.assistant_deck_context import (
    DeckCardInspection,
    build_deck_briefing,
)
from mtg_helper.services.assistant_deck_context import (
    inspect_deck_cards as inspect_deck_cards_service,
)
from mtg_helper.services.mtg_assistant_tools import (
    AssistantManaBaseAnalysis,
    BracketReport,
    DeckAnalysis,
    LegalityReport,
    ThemeMatch,
)
from mtg_helper.services.mtg_assistant_tools import (
    analyze_deck as analyze_deck_service,
)
from mtg_helper.services.mtg_assistant_tools import (
    analyze_mana_base as analyze_mana_base_service,
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
    CardEvidenceSource,
    CardSearchCandidate,
    CardSearchResult,
)
from mtg_helper.services.mtg_card_search import search_cards as search_cards_service

ProgressCb = Callable[[str, str], Awaitable[None]]

_log = logging.getLogger(__name__)
_MAX_TOOL_CALLS = 6
_REQUEST_LIMIT = 8
_TIMEOUT_SECONDS = 45.0
_MAX_HISTORY_CHARACTERS = 12_000

_SYSTEM_PROMPT = """You are a confident but verified Commander deck-building partner.

COACHING WORKFLOW
- Understand the commander's game plan and the user's stated direction.
- Inspect what the deck already contains, then answer the current question directly.
- Give a small ranked package, explain interactions with the commander and existing cards, state
  tradeoffs, and identify what to add or change first.
- Prefer overlapping engines and flexible cards over disconnected staples when evidence supports it.
- Do not ask for facts already present in the deck briefing, memory, or conversation.

VERIFICATION
- Distinguish verified card facts from strategic judgment.
- Recommended additions MUST come from search_cards in this run. Return the exact scryfall_id.
- Inspect exact Oracle text before asserting a current-deck card interaction.
- For a repeatable or infinite loop, account for starting resources, every cost and trigger,
  resources produced, how the state resets, and the payoff. Never call a loop infinite while a
  required resource decreases each iteration.

TOOLS AND OUTPUT
- Use inspect_deck_cards for exact text of current cards.
- Never invent a card, legality result, bracket rule, theme membership, or score.
- For a thematic request, call search_themes before search_cards and pass only returned theme tags.
- Express explicit requirements with search_cards fields; never filter a broad result in prose.
- mana_cost_symbols matches symbols in the printed mana cost, not symbols or X in oracle text.
- Distinguish mana cost from mana value, card type from subtype, and theme from constraints.
- Do not invent numeric meanings for words such as cheap; ask or omit the numeric filter.
- If search_cards reports global_fallback, tell the user the selected theme had no matching cards.
- Call analyze_deck for deck diagnosis, cuts, or swaps.
- For landbase, land base, mana base, color fixing, or land-swap requests, call
  analyze_mana_base first. Its swaps are sufficient unless the user asks for constrained or
  additional alternatives; only then make a follow-up search_cards call.
- For cuts and swaps, prefer the lowest deck-fit scores returned by analyze_deck and explain the
  provided evidence. Do not propose protected cards as ordinary cuts or alter numeric scores.
- For one-card replacement requests, use replacement mode and return the exact target card name
  from the deck. Set each option's role match and explain any tradeoff. Use keep_reason only when
  keeping the target is a defensible recommendation.
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
    role_match: Literal["same_role", "role_upgrade", "theme_upgrade", "role_change"] = "same_role"
    tradeoff: str | None = Field(default=None, max_length=500)


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
    target_card_name: str | None = Field(default=None, max_length=200)
    keep_reason: str | None = Field(default=None, max_length=500)


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
    return Agent[AssistantDeps, AssistantAnswer](
        model=make_openai_model(),
        deps_type=AssistantDeps,
        output_type=AssistantAnswer,
        system_prompt=_SYSTEM_PROMPT,
        model_settings=openai_model_settings(
            max_tokens=4096,
            reasoning="low",
            verbosity="medium",
        ),
        retries=1,
        tools=[
            search_themes,
            search_cards,
            inspect_deck_cards,
            analyze_mana_base,
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


async def inspect_deck_cards(
    ctx: RunContext[AssistantDeps], names: list[str]
) -> DeckCardInspection | None:
    """Return exact text and fit evidence for up to eight current-deck cards."""
    if not ctx.deps.allow_tool():
        return None
    return inspect_deck_cards_service(ctx.deps.deck, names)


async def analyze_deck(ctx: RunContext[AssistantDeps]) -> DeckAnalysis | None:
    """Calculate mana, curve, roles, theme density, and weak-fit cards."""
    if not ctx.deps.allow_tool():
        return None
    return analyze_deck_service(ctx.deps.deck)


async def analyze_mana_base(ctx: RunContext[AssistantDeps]) -> AssistantManaBaseAnalysis | None:
    """Calculate color-source deficiencies and grounded land-for-land swaps."""
    if not ctx.deps.allow_tool():
        return None
    result = await analyze_mana_base_service(ctx.deps.pool, ctx.deps.deck)
    for swap in result.swaps:
        if swap.add.scryfall_id is None:
            continue
        ctx.deps.retrieved[swap.add.scryfall_id] = CardSearchCandidate(
            card=swap.add,
            evidence_source=CardEvidenceSource.GLOBAL_SEARCH,
            matched_filters=["mana_base_analysis"],
            role_matches=["land"],
        )
    return result


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
    history = _bounded_history(request)
    try:
        result = await asyncio.wait_for(
            get_agent().run(
                json.dumps(payload, default=str),
                deps=deps,
                message_history=history,
                usage_limits=UsageLimits(
                    request_limit=_REQUEST_LIMIT,
                    tool_calls_limit=_MAX_TOOL_CALLS,
                    input_tokens_limit=64_000,
                    output_tokens_limit=8_000,
                ),
            ),
            timeout=_TIMEOUT_SECONDS,
        )
        log_run_usage("mtg_assistant", "answer", result.usage())
        output = result.output
    except (TimeoutError, UsageLimitExceeded):
        _log.warning("MTG Assistant exceeded its bounded run budget")
        return CommanderCoachResponse(
            mode="chat",
            reply="I hit the assistant's tool or time limit before I could verify an answer.",
        )
    except Exception as exc:  # noqa: BLE001 - return a recoverable assistant response
        _log.error(
            "AI run failed: workflow=mtg_assistant operation=answer "
            "exception_type=%s; using recoverable chat fallback",
            type(exc).__name__,
        )
        return CommanderCoachResponse(
            mode="chat",
            reply="I couldn't complete a verified answer. Please try the request again.",
        )
    if progress is not None:
        await progress("assistant_grounding", "Validating retrieved cards and deck evidence")
    return _to_response(output, deps)


def _prompt_payload(deck: DeckDetailResponse, request: CommanderCoachRequest) -> dict[str, object]:
    return {
        "current_request": request.message,
        "deck": build_deck_briefing(deck),
        "preferences": (request.coach_memory_notes or "")[-8000:],
    }


def _bounded_history(request: CommanderCoachRequest) -> list[ModelMessage]:
    turns = [turn.model_dump() for turn in request.history]
    while turns and sum(len(turn["content"]) for turn in turns) > _MAX_HISTORY_CHARACTERS:
        turns.pop(0)
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return to_model_messages(turns)


def _to_response(output: AssistantAnswer, deps: AssistantDeps) -> CommanderCoachResponse:
    existing = {card.name for card in deps.deck.cards}
    cuts = [cut for cut in output.cuts if cut.card_name in existing]
    recommendations = [
        (item, deps.retrieved[item.scryfall_id])
        for item in output.recommendations
        if item.scryfall_id in deps.retrieved
    ]
    options = [
        ReplacementOption(
            card=candidate.card,
            reason=item.reason,
            role_match=item.role_match,
            tradeoff=item.tradeoff,
        )
        for item, candidate in recommendations
    ]
    if output.mode == "chat":
        return CommanderCoachResponse(
            mode="chat",
            reply=output.reply,
            recommendations=options,
        )
    if output.mode == "replacement":
        target = _deck_card_name(output.target_card_name, existing)
        keep_reason = output.keep_reason.strip() if output.keep_reason else None
        if target is None or (not recommendations and not keep_reason):
            return CommanderCoachResponse(mode="chat", reply=output.reply)
        replacement = TargetedReplacementResponse(
            target_card_name=target,
            summary=output.reply,
            keep_reason=keep_reason,
            best_pick=options[0].card if options else None,
            options=options,
            tool_call_count=deps.tool_calls,
        )
        return CommanderCoachResponse(
            mode="replacement",
            reply=output.reply,
            recommendations=options,
            replacement=replacement,
        )
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
    return CommanderCoachResponse(
        mode="doctor",
        reply=output.reply,
        recommendations=options,
        doctor=doctor,
    )


def _deck_card_name(target: str | None, existing: set[str]) -> str | None:
    if target is None:
        return None
    normalized = target.strip().casefold()
    return next((name for name in existing if name.casefold() == normalized), None)


def _game_plan(deck: DeckDetailResponse) -> str:
    if deck.description:
        return deck.description[:500]
    themes = ", ".join(tag.replace("_", " ") for tag in deck.archetype_tags[:4])
    commander = deck.commander_card.name if deck.commander_card else deck.name
    return f"Build around {commander}" + (f" using {themes}." if themes else ".")
