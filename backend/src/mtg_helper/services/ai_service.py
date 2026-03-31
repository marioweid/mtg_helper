"""AI deck building service using the OpenAI API."""

import json
import re
from uuid import UUID

import asyncpg
import openai

from mtg_helper.models.ai import BuildResponse, CardSuggestion, ChatResponse, SuggestResponse
from mtg_helper.models.cards import CardResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services import card_service, conversation_service, deck_service
from mtg_helper.services.deck_service import STAGES, next_stage, stage_number

_MODEL = "gpt-4.1-mini"
_TOTAL_STAGES = len(STAGES) - 1  # exclude "complete"

# Stage metadata: (category label, target count description)
_STAGE_META: dict[str, tuple[str, str]] = {
    "theme": ("core theme / synergy", "20-25"),
    "ramp": ("ramp / mana acceleration", "10-12"),
    "draw": ("card draw / card advantage", "8-10"),
    "removal": ("removal / interaction", "8-10"),
    "utility": ("utility / flex", "5-8"),
    "lands": ("mana base / lands", "35-38"),
}

_BRACKET_DESCRIPTIONS = {
    1: "casual precon-level, no staples, minimal tutors",
    2: "upgraded casual, some staples, light tutors",
    3: "optimized, efficient synergies, strong staples",
    4: "cEDH, maximum power, fast mana, free interaction",
}


class DeckNotFoundError(ValueError):
    """Raised when the requested deck does not exist."""


class LLMEmptyResponseError(RuntimeError):
    """Raised when the LLM returns empty or null content."""


def _build_system_prompt(
    deck: DeckDetailResponse,
    commander: CardResponse,
    partner: CardResponse | None,
) -> str:
    """Build the system prompt with full deck context."""
    color_identity = ", ".join(commander.color_identity) or "colorless"
    bracket = deck.bracket or 3
    bracket_desc = _BRACKET_DESCRIPTIONS.get(bracket, "")

    parts = [
        "You are an expert Magic: The Gathering Commander deck builder.",
        "",
        f"Commander: {commander.name}",
        f"Type: {commander.type_line or 'unknown'}",
        f"Color identity: {color_identity}",
    ]
    if commander.oracle_text:
        parts.append(f"Rules text: {commander.oracle_text}")
    if partner:
        parts.append(f"Partner: {partner.name} ({partner.type_line or ''})")
        if partner.oracle_text:
            parts.append(f"Partner rules text: {partner.oracle_text}")

    if deck.description:
        parts.append(f"\nDeck strategy: {deck.description}")

    parts += [
        f"\nPower level: Bracket {bracket} — {bracket_desc}.",
        "",
        "CONSTRAINTS:",
        f"- Only suggest cards with color identity within: [{color_identity}]",
        "- Only suggest Commander-legal cards (no banned cards)",
        "- Every card must be a real, existing Magic card",
        "",
        "OUTPUT FORMAT:",
        "Return ONLY a JSON array. Each element must have these exact keys:",
        '  {"name": "exact card name", "category": "category label",'
        ' "reasoning": "why this fits", "synergies": ["card or mechanic it synergizes with"]}',
        "Do not include any text outside the JSON array.",
    ]
    return "\n".join(parts)


def _format_current_cards(deck: DeckDetailResponse) -> str:
    """Summarize cards already in the deck for AI context."""
    if not deck.cards:
        return "No cards added yet."
    by_cat: dict[str, list[str]] = {}
    for c in deck.cards:
        by_cat.setdefault(c.category or "other", []).append(c.name)
    lines = []
    for cat, names in sorted(by_cat.items()):
        lines.append(f"{cat}: {', '.join(names)}")
    return "\n".join(lines)


def _build_stage_prompt(stage: str, deck: DeckDetailResponse) -> str:
    """Build the user message for a specific build stage."""
    cat_label, target = _STAGE_META.get(stage, (stage, "10"))
    current_summary = _format_current_cards(deck)
    return (
        f"Build stage: {cat_label} (target: {target} cards)\n\n"
        f"Cards already in the deck:\n{current_summary}\n\n"
        f"Suggest {target} {cat_label} cards for this Commander deck. "
        "Consider synergies with existing cards. Return only the JSON array."
    )


def _parse_suggestions(raw: str) -> list[dict]:
    """Extract a JSON array from the LLM response text."""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group())
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _suggestion_from_card(card: CardResponse, raw: dict) -> CardSuggestion:
    """Build a CardSuggestion from a validated card + raw AI output."""
    return CardSuggestion(
        scryfall_id=card.scryfall_id,
        name=card.name,
        mana_cost=card.mana_cost,
        type_line=card.type_line,
        image_uri=card.image_uri,
        category=raw.get("category", ""),
        reasoning=raw.get("reasoning", ""),
        synergies=raw.get("synergies") or [],
    )


async def _call_llm(
    ai_client: openai.AsyncOpenAI,
    system: str,
    history: list[dict[str, str]],
    user_message: str,
) -> str:
    """Send a message to the LLM and return the text response."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        *history,
        {"role": "user", "content": user_message},
    ]
    response = await ai_client.chat.completions.create(
        model=_MODEL,
        max_completion_tokens=4096,
        messages=messages,
    )
    choice = response.choices[0]
    content = choice.message.content
    if not content:
        finish_reason = getattr(choice, "finish_reason", "unknown")
        raise LLMEmptyResponseError(f"LLM returned empty content (finish_reason={finish_reason!r})")
    return content


async def _validate_suggestions(
    pool: asyncpg.Pool,
    raw_items: list[dict],
    commander: CardResponse,
) -> tuple[list[CardSuggestion], list[str]]:
    """Validate AI suggestions against the local DB and color identity."""
    names = [item.get("name", "") for item in raw_items if item.get("name")]
    matched, unresolved = await card_service.resolve_card_names(pool, names)

    suggestions: list[CardSuggestion] = []
    for card in matched:
        violations = set(card.color_identity) - set(commander.color_identity)
        if violations:
            unresolved.append(card.name)
            continue
        raw = next((r for r in raw_items if r.get("name", "").lower() == card.name.lower()), {})
        suggestions.append(_suggestion_from_card(card, raw))

    return suggestions, unresolved


async def build_stage(
    pool: asyncpg.Pool,
    ai_client: openai.AsyncOpenAI,
    deck_id: UUID,
) -> BuildResponse:
    """Advance the deck to the next build stage and return AI suggestions.

    Args:
        pool: asyncpg connection pool.
        ai_client: OpenAI async client.
        deck_id: The deck's UUID.

    Returns:
        BuildResponse with validated card suggestions for the new stage.

    Raises:
        DeckNotFoundError: If the deck does not exist.
    """
    deck = await deck_service.get_deck(pool, deck_id)
    if deck is None:
        raise DeckNotFoundError(f"Deck {deck_id} not found")

    stage = next_stage(deck.stage)
    if stage is None or stage == "complete":
        return BuildResponse(
            stage="complete",
            stage_number=_TOTAL_STAGES,
            total_stages=_TOTAL_STAGES,
            suggestions=[],
            unresolved=[],
        )

    commander = await card_service.get_card_by_id(pool, deck.commander_id)
    if commander is None:
        raise DeckNotFoundError(f"Commander card not found for deck {deck_id}")

    partner = None
    if deck.partner_id:
        partner = await card_service.get_card_by_id(pool, deck.partner_id)

    system = _build_system_prompt(deck, commander, partner)
    user_msg = _build_stage_prompt(stage, deck)
    history = await conversation_service.get_turns(pool, deck_id)

    raw_response = await _call_llm(ai_client, system, history, user_msg)
    raw_items = _parse_suggestions(raw_response)

    suggestions, unresolved = await _validate_suggestions(pool, raw_items, commander)

    await conversation_service.append_turn(pool, deck_id, "user", user_msg)
    if raw_response:
        await conversation_service.append_turn(pool, deck_id, "assistant", raw_response)
    await deck_service.update_deck(pool, deck_id, deck_service.DeckUpdate(stage=stage))

    return BuildResponse(
        stage=stage,
        stage_number=stage_number(stage),
        total_stages=_TOTAL_STAGES,
        suggestions=suggestions,
        unresolved=unresolved,
    )


async def suggest_cards(
    pool: asyncpg.Pool,
    ai_client: openai.AsyncOpenAI,
    deck_id: UUID,
    prompt: str,
    count: int,
) -> SuggestResponse:
    """Return AI-suggested cards matching a free-form prompt.

    Args:
        pool: asyncpg connection pool.
        ai_client: OpenAI async client.
        deck_id: The deck's UUID.
        prompt: Natural language description of desired cards.
        count: Number of cards to request.

    Returns:
        SuggestResponse with validated suggestions.

    Raises:
        DeckNotFoundError: If the deck does not exist.
    """
    deck = await deck_service.get_deck(pool, deck_id)
    if deck is None:
        raise DeckNotFoundError(f"Deck {deck_id} not found")

    commander = await card_service.get_card_by_id(pool, deck.commander_id)
    if commander is None:
        raise DeckNotFoundError(f"Commander card not found for deck {deck_id}")

    partner = None
    if deck.partner_id:
        partner = await card_service.get_card_by_id(pool, deck.partner_id)

    current_summary = _format_current_cards(deck)
    user_msg = (
        f"{prompt}\n\n"
        f"Suggest {count} cards. Current deck:\n{current_summary}\n\n"
        "Return only the JSON array."
    )

    system = _build_system_prompt(deck, commander, partner)
    history = await conversation_service.get_turns(pool, deck_id)
    raw_response = await _call_llm(ai_client, system, history, user_msg)
    raw_items = _parse_suggestions(raw_response)

    suggestions, unresolved = await _validate_suggestions(pool, raw_items, commander)

    await conversation_service.append_turn(pool, deck_id, "user", user_msg)
    if raw_response:
        await conversation_service.append_turn(pool, deck_id, "assistant", raw_response)

    return SuggestResponse(suggestions=suggestions, unresolved=unresolved)


async def chat_about_deck(
    pool: asyncpg.Pool,
    ai_client: openai.AsyncOpenAI,
    deck_id: UUID,
    message: str,
) -> ChatResponse:
    """Handle a free-form chat message about the deck.

    If the assistant response contains a JSON array of card suggestions, they are
    validated and returned alongside the reply text.

    Args:
        pool: asyncpg connection pool.
        ai_client: OpenAI async client.
        deck_id: The deck's UUID.
        message: User's chat message.

    Returns:
        ChatResponse with reply text and any parsed card suggestions.

    Raises:
        DeckNotFoundError: If the deck does not exist.
    """
    deck = await deck_service.get_deck(pool, deck_id)
    if deck is None:
        raise DeckNotFoundError(f"Deck {deck_id} not found")

    commander = await card_service.get_card_by_id(pool, deck.commander_id)
    if commander is None:
        raise DeckNotFoundError(f"Commander card not found for deck {deck_id}")

    partner = None
    if deck.partner_id:
        partner = await card_service.get_card_by_id(pool, deck.partner_id)

    system = _build_system_prompt(deck, commander, partner)
    history = await conversation_service.get_turns(pool, deck_id)
    raw_response = await _call_llm(ai_client, system, history, message)

    raw_items = _parse_suggestions(raw_response)
    suggestions: list[CardSuggestion] = []
    if raw_items:
        suggestions, _ = await _validate_suggestions(pool, raw_items, commander)

    await conversation_service.append_turn(pool, deck_id, "user", message)
    if raw_response:
        await conversation_service.append_turn(pool, deck_id, "assistant", raw_response)

    return ChatResponse(reply=raw_response, suggestions=suggestions)
