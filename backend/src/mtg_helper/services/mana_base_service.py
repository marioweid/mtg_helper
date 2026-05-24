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

from mtg_helper.models.ai import ColorStatus, ManaBaseReport, ManaFixResponse, RiskyCard
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.services import collection_service
from mtg_helper.services.ai_service import card_from_retrieved
from mtg_helper.services.llm_client import LLMClient
from mtg_helper.services.retrieval_service import PriceFilter, RetrievedCard, retrieve_candidates

_COLORS: tuple[str, ...] = ("W", "U", "B", "R", "G")
_SYMBOL_RE = re.compile(r"\{([^}]+)\}")
_LAND_SUGGEST_LIMIT = 12
_RAMP_TAGS: frozenset[str] = frozenset({"ramp", "fast_mana"})
_RISKY_PER_COLOR_CAP = 5
_LAND_REC_MIN = 32
_LAND_REC_MAX = 42

# Frank Karsten 99-card singleton table: sources needed for ~90% probability of
# casting a spell with ``pip`` solid colored pips on ``turn``, on the play.
# Rows = turn (1..6), cols = pip count (1=single, 2=double, 3=triple).
# Values of 0 mean "impossible by that turn" (e.g. {U}{U}{U} on turn 2).
_KARSTEN_99: dict[tuple[int, int], int] = {
    (1, 1): 19, (1, 2): 0,  (1, 3): 0,
    (2, 1): 17, (2, 2): 0,  (2, 3): 0,
    (3, 1): 16, (3, 2): 21, (3, 3): 0,
    (4, 1): 15, (4, 2): 20, (4, 3): 23,
    (5, 1): 14, (5, 2): 19, (5, 3): 22,
    (6, 1): 13, (6, 2): 18, (6, 3): 22,
}  # fmt: skip


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


def _solid_pips(mana_cost: str | None) -> dict[str, int]:
    """Count *only* solid colored pips in a cost (no hybrid or phyrexian).

    Solid pips drive Karsten's turn-N analysis because they must be paid in
    that specific color. Hybrid pips can be paid by either side and don't
    create the same color-source pressure.
    """
    pips: dict[str, int] = {c: 0 for c in _COLORS}
    if not mana_cost:
        return pips
    for symbol in _SYMBOL_RE.findall(mana_cost):
        if symbol in _COLORS:
            pips[symbol] += 1
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


def _karsten_requirement(turn: int, pip_count: int) -> int:
    """Karsten lookup with clamping. Returns 0 when the combo is unreachable."""
    turn_c = max(1, min(6, turn))
    pip_c = max(1, min(3, pip_count))
    return _KARSTEN_99.get((turn_c, pip_c), 0)


def _recommend_land_count(avg_cmc: float, ramp_count: int) -> int:
    """Karsten-derived total-land recommendation, clamped to [32, 42].

    Formula: ``31.42 + 3.13 * avg_cmc - 0.28 * ramp_count``. Source:
    Frank Karsten's land-count study, adjusted for typical commander decks.
    Clamped: even very low-CMC ramp-heavy decks should run at least 32, and
    even very high-CMC ramp-light decks rarely benefit beyond 42.
    """
    raw = 31.42 + 3.13 * avg_cmc - 0.28 * ramp_count
    return max(_LAND_REC_MIN, min(_LAND_REC_MAX, round(raw)))


def _avg_nonland_cmc(deck: DeckDetailResponse) -> float:
    """Quantity-weighted average CMC of non-land cards (excluding commander)."""
    total_cmc = 0.0
    total_qty = 0
    for card in deck.cards:
        if _is_land(card) or card.cmc is None:
            continue
        qty = max(1, card.quantity)
        total_cmc += float(card.cmc) * qty
        total_qty += qty
    if total_qty == 0:
        return 0.0
    return total_cmc / total_qty


def _ramp_count(deck: DeckDetailResponse, card_tags: dict[UUID, list[str]] | None) -> int:
    """Sum of quantities of cards tagged ramp/fast_mana (lands excluded)."""
    if not card_tags:
        return 0
    count = 0
    for card in deck.cards:
        if _is_land(card):
            continue
        tags = set(card_tags.get(card.card_id, []))
        if tags & _RAMP_TAGS:
            count += max(1, card.quantity)
    return count


def _collect_risky_cards(
    deck: DeckDetailResponse, sources_by_color: dict[str, int]
) -> dict[str, list[RiskyCard]]:
    """Walk non-land cards; flag those whose solid-pip needs exceed sources.

    For each non-land card and each color C with solid pips > 0, look up the
    Karsten requirement at the card's CMC (capped at turn 6) and compare to
    ``sources_by_color[C]``. Cards where availability < requirement get a
    ``RiskyCard`` entry under that color.

    Per-color list is sorted by deficit descending and capped at
    ``_RISKY_PER_COLOR_CAP`` entries to keep payloads bounded.
    """
    buckets: dict[str, list[RiskyCard]] = {c: [] for c in _COLORS}
    for card in deck.cards:
        if _is_land(card) or card.cmc is None:
            continue
        turn = max(1, int(card.cmc))
        solid = _solid_pips(card.mana_cost)
        for color, pips in solid.items():
            if pips <= 0:
                continue
            required = _karsten_requirement(turn, pips)
            if required <= 0:
                continue
            available = sources_by_color.get(color, 0)
            if available >= required:
                continue
            buckets[color].append(
                RiskyCard(
                    card_id=card.card_id,
                    name=card.name,
                    mana_cost=card.mana_cost,
                    cmc=turn,
                    color=color,
                    pips_required=pips,
                    sources_available=available,
                    sources_required=required,
                )
            )
    for color, cards in buckets.items():
        cards.sort(key=lambda r: r.sources_required - r.sources_available, reverse=True)
        buckets[color] = cards[:_RISKY_PER_COLOR_CAP]
    return buckets


def analyze_mana_base(
    deck: DeckDetailResponse,
    *,
    card_tags: dict[UUID, list[str]] | None = None,
) -> ManaBaseReport:
    """Analyze the deck's mana base and report deficits per color.

    Skips the commander and partner (color identity already drives what's
    allowed). Sums pip counts on non-land cards (weighted by quantity) and
    source counts on land cards (likewise quantity-weighted).

    Args:
        deck: Deck to analyze.
        card_tags: Optional map ``card_id -> tag list``. When provided, enables
            ramp-count detection and the land-count recommendation. Absent
            ⇒ ``ramp_count=0`` and the recommendation reflects avg CMC only.

    Returns:
        ManaBaseReport with per-color status plus aggregate land
        recommendation and CMC/ramp signals.
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

    risky_buckets = _collect_risky_cards(deck, sources_by_color)

    total_pips = sum(pips_by_color[c] for c in color_identity)
    statuses: list[ColorStatus] = []
    for color in color_identity:
        pip = pips_by_color.get(color, 0.0)
        sources = sources_by_color.get(color, 0)
        target = _compute_target(pip, total_pips, total_lands)
        deficit = max(0, target - sources)
        risky = risky_buckets.get(color, [])
        turn_demand = max((r.sources_required for r in risky), default=0)
        turn_deficit = max(0, turn_demand - sources)
        statuses.append(
            ColorStatus(
                color=color,
                pip_count=round(pip, 2),
                source_count=sources,
                target=target,
                deficit=deficit,
                turn_demand=turn_demand,
                turn_deficit=turn_deficit,
                risky_cards=risky,
            )
        )

    avg_cmc = _avg_nonland_cmc(deck)
    ramp = _ramp_count(deck, card_tags)
    recommended = _recommend_land_count(avg_cmc, ramp)
    return ManaBaseReport(
        total_lands=total_lands,
        total_colored_pips=round(total_pips, 2),
        colors=statuses,
        avg_cmc=round(avg_cmc, 2),
        ramp_count=ramp,
        recommended_lands=recommended,
        land_delta=recommended - total_lands,
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


async def _fetch_card_tags(pool: asyncpg.Pool, card_ids: list[UUID]) -> dict[UUID, list[str]]:
    """Fetch the ``tags`` arrays for a batch of card UUIDs."""
    if not card_ids:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, tags FROM cards WHERE id = ANY($1::uuid[])", card_ids)
    return {row["id"]: list(row["tags"] or []) for row in rows}


async def suggest_mana_fix(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    deck: DeckDetailResponse,
    account_id: UUID | None,
    *,
    max_price_cents: int | None = None,
) -> ManaFixResponse:
    """Analyze the deck and return both the report and a land-fix shortlist.

    Combines the deficit-based suggestion list with the enriched report (land
    count recommendation + turn-N risk). When neither dimension flags an
    issue, suggestions is empty.

    Args:
        pool: asyncpg connection pool.
        ai_client: LLM adapter (used by retrieval for query embedding).
        qdrant_client: Qdrant async client.
        deck: Deck to analyze.
        account_id: Caller's account (for ownership annotations).
        max_price_cents: When set, excludes candidate lands above this EUR
            cap. ``None`` ⇒ no price ceiling.
    """
    card_tags = await _fetch_card_tags(pool, [c.card_id for c in deck.cards])
    report = analyze_mana_base(deck, card_tags=card_tags)
    deficient = [c.color for c in report.colors if c.deficit > 0]
    if not deficient:
        return ManaFixResponse(report=report, suggestions=[], unresolved=[])

    deck_card_ids = [c.card_id for c in deck.cards]
    commander_ids = [deck.commander_id] + ([deck.partner_id] if deck.partner_id else [])
    excluded = list({*deck_card_ids, *commander_ids})

    price_filter = PriceFilter(max_cents=max_price_cents, min_cents=0) if max_price_cents else None
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
        price_filter=price_filter,
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
