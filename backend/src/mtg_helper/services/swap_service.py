"""Budget swap finder: cheaper alternatives ranked by function similarity.

The similarity heuristic is a deterministic pure function over four signals —
tag overlap (Jaccard), primary-type match, CMC proximity, color-identity
containment. No LLM call. Candidates come from the structured retrieval
pipeline with a price ceiling derived from the source card.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import asyncpg

from mtg_helper.models.ai import CardSuggestion
from mtg_helper.models.cards import CardResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.models.swaps import SwapCandidate, SwapResponse
from mtg_helper.services import card_service, collection_service
from mtg_helper.services.ai_service import card_from_retrieved
from mtg_helper.services.retrieval_service import (
    PriceFilter,
    RetrievedCard,
    TypeFilter,
    retrieve_candidates,
)

_PRIMARY_TYPES: tuple[str, ...] = (
    "Creature",
    "Planeswalker",
    "Instant",
    "Sorcery",
    "Artifact",
    "Enchantment",
    "Battle",
    "Land",
)
_MIN_SWAPPABLE_PRICE_CENTS = 50
_RETRIEVAL_POOL = 40


class SwapError(ValueError):
    """Raised when a swap cannot be computed (basic land, missing price, etc.)."""


@dataclass(frozen=True)
class _SourceCard:
    """Minimal source-card view used by similarity scoring."""

    card_id: UUID
    name: str
    mana_cost: str | None
    cmc: float
    type_line: str
    oracle_text: str
    color_identity: frozenset[str]
    tags: tuple[str, ...]
    price_eur_cents: int | None


def _primary_type(type_line: str | None) -> str | None:
    """Return the first primary type word found in a type line."""
    if not type_line:
        return None
    text = type_line.split("—")[0]
    for t in _PRIMARY_TYPES:
        if t in text:
            return t
    return None


def _tag_jaccard(a: list[str] | tuple[str, ...], b: list[str] | tuple[str, ...]) -> float:
    """Jaccard similarity over two tag iterables. Returns 1.0 if both empty."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def _type_match(source_line: str | None, cand_line: str | None) -> float:
    """Primary-type match score: 1.0 same, 0.5 supertype-only overlap, 0 mismatch."""
    s_primary = _primary_type(source_line)
    c_primary = _primary_type(cand_line)
    if s_primary is None or c_primary is None:
        return 0.0
    if s_primary == c_primary:
        return 1.0
    # Soft credit for permanent vs spell overlap.
    permanents = {"Creature", "Artifact", "Enchantment", "Planeswalker", "Battle"}
    spells = {"Instant", "Sorcery"}
    if (s_primary in permanents and c_primary in permanents) or (
        s_primary in spells and c_primary in spells
    ):
        return 0.5
    return 0.0


def _cmc_proximity(source_cmc: float, cand_cmc: float | Decimal | None) -> float:
    """Distance-based proximity: 1.0 same CMC, 0.0 at delta >= 4."""
    if cand_cmc is None:
        return 0.0
    delta = abs(float(cand_cmc) - source_cmc)
    return max(0.0, 1.0 - min(delta / 4.0, 1.0))


def _color_subset(
    source_ci: frozenset[str] | list[str], cand_ci: frozenset[str] | list[str]
) -> float:
    """1.0 if candidate identity ⊆ source identity, 0.5 if overlap, 0 else."""
    sset = set(source_ci)
    cset = set(cand_ci)
    if not cset:
        return 1.0  # colorless fits anywhere
    if cset.issubset(sset):
        return 1.0
    if sset & cset:
        return 0.5
    return 0.0


def function_similarity(source: _SourceCard, cand: RetrievedCard) -> dict[str, float]:
    """Compute weighted similarity breakdown for a candidate against the source.

    Weights (sum to 1.0):
        tag overlap     → 0.40
        primary type    → 0.25
        CMC proximity   → 0.20
        color subset    → 0.15

    Args:
        source: Source-card snapshot.
        cand: Candidate retrieved card.

    Returns:
        Dict with per-component scores plus the weighted ``total`` in [0, 1].
    """
    tag = _tag_jaccard(source.tags, cand.tags)
    typ = _type_match(source.type_line, cand.type_line)
    cmc = _cmc_proximity(source.cmc, cand.cmc)
    col = _color_subset(source.color_identity, cand.color_identity or [])
    total = 0.40 * tag + 0.25 * typ + 0.20 * cmc + 0.15 * col
    return {"tag": tag, "type": typ, "cmc": cmc, "color": col, "total": total}


def _type_filter_for(source_type_line: str | None) -> TypeFilter | None:
    """Build a soft TypeFilter that biases retrieval toward the same primary type."""
    primary = _primary_type(source_type_line)
    if primary is None:
        return None
    return TypeFilter(card_types=[primary], subtypes=[], strict=False)


async def _load_source(pool: asyncpg.Pool, card_id: UUID) -> _SourceCard:
    """Load the source card with its tag list and EUR price.

    Raises:
        SwapError: when the card isn't found, is a basic land, or has no
            meaningful EUR price (under ``_MIN_SWAPPABLE_PRICE_CENTS``).
    """
    card: CardResponse | None = await card_service.get_card_by_id(pool, card_id)
    if card is None:
        raise SwapError(f"Card {card_id} not found")
    type_line = card.type_line or ""
    if "Basic Land" in type_line:
        raise SwapError("Cannot find swaps for basic lands")
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT tags FROM cards WHERE id = $1", card_id)
    tags = tuple(row["tags"] or []) if row else ()
    eur_str = (card.prices or {}).get("eur")
    price_cents: int | None = None
    if eur_str is not None:
        try:
            price_cents = int(round(float(eur_str) * 100))
        except (TypeError, ValueError):
            price_cents = None
    if price_cents is not None and price_cents < _MIN_SWAPPABLE_PRICE_CENTS:
        raise SwapError("Source card is already cheap; no swap target")
    return _SourceCard(
        card_id=card.id,
        name=card.name,
        mana_cost=card.mana_cost,
        cmc=float(card.cmc) if card.cmc is not None else 0.0,
        type_line=type_line,
        oracle_text=card.oracle_text or "",
        color_identity=frozenset(card.color_identity or []),
        tags=tags,
        price_eur_cents=price_cents,
    )


def _query_text_for(source: _SourceCard) -> str:
    """Build a retrieval query from source card name + truncated oracle text."""
    snippet = source.oracle_text[:200] if source.oracle_text else ""
    return f"{source.name}. {snippet}".strip()


def _resolve_price_ceiling(source: _SourceCard, requested: int | None) -> int | None:
    """Pick the effective max price for the price filter.

    Caller's value wins. Otherwise: source price minus 1 cent so we only
    return strictly cheaper candidates.
    """
    if requested is not None:
        return requested
    if source.price_eur_cents is None:
        return None
    return max(0, source.price_eur_cents - 1)


def _to_swap_candidate(
    cand: RetrievedCard,
    base: CardSuggestion,
    source_price_cents: int | None,
    breakdown: dict[str, float],
) -> SwapCandidate:
    """Wrap a CardSuggestion with swap-specific price/loss metadata."""
    cand_cents = cand.price_eur_cents
    if source_price_cents is not None and cand_cents is not None:
        delta = cand_cents - source_price_cents
    else:
        delta = 0
    loss_pct = round((1.0 - breakdown["total"]) * 100)
    return SwapCandidate(
        scryfall_id=base.scryfall_id,
        name=base.name,
        mana_cost=base.mana_cost,
        type_line=base.type_line,
        image_uri=base.image_uri,
        oracle_text=base.oracle_text,
        power=base.power,
        toughness=base.toughness,
        rarity=base.rarity,
        cmc=base.cmc,
        color_identity=base.color_identity,
        category=base.category,
        reasoning=base.reasoning,
        synergies=base.synergies,
        highlight_reasons=base.highlight_reasons,
        price_eur_cents=base.price_eur_cents,
        owned_in=base.owned_in,
        qualifying_stages=base.qualifying_stages,
        sources=base.sources,
        game_changer=base.game_changer,
        price_delta_cents=delta,
        function_loss_pct=max(0, min(100, loss_pct)),
        similarity_breakdown=breakdown,
    )


async def find_budget_swaps(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    card_id: UUID,
    *,
    max_price_cents: int | None,
    account_id: UUID | None,
    limit: int = 5,
) -> SwapResponse:
    """Find ``limit`` cheaper alternatives for ``card_id`` ranked by similarity.

    Args:
        pool: asyncpg connection pool.
        deck: The deck containing the source card.
        card_id: Internal UUID of the card to swap.
        max_price_cents: Hard cap on candidate price. None → source price - 1.
        account_id: Caller's account (for ownership annotations).
        limit: How many candidates to return.

    Returns:
        SwapResponse with source info and ranked candidates.

    Raises:
        SwapError: when the source card is unswappable (basic land, missing,
            or already cheap enough to skip).
    """
    source = await _load_source(pool, card_id)
    ceiling = _resolve_price_ceiling(source, max_price_cents)
    if ceiling is not None and ceiling <= 0:
        return SwapResponse(
            source_card_id=source.card_id,
            source_price_cents=source.price_eur_cents,
            candidates=[],
        )

    deck_card_ids = list({c.card_id for c in deck.cards} | {source.card_id})
    price_filter = PriceFilter(max_cents=ceiling, min_cents=0)

    candidates = await retrieve_candidates(
        pool,
        query_text=_query_text_for(source),
        query_tags=list(source.tags),
        commander_color_identity=deck.commander_color_identity,
        deck_card_ids=deck_card_ids,
        limit=_RETRIEVAL_POOL,
        type_filter=_type_filter_for(source.type_line),
        price_filter=price_filter,
        commander_id=deck.commander_id,
        bracket=deck.bracket,
    )

    scored = [(c, function_similarity(source, c)) for c in candidates]
    scored.sort(key=lambda x: x[1]["total"], reverse=True)
    top = scored[:limit]

    ownership_map = await collection_service.build_ownership_map(
        pool, account_id, [c.scryfall_id for c, _ in top]
    )
    suggestions: list[SwapCandidate] = []
    for cand, breakdown in top:
        base = card_from_retrieved(cand, "swap", list(source.tags), ownership_map)
        suggestions.append(_to_swap_candidate(cand, base, source.price_eur_cents, breakdown))

    return SwapResponse(
        source_card_id=source.card_id,
        source_price_cents=source.price_eur_cents,
        candidates=suggestions,
    )
