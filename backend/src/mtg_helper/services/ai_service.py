"""AI deck building service using the OpenAI API."""

import asyncio
import json
import logging
import re
from decimal import Decimal
from uuid import UUID

import asyncpg
import openai
from qdrant_client import AsyncQdrantClient

from mtg_helper.models.ai import BuildResponse, CardSuggestion, ChatResponse, SuggestResponse
from mtg_helper.models.cards import CardResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services import (
    card_service,
    conversation_service,
    deck_service,
    preference_service,
    profile_service,
)
from mtg_helper.services.deck_service import STAGES, next_stage, stage_number
from mtg_helper.services.retrieval_service import (
    RetrievedCard,
    parse_query_tags,
    parse_query_types,
    retrieve_candidates,
    stage_retrieval_query,
)

_log = logging.getLogger(__name__)

_MODEL = "gpt-4.1-mini"
_TOTAL_STAGES = len(STAGES) - 1  # exclude "complete"

# Stage metadata: (category label, target count description)
_STAGE_META: dict[str, tuple[str, str]] = {
    "ramp": ("ramp / mana acceleration", "10-12"),
    "interaction": (
        "interaction / removal and protection — targeted removal, board wipes, "
        "counterspells, hexproof/shroud givers (e.g. Lightning Greaves, Swiftfoot Boots), "
        "and indestructible effects (e.g. Heroic Intervention, Boros Charm)",
        "8-10",
    ),
    "draw": ("card draw / card advantage", "8-10"),
    "theme": ("core theme / synergy", "20-25"),
    "utility": ("utility / flex", "5-8"),
    "lands": ("mana base / lands", "35-38"),
}

_BRACKET_DESCRIPTIONS = {
    1: (
        "casual precon-level. No tutors, no infinite combos, no extra turn spells, "
        "no fast mana beyond Sol Ring. Prioritize fun and flavor over efficiency. "
        "Avoid staples that feel repetitive across every deck."
    ),
    2: (
        "upgraded casual. Light tutors are acceptable, but no infinite combos. "
        "Staples like Sol Ring and Arcane Signet are fine. "
        "Avoid mass land destruction and hyper-efficient win conditions."
    ),
    3: (
        "optimized. Efficient synergies and strong staples are expected. "
        "Tutors, combo finishers, and tight interaction are appropriate. "
        "Focus on a clear, redundant game plan."
    ),
    4: (
        "cEDH, maximum power. Prioritize fast mana, free interaction, "
        "compact win conditions, and efficient tutors. "
        "Every card should contribute to winning as quickly and consistently as possible."
    ),
}

_SIGNAL_LABELS: dict[str, str] = {
    "semantic": "Strong semantic match",
    "tag": "High tag relevance",
    "fts": "Strong text match",
}

# Threshold for highlighting top picks (new scoring is [0, 1])
_BANGER_SCORE_THRESHOLD = 0.6
_BANGER_MIN_SIGNALS = 2


class DeckNotFoundError(ValueError):
    """Raised when the requested deck does not exist."""


class LLMEmptyResponseError(RuntimeError):
    """Raised when the LLM returns empty or null content."""


def _compute_highlight_reasons(candidate: RetrievedCard) -> list[str] | None:
    """Return highlight reasons if the card is a multi-signal top hit ('banger').

    A card is highlighted when it scores highly across 2+ retrieval signals.

    Args:
        candidate: Retrieved card with weighted score and signal list.

    Returns:
        List of human-readable reason strings, or None if not a banger.
    """
    if len(candidate.signals) < _BANGER_MIN_SIGNALS:
        return None
    if candidate.score < _BANGER_SCORE_THRESHOLD:
        return None
    return [_SIGNAL_LABELS[s] for s in candidate.signals if s in _SIGNAL_LABELS]


def _card_from_retrieved(
    card: RetrievedCard,
    stage: str,
    query_tags: list[str],
) -> CardSuggestion:
    """Build a CardSuggestion directly from a RetrievedCard without LLM involvement.

    Args:
        card: Retrieved card with scoring data.
        stage: Build stage name (used for category label).
        query_tags: Tags used in the retrieval query (used to derive synergies).

    Returns:
        CardSuggestion populated from retrieval signals.
    """
    category = _STAGE_META.get(stage, (stage, ""))[0]
    matching_tags = [t for t in card.tags if t in query_tags]
    synergies = matching_tags or card.tags[:3]

    parts: list[str] = []
    for signal in card.signals:
        label = _SIGNAL_LABELS.get(signal)
        if label:
            parts.append(label)
    if card.edhrec_rank and card.edhrec_rank < 1000:
        parts.append(f"EDHREC rank {card.edhrec_rank}")
    reasoning = ". ".join(parts) if parts else "Relevant to stage"

    cmc_float: float | None = float(card.cmc) if card.cmc is not None else None

    return CardSuggestion(
        scryfall_id=card.scryfall_id,
        name=card.name,
        mana_cost=card.mana_cost,
        type_line=card.type_line,
        image_uri=card.image_uri,
        oracle_text=card.oracle_text,
        power=card.power,
        toughness=card.toughness,
        rarity=card.rarity,
        cmc=cmc_float,
        category=category,
        reasoning=reasoning,
        synergies=synergies,
        highlight_reasons=_compute_highlight_reasons(card),
    )


def _build_system_prompt(
    deck: DeckDetailResponse,
    commander: CardResponse,
    partner: CardResponse | None,
    preferences: dict[str, list[str]] | None = None,
    downvoted_cards: list[str] | None = None,
) -> str:
    """Build the system prompt with full deck context (used for chat).

    Args:
        deck: Full deck detail including cards and metadata.
        commander: Commander card data.
        partner: Partner commander card data, if any.
        preferences: Account preferences grouped by type for injection.
        downvoted_cards: Card names the user has thumbed-down for this deck.
    """
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
        f"\nPower level: Bracket {bracket} — {bracket_desc}",
        "",
        "CONSTRAINTS:",
        f"- Only suggest cards with color identity within: [{color_identity}]",
        "- Only suggest Commander-legal cards (no banned cards)",
        "- Every card must be a real, existing Magic card",
    ]

    pref_lines = _build_preference_lines(preferences, downvoted_cards)
    if pref_lines:
        parts += ["", *pref_lines]

    parts += [
        "",
        "OUTPUT FORMAT:",
        "Return ONLY a JSON array. Each element must have these exact keys:",
        '  {"name": "exact card name", "category": "category label",'
        ' "reasoning": "why this fits", "synergies": ["card or mechanic it synergizes with"]}',
        "Do not include any text outside the JSON array.",
    ]
    return "\n".join(parts)


def _build_preference_lines(
    preferences: dict[str, list[str]] | None,
    downvoted_cards: list[str] | None,
) -> list[str]:
    """Build the PLAYER PREFERENCES and FEEDBACK sections for the system prompt."""
    lines: list[str] = []

    if preferences is not None and any(preferences.values()):
        lines.append("PLAYER PREFERENCES:")
        if preferences.get("pet_cards"):
            cards = ", ".join(preferences["pet_cards"])
            lines.append(f"- Try to include these cards when possible: {cards}")
        if preferences.get("avoid_cards"):
            cards = ", ".join(preferences["avoid_cards"])
            lines.append(f"- Never suggest these cards: {cards}")
        if preferences.get("avoid_archetypes"):
            archetypes = ", ".join(preferences["avoid_archetypes"])
            lines.append(f"- Avoid strategies involving: {archetypes}")
        if preferences.get("general"):
            for note in preferences["general"]:
                lines.append(f"- {note}")

    if downvoted_cards:
        lines.append("FEEDBACK:")
        cards = ", ".join(downvoted_cards)
        lines.append(f"- Do not suggest these previously rejected cards: {cards}")

    return lines


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
    """Build a CardSuggestion from a validated card + raw AI output (used for chat)."""
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


async def _compute_feedback_weights(
    pool: asyncpg.Pool,
    deck_id: UUID,
    owner_id: UUID | None,
) -> dict[UUID, float] | None:
    """Compute per-card score multipliers from feedback and preferences.

    Returns None if feedback boosting is disabled or the deck has no owner.
    Weights are clamped to [0.05, 2.0].

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID (for per-deck thumbs up/down).
        owner_id: The account UUID (for account-level pet/avoid weights).

    Returns:
        Dict mapping card UUID to combined weight, or None to skip weighting.
    """
    if owner_id is None:
        return None
    if not await preference_service.is_feedback_boosting_enabled(pool, owner_id):
        return None

    async with pool.acquire() as conn:
        feedback_rows = await conn.fetch(
            "SELECT card_id, feedback FROM deck_feedback WHERE deck_id = $1",
            deck_id,
        )

    weights: dict[UUID, float] = {}
    for row in feedback_rows:
        weights[row["card_id"]] = 1.3 if row["feedback"] == "up" else 0.3

    pref_weights = await preference_service.get_card_preference_weights(pool, owner_id)
    for card_id, pref_mult in pref_weights.items():
        weights[card_id] = weights.get(card_id, 1.0) * pref_mult

    for card_id in weights:
        weights[card_id] = max(0.05, min(2.0, weights[card_id]))

    return weights if weights else None


async def _load_user_profile(
    pool: asyncpg.Pool,
    deck_id: UUID,
    owner_id: UUID | None,
) -> "profile_service.UserProfile | None":
    """Load the cross-deck user profile if the feature is enabled.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck being built (excluded from profile).
        owner_id: The account UUID.

    Returns:
        UserProfile if enabled and sufficient deck history exists, else None.
    """
    if owner_id is None:
        return None
    if not await preference_service.is_user_profile_enabled(pool, owner_id):
        return None
    return await profile_service.get_user_profile(pool, owner_id, deck_id)


async def _load_prompt_context(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
) -> tuple[dict[str, list[str]] | None, list[str]]:
    """Load account preferences and downvoted cards for prompt injection (used for chat).

    Args:
        pool: asyncpg connection pool.
        deck: Deck detail (owner_id used to fetch preferences).

    Returns:
        Tuple of (preferences dict or None, list of downvoted card names).
    """
    prefs: dict[str, list[str]] | None = None
    if deck.owner_id is not None:
        prefs = await preference_service.get_preferences_for_prompt(pool, deck.owner_id)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.name
            FROM deck_feedback df
            JOIN cards c ON df.card_id = c.id
            WHERE df.deck_id = $1 AND df.feedback = 'down'
            """,
            deck.id,
        )
    downvoted = [r["name"] for r in rows]
    return prefs, downvoted


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
    """Validate AI suggestions against the local DB and color identity (used for chat)."""
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


def _resolve_stage(
    current_deck_stage: str,
    requested_stage: str | None,
) -> tuple[str, bool]:
    """Resolve which stage to build and whether to advance the deck's stage column.

    Args:
        current_deck_stage: The deck's current stage from the database.
        requested_stage: Explicit stage requested by the client, or None to auto-advance.

    Returns:
        Tuple of (resolved_stage, should_advance).

    Raises:
        ValueError: If requested_stage is not a valid active stage.
    """
    if requested_stage is not None:
        active_stages = [s for s in STAGES if s != "complete"]
        if requested_stage not in active_stages:
            raise ValueError(f"Invalid stage: {requested_stage!r}")
        return requested_stage, False

    resolved = next_stage(current_deck_stage)
    if resolved is None or resolved == "complete":
        return "complete", False
    return resolved, True


def _compute_deck_cmc_counts(deck: DeckDetailResponse) -> dict[int, int]:
    """Compute CMC distribution of cards currently in the deck.

    Args:
        deck: Full deck detail with cards.

    Returns:
        Dict mapping CMC bucket (int, capped at 6) to count.
    """
    counts: dict[int, int] = {}
    for card in deck.cards:
        cmc = getattr(card, "cmc", None)
        if cmc is None:
            continue
        bucket = min(int(Decimal(str(cmc))), 6)
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


async def _resolve_exclude_ids(
    pool: asyncpg.Pool,
    exclude: list[str] | None,
) -> list[UUID]:
    """Resolve a list of card names to their database UUIDs.

    Args:
        pool: asyncpg connection pool.
        exclude: Card names to resolve.

    Returns:
        List of resolved card UUIDs.
    """
    if not exclude:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM cards WHERE LOWER(name) = ANY($1::text[])",
            [n.lower() for n in exclude],
        )
    return [r["id"] for r in rows]


async def build_stage(
    pool: asyncpg.Pool,
    ai_client: openai.AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
    deck_id: UUID,
    stage: str | None = None,
    target: int | None = None,
    exclude: list[str] | None = None,
) -> BuildResponse:
    """Generate card suggestions for a build stage using hybrid retrieval.

    Args:
        pool: asyncpg connection pool.
        ai_client: OpenAI async client (used for embeddings only).
        qdrant_client: Qdrant async client for semantic retrieval.
        deck_id: The deck's UUID.
        stage: Specific stage to generate for. If None, auto-advances to the next stage.
        target: Override target card count (determines how many candidates to return).
        exclude: Card names to exclude from suggestions (already shown to the user).

    Returns:
        BuildResponse with card suggestions for the stage.

    Raises:
        DeckNotFoundError: If the deck does not exist.
        ValueError: If an invalid stage name is provided.
    """
    deck = await deck_service.get_deck(pool, deck_id)
    if deck is None:
        raise DeckNotFoundError(f"Deck {deck_id} not found")

    resolved_stage, advance_deck_stage = _resolve_stage(deck.stage, stage)
    if resolved_stage == "complete":
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

    deck_card_ids = [c.card_id for c in deck.cards]
    exclude_ids = await _resolve_exclude_ids(pool, exclude)
    all_excluded = list({*deck_card_ids, *exclude_ids})

    query_text, query_tags = stage_retrieval_query(resolved_stage, deck.description)
    feedback_weights, user_profile = await asyncio.gather(
        _compute_feedback_weights(pool, deck.id, deck.owner_id),
        _load_user_profile(pool, deck.id, deck.owner_id),
    )
    deck_cmc_counts = _compute_deck_cmc_counts(deck)

    limit = target if target is not None else 20
    candidates = await retrieve_candidates(
        pool,
        ai_client,
        qdrant_client,
        query_text,
        query_tags,
        commander.color_identity,
        all_excluded,
        limit=limit,
        stage=resolved_stage,
        deck_cmc_counts=deck_cmc_counts,
        feedback_weights=feedback_weights,
        user_profile=user_profile,
    )
    _log.debug("Stage %s: retrieved %d candidates", resolved_stage, len(candidates))

    suggestions = [_card_from_retrieved(c, resolved_stage, query_tags) for c in candidates]

    if advance_deck_stage:
        await deck_service.update_deck(pool, deck_id, deck_service.DeckUpdate(stage=resolved_stage))

    return BuildResponse(
        stage=resolved_stage,
        stage_number=stage_number(resolved_stage),
        total_stages=_TOTAL_STAGES,
        suggestions=suggestions,
        unresolved=[],
    )


async def suggest_cards(
    pool: asyncpg.Pool,
    ai_client: openai.AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
    deck_id: UUID,
    prompt: str,
    count: int,
) -> SuggestResponse:
    """Return suggested cards matching a free-form prompt via hybrid retrieval.

    Args:
        pool: asyncpg connection pool.
        ai_client: OpenAI async client (used for embeddings only).
        qdrant_client: Qdrant async client for semantic retrieval.
        deck_id: The deck's UUID.
        prompt: Natural language description of desired cards.
        count: Number of cards to return.

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

    deck_card_ids = [c.card_id for c in deck.cards]
    query_tags = parse_query_tags(prompt)
    type_filter = parse_query_types(prompt)
    feedback_weights, user_profile = await asyncio.gather(
        _compute_feedback_weights(pool, deck.id, deck.owner_id),
        _load_user_profile(pool, deck.id, deck.owner_id),
    )
    deck_cmc_counts = _compute_deck_cmc_counts(deck)

    candidates = await retrieve_candidates(
        pool,
        ai_client,
        qdrant_client,
        prompt,
        query_tags,
        commander.color_identity,
        deck_card_ids,
        limit=count,
        deck_cmc_counts=deck_cmc_counts,
        feedback_weights=feedback_weights,
        user_profile=user_profile,
        type_filter=type_filter,
    )
    _log.debug("Suggest: retrieved %d candidates for prompt %r", len(candidates), prompt[:60])

    suggestions = [_card_from_retrieved(c, "theme", query_tags) for c in candidates]
    return SuggestResponse(suggestions=suggestions, unresolved=[])


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

    prefs, downvoted = await _load_prompt_context(pool, deck)
    system = _build_system_prompt(deck, commander, partner, prefs, downvoted)
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
