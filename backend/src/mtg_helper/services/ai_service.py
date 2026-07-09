"""AI deck building service using the Gemini API."""

import asyncio
import logging
from decimal import Decimal
from uuid import UUID

import asyncpg

from mtg_helper.models.ai import (
    BuildResponse,
    CardSuggestion,
    CollectionMembership,
    SuggestResponse,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.models.ranking_weights import RankingWeights
from mtg_helper.services import (
    card_service,
    collection_service,
    deck_service,
    preference_service,
    profile_service,
    ranking_weight_service,
)
from mtg_helper.services.deck_service import STAGES, next_stage, stage_number
from mtg_helper.services.retrieval_service import (
    CollectionFilter,
    PriceFilter,
    RetrievedCard,
    TypeFilter,
    card_qualifying_stages,
    parse_query_tags,
    parse_query_types,
    retrieve_candidates,
    stage_retrieval_query,
)

_log = logging.getLogger(__name__)
_TOTAL_STAGES = len(STAGES) - 1  # exclude "complete"
_FEEDBACK_WEIGHTS: dict[str, float] = {"up": 1.3, "down": 0.3}
_REJECT_BASE: float = 0.3  # weight = _REJECT_BASE ** reject_count
_REJECT_FLOOR: float = 0.02

_SIGNAL_LABELS: dict[str, str] = {
    "tag": "High tag relevance",
    "fts": "Strong text match",
}

# User-facing labels for the *source* badges shown on every suggestion card.
# Distinct from ``_SIGNAL_LABELS`` (which feed banger highlight reasons): these
# are the simple "where did this come from?" chips and cover signals beyond the
# original three (edhrec, moxfield, type filter).
_SOURCE_LABELS: dict[str, str] = {
    "tag": "Tags",
    "fts": "Text",
    "edhrec": "EDHREC",
    "edhrec_theme": "EDHREC Theme",
    "moxfield": "Moxfield",
    "type": "Type",
}

# Threshold for highlighting top picks (new scoring is [0, 1])
_BANGER_SCORE_THRESHOLD = 0.6
_BANGER_MIN_SIGNALS = 2

# Inclusion-weight thresholds that promote a card to the "hot" set even when
# it doesn't meet the multi-signal banger rule. EDHREC weights are the per-
# category boost (highsynergycards = 1.00, topcards = 0.85, etc.); 0.7 captures
# the strongest categories. Moxfield weights are ``count / _TOP_DECKS`` (10),
# so 0.5 means the card is in 5+ of the top-liked decks for the commander.
_HOT_EDHREC_THRESHOLD = 0.7
_HOT_MOXFIELD_THRESHOLD = 0.5


class DeckNotFoundError(ValueError):
    """Raised when the requested deck does not exist."""


def _compute_highlight_reasons(candidate: RetrievedCard) -> list[str] | None:
    """Return reasons that should fire the "hot" / fire-icon badge on a card.

    Triggers (any one is enough):
      * Multi-signal top hit: ≥2 retrieval signals AND composite score ≥ 0.6.
      * Hot on EDHREC: inclusion weight ≥ ``_HOT_EDHREC_THRESHOLD`` — present
        in EDHREC's strong categories (highsynergy / topcards / combos).
      * In majority of top Moxfield decks: weight ≥ ``_HOT_MOXFIELD_THRESHOLD``
        — appears in at least half of the cached top-liked Moxfield decks.

    Args:
        candidate: Retrieved card with score, signals, and inclusion weights.

    Returns:
        List of human-readable reason strings, or None when nothing fires.
    """
    reasons: list[str] = []

    enough_signals = len(candidate.signals) >= _BANGER_MIN_SIGNALS
    if enough_signals and candidate.score >= _BANGER_SCORE_THRESHOLD:
        reasons.extend(_SIGNAL_LABELS[s] for s in candidate.signals if s in _SIGNAL_LABELS)

    if candidate.edhrec_weight >= _HOT_EDHREC_THRESHOLD:
        reasons.append("Hot on EDHREC")
    if candidate.moxfield_weight >= _HOT_MOXFIELD_THRESHOLD:
        reasons.append("In majority of top Moxfield decks")

    if not reasons:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _sources_for(candidate: RetrievedCard) -> list[str]:
    """Map a candidate's signals to user-facing source labels.

    Preserves ``_SOURCE_LABELS`` ordering so badges render in a stable visual
    sequence regardless of the order signals were appended internally.
    """
    have = set(candidate.signals)
    return [_SOURCE_LABELS[s] for s in _SOURCE_LABELS if s in have]


def card_from_retrieved(
    card: RetrievedCard,
    stage: str,
    query_tags: list[str],
    ownership_map: dict[UUID, list[CollectionMembership]] | None = None,
) -> CardSuggestion:
    """Build a CardSuggestion directly from a RetrievedCard without LLM involvement.

    Args:
        card: Retrieved card with scoring data.
        stage: Build stage name (used for category label).
        query_tags: Tags used in the retrieval query (used to derive synergies).
        ownership_map: Optional map from scryfall_id to list of collections that own it.

    Returns:
        CardSuggestion populated from retrieval signals.
    """
    category = stage
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
    owned_in = (ownership_map or {}).get(card.scryfall_id, [])
    qualifying_stages = card_qualifying_stages(card.tags, card.type_line)
    if stage not in qualifying_stages:
        qualifying_stages.append(stage)

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
        color_identity=list(card.color_identity or []),
        category=category,
        reasoning=reasoning,
        synergies=synergies,
        highlight_reasons=_compute_highlight_reasons(card),
        price_eur_cents=card.price_eur_cents,
        owned_in=owned_in,
        qualifying_stages=qualifying_stages,
        sources=_sources_for(card),
    )


async def _compute_feedback_weights(
    pool: asyncpg.Pool,
    deck_id: UUID,
    account_id: UUID | None,
) -> dict[UUID, float] | None:
    """Compute per-card score multipliers from feedback and preferences.

    Returns None if feedback boosting is disabled or no account is provided.
    Weights are clamped to [0.05, 2.0].

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID (for per-deck thumbs up/down).
        account_id: The account UUID (for account-level pet/avoid weights).

    Returns:
        Dict mapping card UUID to combined weight, or None to skip weighting.
    """
    if account_id is None:
        return None
    if not await preference_service.is_feedback_boosting_enabled(pool, account_id):
        return None

    async with pool.acquire() as conn:
        feedback_rows = await conn.fetch(
            "SELECT card_id, feedback, reject_count FROM deck_feedback WHERE deck_id = $1",
            deck_id,
        )

    weights: dict[UUID, float] = {}
    for row in feedback_rows:
        if row["feedback"] == "reject":
            count = max(1, row["reject_count"])
            weights[row["card_id"]] = max(_REJECT_FLOOR, _REJECT_BASE**count)
        else:
            weights[row["card_id"]] = _FEEDBACK_WEIGHTS.get(row["feedback"], 0.3)

    pref_weights = await preference_service.get_card_preference_weights(pool, account_id)
    for card_id, pref_mult in pref_weights.items():
        weights[card_id] = weights.get(card_id, 1.0) * pref_mult

    for card_id in weights:
        weights[card_id] = max(0.05, min(2.0, weights[card_id]))

    return weights if weights else None


async def _load_user_profile(
    pool: asyncpg.Pool,
    deck_id: UUID,
    account_id: UUID | None,
    email: str | None,
) -> "profile_service.UserProfile | None":
    """Load the cross-deck user profile if the feature is enabled.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck being built (excluded from profile).
        account_id: The account UUID (for preference flag).
        email: The owner's email (canonical deck-ownership key).

    Returns:
        UserProfile if enabled and sufficient deck history exists, else None.
    """
    if account_id is None or email is None:
        return None
    if not await preference_service.is_user_profile_enabled(pool, account_id):
        return None
    return await profile_service.get_user_profile(pool, email, deck_id)


async def _load_ranking_weights(
    pool: asyncpg.Pool,
    account_id: UUID | None,
) -> RankingWeights | None:
    """Load per-user ranking weights, returning None if no account.

    Args:
        pool: asyncpg connection pool.
        account_id: The account UUID, or None for anonymous decks.

    Returns:
        RankingWeights if account exists, else None (uses defaults in retrieval).
    """
    if account_id is None:
        return None
    try:
        result = await ranking_weight_service.get_weights(pool, account_id)
        return RankingWeights(
            semantic=result.semantic,
            synergy=result.synergy,
            popularity=result.popularity,
            personal=result.personal,
            deck_inclusion=result.deck_inclusion,
            moxfield_inclusion=result.moxfield_inclusion,
            trusted_quota=result.trusted_quota,
        )
    except ranking_weight_service.AccountNotFoundError:
        return None


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


async def _resolve_collection_filter(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    request_collection_ids: list[UUID] | None,
) -> CollectionFilter | None:
    """Resolve the collection filter for a request.

    A per-request ``collection_ids`` list overrides the deck's stored selection.
    Empty list or empty deck selection → no filter (unrestricted suggestions).
    Non-empty → candidates restricted to the union of owned cards across the listed
    collections.

    Args:
        pool: asyncpg connection pool.
        deck: Already-fetched deck; avoids a second SELECT.
        request_collection_ids: Optional per-request override.

    Returns:
        A CollectionFilter when ownership filtering is active, otherwise None.
    """
    ids: list[UUID] = (
        list(request_collection_ids)
        if request_collection_ids is not None
        else list(deck.suggestion_collection_ids)
    )
    if not ids:
        return None
    owned = await collection_service.get_owned_card_ids_for_collections(pool, ids)
    return CollectionFilter(owned_card_ids=owned)


_ALLOWED_CARD_TYPES: frozenset[str] = frozenset(
    {"Artifact", "Creature", "Enchantment", "Instant", "Land", "Planeswalker", "Sorcery", "Battle"}
)
_ALLOWED_SUBTYPES: frozenset[str] = frozenset(
    {"Equipment", "Aura", "Vehicle", "Saga", "Background", "Class", "Food", "Treasure", "Clue"}
)


def _canonicalize(values: list[str] | None, allow: frozenset[str]) -> list[str]:
    """Title-case incoming filter terms and keep only those in the allow-list."""
    if not values:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        canonical = v.strip().title()
        if canonical in allow and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def _resolve_structured_type_filter(
    card_types: list[str] | None,
    subtypes: list[str] | None,
) -> TypeFilter | None:
    """Build a strict, AND-across-categories TypeFilter from request fields.

    Returns None when both lists are empty after canonicalization.
    """
    canonical_types = _canonicalize(card_types, _ALLOWED_CARD_TYPES)
    canonical_subs = _canonicalize(subtypes, _ALLOWED_SUBTYPES)
    if not canonical_types and not canonical_subs:
        return None
    return TypeFilter(
        card_types=canonical_types,
        subtypes=canonical_subs,
        strict=True,
        match_all_categories=True,
    )


def _merge_type_filters(
    primary: TypeFilter | None,
    secondary: TypeFilter | None,
) -> TypeFilter | None:
    """Union two TypeFilters; primary's strict/match_all flags win when set."""
    if primary is None:
        return secondary
    if secondary is None:
        return primary

    def _union(a: list[str], b: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in [*a, *b]:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    return TypeFilter(
        card_types=_union(primary.card_types, secondary.card_types),
        subtypes=_union(primary.subtypes, secondary.subtypes),
        keywords=_union(primary.keywords, secondary.keywords),
        traits=_union(primary.traits, secondary.traits),
        token_types=_union(primary.token_types, secondary.token_types),
        strict=primary.strict or secondary.strict,
        match_all_categories=primary.match_all_categories or secondary.match_all_categories,
    )


def _resolve_price_filter(max_cents: int | None, min_cents: int | None) -> PriceFilter | None:
    """Resolve the per-request price filter (cap and/or floor).

    Returns None when neither a cap nor a positive floor is active.
    """
    cap = max_cents if max_cents is not None and max_cents > 0 else None
    floor = min_cents if min_cents is not None and min_cents > 0 else 0
    if cap is None and floor == 0:
        return None
    return PriceFilter(max_cents=cap, min_cents=floor)


async def build_stage(
    pool: asyncpg.Pool,
    deck_id: UUID,
    account_id: UUID,
    email: str,
    stage: str | None = None,
    target: int | None = None,
    offset: int = 0,
    exclude: list[str] | None = None,
    collection_ids: list[UUID] | None = None,
    max_price_cents: int | None = None,
    min_price_cents: int | None = None,
    card_types: list[str] | None = None,
    subtypes: list[str] | None = None,
    theme_tag: str | None = None,
) -> BuildResponse:
    """Generate card suggestions for a build stage using hybrid retrieval.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        stage: Specific stage to generate for. If None, auto-advances to the next stage.
        target: Override target card count (determines how many candidates to return).
        offset: Pagination offset into the ranked candidate list. Used by
            Load More to fetch the next page without re-sending shown names.
        exclude: Persistent rejections (thumbs-down / per-session rejects). Not
            used for pagination — that's handled via ``offset``.
        collection_ids: Per-request override. When provided, replaces the deck's
            stored ``suggestion_collection_ids`` for this call only.
        theme_tag: Active theme keyword when building the theme stage.

    Returns:
        BuildResponse with card suggestions for the stage.

    Raises:
        DeckNotFoundError: If the deck does not exist.
        ValueError: If an invalid stage name is provided.
    """
    deck = await deck_service.get_deck(pool, deck_id, email)
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
    commander_ids = [deck.commander_id] + ([deck.partner_id] if deck.partner_id else [])
    avoid_ids = await preference_service.get_avoid_card_ids(pool, account_id)
    all_excluded = list({*deck_card_ids, *exclude_ids, *commander_ids, *avoid_ids})

    query_text, base_tags = stage_retrieval_query(resolved_stage, deck.description)
    deck_archetype_tags = list(deck.archetype_tags or [])
    if resolved_stage == "theme" and deck_archetype_tags:
        active_theme_tag = (
            theme_tag if theme_tag in deck_archetype_tags else deck_archetype_tags[0]
        )
        query_tags = [active_theme_tag]
        query_text = f"{query_text} {active_theme_tag.replace('_', ' ')}"
        prefer_keywords = True
    elif deck_archetype_tags:
        # Union the explicit chips with the stage's default tags so e.g. the
        # ramp stage still pulls ramp cards while the deck's archetype tilts
        # which ramp pieces win the tiebreaker.
        seen: set[str] = set()
        query_tags = [
            t for t in (*deck_archetype_tags, *base_tags) if not (t in seen or seen.add(t))
        ]
        prefer_keywords = True
    else:
        query_tags = base_tags
        prefer_keywords = False

    feedback_weights, user_profile = await asyncio.gather(
        _compute_feedback_weights(pool, deck.id, account_id),
        _load_user_profile(pool, deck.id, account_id, email),
    )
    ranking_weights = await _load_ranking_weights(pool, account_id)
    deck_cmc_counts = _compute_deck_cmc_counts(deck)
    collection_filter = await _resolve_collection_filter(pool, deck, collection_ids)
    price_filter = _resolve_price_filter(max_price_cents, min_price_cents)
    type_filter = _resolve_structured_type_filter(card_types, subtypes)

    limit = target if target is not None else 20
    candidates = await retrieve_candidates(
        pool,
        query_text,
        query_tags,
        commander.color_identity,
        all_excluded,
        limit=limit,
        offset=offset,
        stage=resolved_stage,
        deck_cmc_counts=deck_cmc_counts,
        feedback_weights=feedback_weights,
        user_profile=user_profile,
        ranking_weights=ranking_weights,
        collection_filter=collection_filter,
        price_filter=price_filter,
        commander_id=deck.commander_id,
        bracket=deck.bracket,
        type_filter=type_filter,
        prefer_keywords=prefer_keywords,
    )
    _log.debug("Stage %s: retrieved %d candidates", resolved_stage, len(candidates))

    if resolved_stage == "lands":
        candidates = [c for c in candidates if "Land" in (c.type_line or "")]
    ownership_map = await collection_service.build_ownership_map(
        pool, account_id, [c.scryfall_id for c in candidates]
    )
    suggestions = [
        card_from_retrieved(c, resolved_stage, query_tags, ownership_map) for c in candidates
    ]

    if advance_deck_stage:
        await deck_service.update_deck(
            pool, deck_id, deck_service.DeckUpdate(stage=resolved_stage)
        )

    return BuildResponse(
        stage=resolved_stage,
        stage_number=stage_number(resolved_stage),
        total_stages=_TOTAL_STAGES,
        suggestions=suggestions,
        unresolved=[],
    )


async def suggest_cards(
    pool: asyncpg.Pool,
    deck_id: UUID,
    account_id: UUID,
    email: str,
    prompt: str,
    count: int,
    collection_ids: list[UUID] | None = None,
    max_price_cents: int | None = None,
    min_price_cents: int | None = None,
    card_types: list[str] | None = None,
    subtypes: list[str] | None = None,
) -> SuggestResponse:
    """Return suggested cards matching a free-form prompt via structured retrieval.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        prompt: Natural language description of desired cards.
        count: Number of cards to return.
        collection_ids: Per-request override. When provided, replaces the deck's
            stored ``suggestion_collection_ids`` for this call only.

    Returns:
        SuggestResponse with validated suggestions.

    Raises:
        DeckNotFoundError: If the deck does not exist.
    """
    deck = await deck_service.get_deck(pool, deck_id, email)
    if deck is None:
        raise DeckNotFoundError(f"Deck {deck_id} not found")

    commander = await card_service.get_card_by_id(pool, deck.commander_id)
    if commander is None:
        raise DeckNotFoundError(f"Commander card not found for deck {deck_id}")

    commander_ids = [deck.commander_id] + ([deck.partner_id] if deck.partner_id else [])
    deck_card_ids = list({*(c.card_id for c in deck.cards), *commander_ids})
    parsed_tags = parse_query_tags(prompt)
    deck_archetype_tags = list(deck.archetype_tags or [])
    seen: set[str] = set()
    query_tags = [
        t for t in (*deck_archetype_tags, *parsed_tags) if not (t in seen or seen.add(t))
    ]
    prefer_keywords = bool(deck_archetype_tags)
    parsed_filter = parse_query_types(prompt)
    structured_filter = _resolve_structured_type_filter(card_types, subtypes)
    type_filter = _merge_type_filters(structured_filter, parsed_filter)
    feedback_weights, user_profile = await asyncio.gather(
        _compute_feedback_weights(pool, deck.id, account_id),
        _load_user_profile(pool, deck.id, account_id, email),
    )
    deck_cmc_counts = _compute_deck_cmc_counts(deck)
    collection_filter = await _resolve_collection_filter(pool, deck, collection_ids)
    price_filter = _resolve_price_filter(max_price_cents, min_price_cents)

    candidates = await retrieve_candidates(
        pool,
        prompt,
        query_tags,
        commander.color_identity,
        deck_card_ids,
        limit=count,
        deck_cmc_counts=deck_cmc_counts,
        feedback_weights=feedback_weights,
        user_profile=user_profile,
        type_filter=type_filter,
        collection_filter=collection_filter,
        price_filter=price_filter,
        commander_id=deck.commander_id,
        bracket=deck.bracket,
        prefer_keywords=prefer_keywords,
    )
    _log.debug("Suggest: retrieved %d candidates for prompt %r", len(candidates), prompt[:60])

    ownership_map = await collection_service.build_ownership_map(
        pool, account_id, [c.scryfall_id for c in candidates]
    )
    suggestions = [card_from_retrieved(c, "theme", query_tags, ownership_map) for c in candidates]
    return SuggestResponse(suggestions=suggestions, unresolved=[])
