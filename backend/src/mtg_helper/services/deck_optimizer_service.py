"""Greedy deck optimizer: iteratively swap weak cards and re-simulate.

The loop:

1. Run a baseline goldfish simulation and compute a weighted health score.
2. **Mana-fix stage** (when color screw is breached): trim an over-represented
   basic land and add a dual/check/shock land that covers the deficient color,
   sourced from :mod:`mana_base_service`. Re-simulate; keep the swap if the
   score improves. Repeat while color screw stays breached and budget remains.
3. **Nonland stage**: rank in-deck cards by how badly they hurt the score
   (stuck in hand, never cast, blocked on mana/colors). For each weak card,
   ask :mod:`swap_service` for cheaper functional replacements under the price
   ceiling.
4. Re-simulate a variant deck with each replacement in place. Pin the RNG
   seed across every variant so the score delta measures the card change,
   not RNG noise.
5. Keep the replacement with the largest positive delta above an epsilon
   floor (rejects noise-driven flips). Stop at ``max_swaps`` total swaps.

No DB writes happen here — the caller applies confirmed swaps via the
existing add/remove deck endpoints.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
from qdrant_client import AsyncQdrantClient

from mtg_helper.models.ai import CardSuggestion
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.models.optimizer import OptimizationProposal, ProposedSwap
from mtg_helper.models.playtest import PlaytestSimulateRequest, PlaytestStats
from mtg_helper.services import mana_base_service, playtest_service, swap_service
from mtg_helper.services.llm_client import LLMClient
from mtg_helper.services.swap_service import SwapError

_SCORE_EPSILON = 0.01
_WEAK_CARD_ATTEMPTS = 6
_CANDIDATE_LIMIT = 5
# Color screw above this fraction triggers the mana-fix stage.
_COLOR_SCREW_TRIGGER = 0.05
_FIVE_COLORS = frozenset("WUBRG")

_SCORE_WEIGHTS = {
    "screw": 1.5,
    "flood": 1.0,
    "color_screw": 1.2,
    "mulligans": 0.8,
    "kept_at_7": 0.6,
    "commander_cast": 0.4,
}


def _health_score(stats: PlaytestStats) -> float:
    """Weighted health score — higher is better. Each component is normalized
    so the healthier direction yields a larger number.
    """
    mulligan_pressure = max(0.0, min(stats.avg_mulligans / 3.0, 1.0))
    commander_cast = stats.commander.pct_ever_cast if stats.commander is not None else 0.0
    return (
        (1.0 - stats.pct_screw) * _SCORE_WEIGHTS["screw"]
        + (1.0 - stats.pct_flood) * _SCORE_WEIGHTS["flood"]
        + (1.0 - stats.color_screw.pct_color_screw) * _SCORE_WEIGHTS["color_screw"]
        + (1.0 - mulligan_pressure) * _SCORE_WEIGHTS["mulligans"]
        + stats.opening_hand.pct_kept_7 * _SCORE_WEIGHTS["kept_at_7"]
        + commander_cast * _SCORE_WEIGHTS["commander_cast"]
    )


def _resolve_seed(deck: DeckDetailResponse, sim: PlaytestSimulateRequest) -> int:
    """Pick the seed pinned across all variant sims. Caller's value wins;
    otherwise a stable hash of the deck id keeps reruns reproducible.
    """
    if sim.seed is not None:
        return sim.seed
    return abs(hash(deck.id)) % (2**31)


def _pinned(sim: PlaytestSimulateRequest, seed: int) -> PlaytestSimulateRequest:
    return sim.model_copy(update={"seed": seed})


@dataclass(frozen=True)
class _WeakCard:
    """One in-deck card flagged as a likely swap source, with its rank score."""

    card: DeckCardItem
    weight: float
    reason: str


_BLOCKER_PRIORITY = {"colors": 3.0, "mana": 2.0, "never_drawn": 0.5}


def _is_basic_land(card: DeckCardItem) -> bool:
    return "Basic Land" in (card.type_line or "")


def _rank_weak_cards(
    deck: DeckDetailResponse,
    stats: PlaytestStats,
    excluded_names: set[str],
) -> list[_WeakCard]:
    """Order in-deck cards by how much swapping them out is likely to help.

    Combines ``top_stuck_cards`` (with a per-blocker priority) and per-card
    stuck-in-hand percentages. Basic lands, commanders/partners, and any
    names in ``excluded_names`` are skipped.
    """
    by_name: dict[str, DeckCardItem] = {c.name: c for c in deck.cards if not _is_basic_land(c)}
    weights: dict[str, tuple[float, str]] = {}

    for stuck in stats.top_stuck_cards:
        if stuck.name not in by_name or stuck.name in excluded_names:
            continue
        priority = _BLOCKER_PRIORITY.get(stuck.blocker, 1.0)
        score = stuck.pct_stuck * priority
        reason = f"stuck in hand {stuck.pct_stuck * 100:.0f}% (blocker: {stuck.blocker})"
        weights[stuck.name] = (score, reason)

    for per_card in stats.per_card:
        if per_card.name in excluded_names or per_card.name not in by_name:
            continue
        if per_card.pct_stuck_in_hand_at_end < 0.15:
            continue
        score = per_card.pct_stuck_in_hand_at_end
        if per_card.pct_ever_cast < 0.5:
            score += 0.1
        existing = weights.get(per_card.name)
        if existing is None or score > existing[0]:
            reason = (
                f"cast {per_card.pct_ever_cast * 100:.0f}%, "
                f"stuck {per_card.pct_stuck_in_hand_at_end * 100:.0f}%"
            )
            weights[per_card.name] = (score, reason)

    ranked = sorted(weights.items(), key=lambda item: item[1][0], reverse=True)
    return [_WeakCard(card=by_name[name], weight=w, reason=r) for name, (w, r) in ranked]


def _candidate_to_card_item(
    cand: CardSuggestion, source: DeckCardItem, source_stages: list[str]
) -> DeckCardItem:
    """Build an in-memory ``DeckCardItem`` for the replacement so the variant
    deck can be simulated without touching the DB. Identifiers are fresh
    placeholders; persistence happens in the apply step via the real
    add-card endpoint.
    """
    cmc_value: Decimal | None = None
    if cand.cmc is not None:
        cmc_value = Decimal(str(cand.cmc))
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=cand.scryfall_id,
        name=cand.name,
        mana_cost=cand.mana_cost,
        cmc=cmc_value,
        type_line=cand.type_line,
        oracle_text=cand.oracle_text,
        color_identity=list(cand.color_identity or []),
        image_uri=cand.image_uri,
        rarity=cand.rarity,
        quantity=1,
        categories=list(source.categories or []),
        added_by="ai",
        ai_reasoning="optimizer swap",
        qualifying_stages=list(cand.qualifying_stages or source_stages),
        tags=[],
        power=None,
        price_eur_cents=cand.price_eur_cents,
    )


def _apply_swap_in_memory(
    deck: DeckDetailResponse,
    out_card: DeckCardItem,
    replacement: DeckCardItem,
) -> DeckDetailResponse:
    """Return a deep-copied deck with one quantity of ``out_card`` replaced by
    ``replacement``. Does not mutate the input deck.
    """
    variant = deck.model_copy(deep=True)
    new_cards: list[DeckCardItem] = []
    swapped = False
    for item in variant.cards:
        if not swapped and item.card_id == out_card.card_id and item.quantity > 0:
            if item.quantity == 1:
                swapped = True
                continue
            new_cards.append(item.model_copy(update={"quantity": item.quantity - 1}))
            swapped = True
            continue
        new_cards.append(item)
    if not swapped:
        return variant
    new_cards.append(replacement)
    variant.cards = new_cards
    return variant


def _price_delta(out_card: DeckCardItem, cand: CardSuggestion) -> int | None:
    out_price = out_card.price_eur_cents
    in_price = cand.price_eur_cents
    if out_price is None or in_price is None:
        return None
    return in_price - out_price


def _sum_price_deltas(swaps: list[ProposedSwap]) -> int | None:
    """Sum per-swap deltas. Returns ``None`` if any swap has an unknown price
    so the caller can render "—" rather than a misleading total.
    """
    if not swaps:
        return 0
    total = 0
    for s in swaps:
        if s.price_delta_cents is None:
            return None
        total += s.price_delta_cents
    return total


def _pick_overrepresented_basic(
    deck: DeckDetailResponse, exclude_card_ids: set[UUID]
) -> DeckCardItem | None:
    """Pick the basic land whose color is most over-represented, to trim by one.

    Uses ``analyze_mana_base`` source counts: trimming a copy of the most
    abundant color's basic frees a land slot for a dual without starving that
    color. Returns ``None`` when no eligible basic remains.
    """
    report = mana_base_service.analyze_mana_base(deck)
    source_by_color = {c.color: c.source_count for c in report.colors}
    basics = [
        c
        for c in deck.cards
        if _is_basic_land(c) and c.card_id not in exclude_card_ids and c.quantity > 0
    ]
    if not basics:
        return None

    def disposability(card: DeckCardItem) -> int:
        colors = [x for x in (card.color_identity or []) if x in source_by_color]
        return max((source_by_color[x] for x in colors), default=0)

    basics.sort(key=disposability, reverse=True)
    return basics[0]


def _mana_fix_reason(pct_color_screw: float, cand: CardSuggestion) -> str:
    colors = "/".join(c for c in (cand.color_identity or []) if c in _FIVE_COLORS)
    sources = colors if colors else "color"
    return f"color screw {pct_color_screw * 100:.0f}% — adding {sources} source"


async def _try_mana_fix(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    deck: DeckDetailResponse,
    stats: PlaytestStats,
    pinned_sim: PlaytestSimulateRequest,
    current_score: float,
    *,
    max_price_cents: int | None,
    account_id: UUID | None,
    exclude_card_ids: set[UUID],
    excluded_scryfall_ids: set[UUID],
) -> tuple[ProposedSwap, PlaytestStats, DeckDetailResponse] | None:
    """Trim one over-represented basic for the best color-fixing land, or ``None``.

    Sources candidates from ``mana_base_service.suggest_mana_fix`` (already
    price-filtered server-side; re-checked here defensively) and keeps the
    dual whose swap improves the score most, above the epsilon floor.
    """
    out_basic = _pick_overrepresented_basic(deck, exclude_card_ids)
    if out_basic is None:
        return None
    fix = await mana_base_service.suggest_mana_fix(
        pool, ai_client, qdrant_client, deck, account_id, max_price_cents=max_price_cents
    )

    best: tuple[ProposedSwap, PlaytestStats, DeckDetailResponse] | None = None
    best_delta = _SCORE_EPSILON
    for cand in fix.suggestions:
        if cand.scryfall_id in excluded_scryfall_ids:
            continue
        if (
            max_price_cents is not None
            and cand.price_eur_cents is not None
            and cand.price_eur_cents > max_price_cents
        ):
            continue
        replacement = _candidate_to_card_item(cand, out_basic, [])
        variant = _apply_swap_in_memory(deck, out_basic, replacement)
        variant_stats = playtest_service.simulate(variant, pinned_sim)
        delta = _health_score(variant_stats) - current_score
        if delta <= best_delta:
            continue
        proposal = ProposedSwap(
            out_card_id=out_basic.card_id,
            out_scryfall_id=out_basic.scryfall_id,
            out_card_name=out_basic.name,
            in_scryfall_id=cand.scryfall_id,
            in_card_name=cand.name,
            reason=_mana_fix_reason(stats.color_screw.pct_color_screw, cand),
            score_delta=delta,
            price_delta_cents=_price_delta(out_basic, cand),
        )
        best = (proposal, variant_stats, variant)
        best_delta = delta
    return best


async def _try_swap(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    deck: DeckDetailResponse,
    weak: _WeakCard,
    pinned_sim: PlaytestSimulateRequest,
    current_score: float,
    *,
    max_price_cents: int | None,
    account_id: UUID | None,
    excluded_scryfall_ids: set[UUID],
) -> tuple[ProposedSwap, PlaytestStats, DeckDetailResponse] | None:
    """Find the best score-improving replacement for ``weak.card`` or ``None``.

    Returns a tuple of (the swap record, the variant's stats, the variant
    deck) when at least one candidate clears the epsilon floor.
    """
    try:
        swap_resp = await swap_service.find_budget_swaps(
            pool,
            ai_client,
            qdrant_client,
            deck,
            weak.card.card_id,
            max_price_cents=max_price_cents,
            account_id=account_id,
            limit=_CANDIDATE_LIMIT,
        )
    except SwapError:
        return None

    best: tuple[ProposedSwap, PlaytestStats, DeckDetailResponse] | None = None
    best_delta = _SCORE_EPSILON
    for cand in swap_resp.candidates:
        if cand.scryfall_id in excluded_scryfall_ids:
            continue
        replacement = _candidate_to_card_item(cand, weak.card, weak.card.qualifying_stages or [])
        variant = _apply_swap_in_memory(deck, weak.card, replacement)
        variant_stats = playtest_service.simulate(variant, pinned_sim)
        delta = _health_score(variant_stats) - current_score
        if delta <= best_delta:
            continue
        proposal = ProposedSwap(
            out_card_id=weak.card.card_id,
            out_scryfall_id=weak.card.scryfall_id,
            out_card_name=weak.card.name,
            in_scryfall_id=cand.scryfall_id,
            in_card_name=cand.name,
            reason=weak.reason,
            score_delta=delta,
            price_delta_cents=_price_delta(weak.card, cand),
        )
        best = (proposal, variant_stats, variant)
        best_delta = delta
    return best


async def _run_mana_fix_loop(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    variant_deck: DeckDetailResponse,
    variant_stats: PlaytestStats,
    pinned_sim: PlaytestSimulateRequest,
    current_score: float,
    swaps: list[ProposedSwap],
    excluded_scryfall_ids: set[UUID],
    *,
    max_price_cents: int | None,
    account_id: UUID | None,
    max_swaps: int,
) -> tuple[DeckDetailResponse, PlaytestStats, float]:
    """Trim over-represented basics for color-fixing lands while screw is breached.

    Mutates ``swaps`` and ``excluded_scryfall_ids`` in place; returns the
    updated ``(deck, stats, score)`` so the caller can continue into the
    nonland stage. Each distinct basic is trimmed at most once per call to
    keep the apply step's single-copy swap unambiguous.
    """
    exclude_basic_ids: set[UUID] = set()
    while len(swaps) < max_swaps:
        if variant_stats.color_screw.pct_color_screw <= _COLOR_SCREW_TRIGGER:
            break
        outcome = await _try_mana_fix(
            pool,
            ai_client,
            qdrant_client,
            variant_deck,
            variant_stats,
            pinned_sim,
            current_score,
            max_price_cents=max_price_cents,
            account_id=account_id,
            exclude_card_ids=exclude_basic_ids,
            excluded_scryfall_ids=excluded_scryfall_ids,
        )
        if outcome is None:
            break
        proposal, new_stats, new_deck = outcome
        swaps.append(proposal)
        current_score += proposal.score_delta
        variant_stats = new_stats
        variant_deck = new_deck
        exclude_basic_ids.add(proposal.out_card_id)
        excluded_scryfall_ids.add(proposal.in_scryfall_id)
    return variant_deck, variant_stats, current_score


async def propose_optimization(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    deck: DeckDetailResponse,
    sim_request: PlaytestSimulateRequest,
    *,
    max_price_cents: int | None,
    max_swaps: int = 3,
    account_id: UUID | None,
) -> OptimizationProposal:
    """Run the greedy swap loop and return the proposal.

    Args:
        pool: asyncpg connection pool.
        ai_client: LLM adapter (used by retrieval for query embedding).
        qdrant_client: Qdrant async client.
        deck: The deck to optimize. Not mutated.
        sim_request: Simulation parameters. ``seed`` is pinned across all
            variants — derived from the deck id when caller omits it.
        max_price_cents: Per-candidate price ceiling, in cents. ``None``
            falls back to ``swap_service``'s "strictly cheaper than source"
            default per swap; the mana-fix stage applies no ceiling when None.
        max_swaps: Upper bound on accepted swaps (shared across the mana-fix
            and nonland stages).
        account_id: Caller's account id (for ownership annotations from
            ``swap_service``).

    Returns:
        ``OptimizationProposal`` with baseline + final stats and the
        accepted swap list.
    """
    seed = _resolve_seed(deck, sim_request)
    pinned_sim = _pinned(sim_request, seed)
    baseline_stats = playtest_service.simulate(deck, pinned_sim)

    variant_deck = deck
    variant_stats = baseline_stats
    current_score = _health_score(baseline_stats)
    swaps: list[ProposedSwap] = []
    excluded_names: set[str] = set()
    excluded_scryfall_ids: set[UUID] = set()

    if baseline_stats.color_screw.pct_color_screw > _COLOR_SCREW_TRIGGER:
        variant_deck, variant_stats, current_score = await _run_mana_fix_loop(
            pool,
            ai_client,
            qdrant_client,
            variant_deck,
            variant_stats,
            pinned_sim,
            current_score,
            swaps,
            excluded_scryfall_ids,
            max_price_cents=max_price_cents,
            account_id=account_id,
            max_swaps=max_swaps,
        )

    while len(swaps) < max_swaps:
        weak_cards = _rank_weak_cards(variant_deck, variant_stats, excluded_names)
        if not weak_cards:
            break
        committed = False
        for weak in weak_cards[:_WEAK_CARD_ATTEMPTS]:
            outcome = await _try_swap(
                pool,
                ai_client,
                qdrant_client,
                variant_deck,
                weak,
                pinned_sim,
                current_score,
                max_price_cents=max_price_cents,
                account_id=account_id,
                excluded_scryfall_ids=excluded_scryfall_ids,
            )
            if outcome is None:
                excluded_names.add(weak.card.name)
                continue
            proposal, new_stats, new_deck = outcome
            swaps.append(proposal)
            current_score += proposal.score_delta
            variant_stats = new_stats
            variant_deck = new_deck
            excluded_names.add(proposal.out_card_name)
            excluded_names.add(proposal.in_card_name)
            excluded_scryfall_ids.add(proposal.out_scryfall_id)
            excluded_scryfall_ids.add(proposal.in_scryfall_id)
            committed = True
            break
        if not committed:
            break

    total_delta = sum(s.score_delta for s in swaps)
    return OptimizationProposal(
        baseline_stats=baseline_stats,
        final_stats=variant_stats,
        swaps=swaps,
        total_score_delta=total_delta,
        total_price_delta_cents=_sum_price_deltas(swaps),
    )
