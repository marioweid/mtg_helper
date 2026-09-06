"""Single tool-using conversational MTG Assistant."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext, UsageLimitExceeded, UsageLimits
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
    GameChangerCheck,
    LegalityReport,
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
    check_game_changers as check_game_changers_service,
)
from mtg_helper.services.mtg_assistant_tools import (
    check_legality as check_legality_service,
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
_MAX_TOOL_CALLS = 10
_REQUEST_LIMIT = 12
_TIMEOUT_SECONDS = 120.0
_MAX_HISTORY_CHARACTERS = 12_000

_SYSTEM_PROMPT = """You are an experienced Commander brewing partner: direct, warm, and verified.

COACHING WORKFLOW
- Understand the commander's game plan and the user's stated direction.
- Answer the current question directly. Have an informed opinion and make reasonable, reversible
  assumptions when the user's direction is clear.
- Give a small ranked package, explain interactions with the commander and existing cards, state
  tradeoffs, and identify what to add or change first.
- Prefer overlapping engines and flexible cards over disconnected staples when evidence supports it.
- Do not ask for facts already present in the deck briefing, memory, or conversation.

THEME CONVERSIONS (e.g. "make this an aristocrats deck")
- Call analyze_deck for current fit evidence, then find_cards with the target strategy as
  theme_hints (natural wording) or theme_tags (exact catalog slugs) plus the user's constraints.
- Cut cards whose function or fit evidence conflicts with the target strategy - for example,
  combat-finisher cards (Craterhoof Behemoth, Triumph of the Horde), tribal anthems, or payoff
  cards that need the old plan - and add target-theme engines and payoffs that overlap the
  commander and existing cards.
- When the deck already produces many tokens, prefer payoffs that trigger from token or artifact
  deaths (e.g. "whenever a creature or artifact you control is put into a graveyard" drains) over
  generic one-mana sac outlets, and keep the deck's token generators as fuel.
- For whole-deck conversions, ask find_cards for a generous limit (12-20) and rank the returned
  pool against the commander's plan and the deck's existing engines before choosing.
- If the target theme is already in the deck's theme tags or cards, anchor recommendations to it.

COLLECTION-ONLY REQUESTS (e.g. "add cards I own", "which of my cards can I add")
- Call find_cards with collection_only=true so results are restricted to cards the user owns.
  Each returned card includes owned_quantity - use it to say how many copies the user has and
  whether a recommended card is a single copy or a spare.
- If the search returns no candidates, the user likely does not own matching cards; say so and
  offer to search without the collection restriction instead of inventing owned cards.

BRACKET CONVERSIONS (e.g. "make this cEDH deck bracket 3")
- Call check_bracket first, passing the target bracket (e.g. 3) so its
  game_changers, game_changer_limit, game_changer_overage, and mass_land_destruction
  lists describe the target rules. The deck briefing also flags game_changer cards.
- Bracket 3 allows at most 3 Game Changers; brackets 1-2 allow none. List the exact Game Changers
  to cut, then use find_cards with exclude_game_changers=true for bracket-3-legal replacements,
  and exclude_game_changers=true for bracket 1-2 conversions (zero Game Changers).
- Replace mass land destruction at brackets 1-3 and fast mana at bracket 1. Prefer replacements
  that keep the deck's core plan (e.g. a fast mana rock for a ritual, a value engine for a
  combo piece) so the power level drops without losing the identity.
- Large conversions: list every Game Changer that must leave in cuts, and call find_cards more than
  once to build a real replacement package (engines, interaction, lands via analyze_mana_base).

VERIFICATION
- Distinguish verified card facts from strategic judgment.
- Recommended additions MUST come from find_cards in this run. Prior recommendation references help
  resolve follow-ups but must be searched again before returning actionable cards. Return the exact
  scryfall_id.
- Never state whether a card is or isn't a Game Changer from memory - verify with
  check_game_changers (arbitrary cards) or check_bracket (the current deck).
- The deck briefing includes bounded Oracle text for every current card. Use inspect_deck_cards only
  when exact wording beyond that briefing matters.
- For a repeatable or infinite loop, account for starting resources, every cost and trigger,
  resources produced, how the state resets, and the payoff. Never call a loop infinite while a
  required resource decreases each iteration.

THEME VOCABULARY (pass these as theme_tags or natural wording as theme_hints)
- aristocrats: sacrifice creatures/tokens for death triggers and drain payoffs (Blood Artist style).
- tokens: go-wide creature/artifact token swarms and token payoffs.
- reanimator: fill the graveyard and return permanents to the battlefield.
- blink: exile and return permanents for enter-the-battlefield value.
- spellslinger: cast many instants/sorceries; storm, magecraft, cantrips.
- artifacts: artifact engines, treasures, affinity, artifact payoffs.
- enchantments: enchantress, constellation, aura strategies.
- equipment: equip payoffs and equipment voltron.
- lifegain: gain life and reward life totals; soul sisters and lifegain finishers.
- +1/+1 counters (plus_one_plus_one): counter synergy, proliferate, counter payoffs.
- voltron: pile auras/equipment/counters onto one attacker; commander damage.
- x_spells: X-cost spells, hydras, scalable mana payoffs.
- graveyard: self-mill, dredge, delve, graveyard-filling engines.
- stax: taxes, restrictions, hate bears, resource denial.
- treasure: Treasure token generation and payoffs.
- storm: storm count payoffs and ritual-heavy lines.

TOOLS AND OUTPUT
- Use inspect_deck_cards to recheck exact text when a rules-sensitive interaction depends on it.
- Never invent a card, legality result, bracket rule, theme membership, or score.
- Use find_cards when actual additions improve the answer. Strategy and deck-building concepts can
  be answered without tools.
- Express explicit requirements with find_cards fields; never filter a broad result in prose.
- mana_cost_symbols matches symbols in the printed mana cost, not symbols or X in oracle text.
- Distinguish mana cost from mana value, card type from subtype, and theme from constraints.
- For qualitative budget words such as cheap, omit the numeric filter and state a brief assumption;
  ask for a hard cap only when it materially changes the decision.
- Call analyze_deck for deck diagnosis, cuts, or swaps.
- For landbase, land base, mana base, color fixing, or land-swap requests, call
  analyze_mana_base first. Its swaps are sufficient unless the user asks for constrained or
  additional alternatives; only then make a follow-up find_cards call.
- For cuts and swaps, prefer the lowest deck-fit scores returned by analyze_deck and explain the
  provided evidence. Do not propose protected cards as ordinary cuts or alter numeric scores.
- For one-card replacement requests, use replacement mode and return the exact target card name
  from the deck. Set each option's role match and explain any tradeoff. Use keep_reason only when
  keeping the target is a defensible recommendation.
- Call check_legality for legality questions and check_bracket for bracket questions.
- Call check_game_changers when a question turns on whether specific cards are on the official
  Game Changers list (e.g. "which of these are Game Changers?"); pass the exact card names.
- Treat brackets as table guidance, not format legality.
- Prefer a few strong, deck-specific recommendations over generic lists.
- Output mode: use mode=doctor for whole-deck diagnosis, cuts, or conversion requests and fill
  cuts plus recommendations (set replaces on each recommendation when the swap is clear). Use
  mode=replacement only for one named card. Otherwise keep mode=chat, which may still include
  recommendations.
- Ask one focused question only when the missing answer materially changes legality, budget, or two
  genuinely different strategies. Never ask because an internal search or theme lookup was empty.
- Never mention tools, searches, pipelines, IDs, scores, theme availability, fallback, or
  validation.
- Sound like a knowledgeable MTG friend, not an audit report. Avoid canned openings and generic
  closing offers.
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
    recommendations: list[AssistantRecommendation] = Field(default_factory=list, max_length=12)
    cuts: list[AssistantCut] = Field(default_factory=list, max_length=24)
    target_card_name: str | None = Field(default=None, max_length=200)
    keep_reason: str | None = Field(default=None, max_length=500)


@dataclass
class AssistantDeps:
    """Runtime dependencies and grounding state for one assistant turn."""

    pool: asyncpg.Pool
    deck: DeckDetailResponse
    account_id: UUID | None = None
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
            find_cards,
            inspect_deck_cards,
            analyze_mana_base,
            analyze_deck,
            check_legality,
            check_bracket,
            check_game_changers,
        ],
    )


async def find_cards(
    ctx: RunContext[AssistantDeps],
    filters: AssistantCardSearchInput,
) -> CardSearchResult:
    """Find legal additions using optional theme evidence and automatic global fallback.

    When ``filters.collection_only`` is set, results are restricted to cards the
    account owns across its collections, and each candidate carries the owned
    quantity so the assistant can say how many copies the user has.
    """
    if not ctx.deps.allow_tool():
        return CardSearchResult(evidence_source="none", message="Tool-call budget exhausted.")
    owned_card_ids = await _owned_card_ids(ctx.deps) if filters.collection_only else None
    result = await search_cards_service(
        ctx.deps.pool,
        ctx.deps.deck,
        filters,
        owned_card_ids=owned_card_ids,
    )
    await _attach_owned_quantities(ctx.deps, result)
    for candidate in result.candidates:
        if candidate.card.scryfall_id is not None:
            ctx.deps.retrieved[candidate.card.scryfall_id] = candidate
    return result


async def _owned_card_ids(deps: AssistantDeps) -> frozenset[UUID]:
    """Return canonical card ids the account owns, or an empty set when unknown."""
    if deps.account_id is None:
        return frozenset()
    from mtg_helper.services import collection_service

    collections = await collection_service.list_collections(deps.pool, deps.account_id)
    return await collection_service.get_owned_card_ids_for_collections(
        deps.pool, [collection.id for collection in collections]
    )


async def _attach_owned_quantities(deps: AssistantDeps, result: CardSearchResult) -> None:
    """Enrich collection-restricted candidates with the number of copies owned."""
    if deps.account_id is None or not result.candidates:
        return
    scryfall_ids = [
        candidate.card.scryfall_id
        for candidate in result.candidates
        if candidate.card.scryfall_id is not None
    ]
    if not scryfall_ids:
        return
    from mtg_helper.services import collection_service

    quantities = await collection_service.owned_quantities(deps.pool, deps.account_id, scryfall_ids)
    for candidate in result.candidates:
        if candidate.card.scryfall_id is not None:
            candidate.owned_quantity = quantities.get(candidate.card.scryfall_id, 0)


async def inspect_deck_cards(
    ctx: RunContext[AssistantDeps],
    names: Annotated[list[str], Field(max_length=8)],
) -> DeckCardInspection | None:
    """Return exact text and fit evidence for up to eight current-deck cards.

    The argument schema caps ``names`` at eight so pydantic-ai rejects an
    oversized tool call as a retryable validation error instead of letting the
    deck-inspection guard raise ValueError inside the tool and abort the run.
    """
    if not ctx.deps.allow_tool():
        return None
    if len(names) > 8:
        raise ModelRetry(
            f"inspect_deck_cards accepts at most 8 card names per call "
            f"(received {len(names)}); split the request into batches of up to 8."
        )
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


async def check_bracket(
    ctx: RunContext[AssistantDeps], target_bracket: int | None = None
) -> BracketReport | None:
    """Evaluate the deck against the project's versioned bracket rules.

    Pass ``target_bracket`` to evaluate a conversion (e.g. 3 for "would this
    pass at bracket 3?"); otherwise the deck's declared bracket is used.
    """
    if not ctx.deps.allow_tool():
        return None
    return check_bracket_service(ctx.deps.deck, target_bracket)


async def check_game_changers(
    ctx: RunContext[AssistantDeps],
    names: Annotated[list[str], Field(max_length=10)],
) -> GameChangerCheck | None:
    """Check which named cards are on the official Game Changers list.

    Use for questions about arbitrary cards (e.g. "is Doubling Season a Game
    Changer?"); for the current deck, prefer check_bracket. The argument schema
    caps ``names`` at ten so an oversized tool call becomes a retryable
    validation error instead of a ValueError inside the tool aborting the run.
    """
    if not ctx.deps.allow_tool():
        return None
    if len(names) > 10:
        raise ModelRetry(
            f"check_game_changers accepts at most 10 card names per call "
            f"(received {len(names)}); split the request into batches of up to 10."
        )
    return await check_game_changers_service(ctx.deps.pool, names)


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
    *,
    account_id: UUID | None = None,
) -> CommanderCoachResponse:
    """Run one bounded assistant turn and return the legacy-compatible envelope.

    Args:
        pool: Database pool.
        deck: The deck the assistant is coaching.
        request: The user request with history and memory.
        progress: Optional progress callback.
        account_id: The owning account; enables collection-aware card search.
    """
    if progress is not None:
        await progress("assistant_thinking", "MTG Assistant is selecting deterministic tools")
    deps = AssistantDeps(pool=pool, deck=deck, account_id=account_id)
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
                    input_tokens_limit=128_000,
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
        "prior_recommendations": [
            reference.model_dump(mode="json")
            for turn in request.history
            if turn.role == "assistant"
            for reference in turn.recommendations
        ][-8:],
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
    reply = output.reply
    if output.recommendations and not recommendations:
        reply = "I couldn't verify those card suggestions, so I left them out."
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
            reply=reply,
            recommendations=options,
        )
    if output.mode == "replacement":
        target = _deck_card_name(output.target_card_name, existing)
        keep_reason = output.keep_reason.strip() if output.keep_reason else None
        if target is None or (not recommendations and not keep_reason):
            return CommanderCoachResponse(mode="chat", reply=reply)
        replacement = TargetedReplacementResponse(
            target_card_name=target,
            summary=reply,
            keep_reason=keep_reason,
            best_pick=options[0].card if options else None,
            options=options,
            tool_call_count=deps.tool_calls,
        )
        return CommanderCoachResponse(
            mode="replacement",
            reply=reply,
            recommendations=options,
            replacement=replacement,
        )
    if not recommendations and not cuts:
        return CommanderCoachResponse(mode="chat", reply=reply)
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
        summary=reply,
        game_plan=_game_plan(deps.deck),
        cuts=doctor_cuts,
        adds=doctor_adds,
        swaps=swaps,
        tool_call_count=deps.tool_calls,
    )
    return CommanderCoachResponse(
        mode="doctor",
        reply=reply,
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
