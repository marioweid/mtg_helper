"""Mana-base analysis: per-color pip vs. source counts and land-fix suggestions.

The analyzer is a pure function over a ``DeckDetailResponse``. Color production
for lands is approximated from ``cards.color_identity`` (the Scryfall data we
already store); ``cards.produced_mana`` is not yet imported, so utility lands
like Reflecting Pool with empty color identity will read as colorless. Good
enough for v1 — fetch/dual/shock classification is deferred.
"""

import re
from uuid import UUID

import asyncpg
from qdrant_client import AsyncQdrantClient

from mtg_helper.models.ai import ColorStatus, ManaBaseReport, ManaFixResponse
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.services import collection_service
from mtg_helper.services.ai_service import card_from_retrieved
from mtg_helper.services.llm_client import LLMClient
from mtg_helper.services.retrieval_service import RetrievedCard, retrieve_candidates

_COLORS: tuple[str, ...] = ("W", "U", "B", "R", "G")
_SYMBOL_RE = re.compile(r"\{([^}]+)\}")
_LAND_SUGGEST_LIMIT = 12


def _is_land(card: DeckCardItem) -> bool:
    return "Land" in (card.type_line or "")


def parse_pips(mana_cost: str | None) -> dict[str, float]:
    """Count colored pips in a single mana cost, by color.

    Hybrid (``{W/U}``) contributes 0.5 to each side. Phyrexian (``{W/P}``) and
    twobrid (``{2/W}``) contribute 0.5 to the colored half — both are usually
    paid in non-colored ways, but they still bias the deck toward that color.
    Generic, X, and snow symbols don't count.

    Args:
        mana_cost: Scryfall-format mana cost string, e.g. ``"{2}{W}{U/B}"``.

    Returns:
        Mapping color letter -> total pip count (floats allowed).
    """
    pips: dict[str, float] = {c: 0.0 for c in _COLORS}
    if not mana_cost:
        return pips
    for symbol in _SYMBOL_RE.findall(mana_cost):
        if symbol in _COLORS:
            pips[symbol] += 1.0
            continue
        if "/" not in symbol:
            continue
        parts = symbol.split("/")
        colors = [p for p in parts if p in _COLORS]
        if len(colors) == 2:
            for c in colors:
                pips[c] += 0.5
        elif len(colors) == 1:
            # W/P (phyrexian) or 2/W (twobrid) — half-weight contribution.
            pips[colors[0]] += 0.5
    return pips


def _floor_for_pip_count(pip_count: float) -> int:
    """Minimum reasonable sources for a given total colored pip count."""
    if pip_count <= 0:
        return 0
    if pip_count <= 5:
        return 6
    if pip_count <= 15:
        return 10
    return 14


def _compute_target(pip_count: float, total_pips: float, total_lands: int) -> int:
    """Target source count for one color.

    Uses proportional allocation of the land base by share of total colored pips,
    floored at a per-band minimum so trivially small splashes still get a few
    sources.
    """
    if pip_count <= 0 or total_lands <= 0:
        return 0
    proportional = round(total_lands * pip_count / total_pips) if total_pips else 0
    return min(total_lands, max(proportional, _floor_for_pip_count(pip_count)))


def _land_sources(card: DeckCardItem) -> set[str]:
    """Colors a land card produces. Heuristic: ``color_identity`` as proxy."""
    if not _is_land(card):
        return set()
    return set(card.color_identity or [])


def analyze_mana_base(deck: DeckDetailResponse) -> ManaBaseReport:
    """Analyze the deck's mana base and report deficits per color.

    Skips the commander and partner (color identity already drives what's
    allowed). Sums pip counts on non-land cards (weighted by quantity) and
    source counts on land cards (likewise quantity-weighted).
    """
    color_identity = deck.commander_color_identity
    pips_by_color: dict[str, float] = {c: 0.0 for c in _COLORS}
    sources_by_color: dict[str, int] = {c: 0 for c in _COLORS}
    total_lands = 0
    for card in deck.cards:
        qty = max(1, card.quantity)
        if _is_land(card):
            total_lands += qty
            for c in _land_sources(card):
                sources_by_color[c] += qty
        else:
            card_pips = parse_pips(card.mana_cost)
            for c, p in card_pips.items():
                pips_by_color[c] += p * qty

    total_pips = sum(pips_by_color[c] for c in color_identity)
    statuses: list[ColorStatus] = []
    for color in color_identity:
        pip = pips_by_color.get(color, 0.0)
        sources = sources_by_color.get(color, 0)
        target = _compute_target(pip, total_pips, total_lands)
        deficit = max(0, target - sources)
        statuses.append(
            ColorStatus(
                color=color,
                pip_count=round(pip, 2),
                source_count=sources,
                target=target,
                deficit=deficit,
            )
        )
    return ManaBaseReport(
        total_lands=total_lands,
        total_colored_pips=round(total_pips, 2),
        colors=statuses,
    )


def _bucket_by_color(
    candidates: list[RetrievedCard], deficient: list[str]
) -> dict[str, list[RetrievedCard]]:
    """Bucket each candidate under every deficient color it can produce."""
    return {
        color: [c for c in candidates if color in (c.color_identity or [])] for color in deficient
    }


def _round_robin_pick(
    buckets: dict[str, list[RetrievedCard]],
    order: list[str],
    limit: int,
) -> list[RetrievedCard]:
    """Take one card per bucket per pass until ``limit`` reached or all empty."""
    picked: list[RetrievedCard] = []
    seen: set[UUID] = set()
    while len(picked) < limit:
        progress = False
        for color in order:
            stream = buckets[color]
            while stream and stream[0].id in seen:
                stream.pop(0)
            if not stream or len(picked) >= limit:
                continue
            candidate = stream.pop(0)
            seen.add(candidate.id)
            picked.append(candidate)
            progress = True
        if not progress:
            break
    return picked


def _pick_lands_for_deficits(
    candidates: list[RetrievedCard], deficient: list[str]
) -> list[RetrievedCard]:
    """Round-robin pick top lands producing each deficient color.

    Each candidate is bucketed under every deficient color it produces (using
    ``color_identity`` as the production proxy). We then round-robin across
    colors, taking the next-best card per color, until ``_LAND_SUGGEST_LIMIT``
    is reached. Lands producing none of the deficient colors are dropped.
    """
    if not deficient:
        return []
    buckets = _bucket_by_color(candidates, deficient)
    return _round_robin_pick(buckets, deficient, _LAND_SUGGEST_LIMIT)


async def suggest_mana_fix(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    deck: DeckDetailResponse,
    account_id: UUID | None,
) -> ManaFixResponse:
    """Analyze the deck and return both the report and a land-fix shortlist.

    When no color is deficient, returns an empty suggestions list.
    """
    report = analyze_mana_base(deck)
    deficient = [c.color for c in report.colors if c.deficit > 0]
    if not deficient:
        return ManaFixResponse(report=report, suggestions=[], unresolved=[])

    deck_card_ids = [c.card_id for c in deck.cards]
    commander_ids = [deck.commander_id] + ([deck.partner_id] if deck.partner_id else [])
    excluded = list({*deck_card_ids, *commander_ids})

    candidates = await retrieve_candidates(
        pool,
        ai_client,
        qdrant_client,
        query_text="mana fixing lands color sources",
        query_tags=["lands"],
        commander_color_identity=deck.commander_color_identity,
        deck_card_ids=excluded,
        limit=40,
        stage="lands",
        commander_id=deck.commander_id,
        bracket=deck.bracket,
    )
    candidates = [c for c in candidates if "Land" in (c.type_line or "")]
    picked = _pick_lands_for_deficits(candidates, deficient)

    ownership_map = await collection_service.build_ownership_map(
        pool, account_id, [c.scryfall_id for c in picked]
    )
    suggestions = [card_from_retrieved(c, "lands", ["lands"], ownership_map) for c in picked]
    return ManaFixResponse(report=report, suggestions=suggestions, unresolved=[])
