"""Broad deck optimizer: search land + nonland swaps and re-simulate.

The run has three phases, all driven by a goldfish simulation and a single
weighted health score (:func:`_health_score`):

1. **Land search** — build a large pool of in-color land sources
   (:func:`mana_base_service.candidate_lands`) and a ranked list of swappable
   lands (over-represented basics + weak nonbasic lands, e.g. enters-tapped
   single-color lands). Each round, try every (swap-out land × candidate)
   pair, simulate, and commit the single best score-improving swap.
2. **Nonland search** — the existing weak-card loop (:func:`_try_swap` over
   :mod:`swap_service` candidates) for any remaining swap budget.
3. **Confirm** — the search runs at reduced trials for speed; afterwards the
   original and final decks are re-simulated at full trials to produce the
   reported baseline/final stats.

Every simulation is offloaded with :func:`asyncio.to_thread` (the simulator is
sync/CPU-bound) and reports progress through a :class:`_Progress` ticker, so a
long run keeps the event loop free for status polling.

No DB writes happen here — the caller applies confirmed swaps via the existing
add/remove deck endpoints.
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
from qdrant_client import AsyncQdrantClient

from mtg_helper.models.ai import CardSuggestion
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.models.optimizer import OptimizationProposal, ProposedSwap, SearchDepth
from mtg_helper.models.playtest import PlaytestSimulateRequest, PlaytestStats
from mtg_helper.services import mana_base_service, playtest_service, swap_service
from mtg_helper.services.llm_client import LLMClient
from mtg_helper.services.optimizer_jobs import ProgressCb, noop_progress
from mtg_helper.services.swap_service import SwapError

_SCORE_EPSILON = 0.01
_WEAK_CARD_ATTEMPTS = 6
_CANDIDATE_LIMIT = 5
_FIVE_COLORS = frozenset("WUBRG")

_SCORE_WEIGHTS = {
    "screw": 1.5,
    "flood": 1.0,
    "color_screw": 1.2,
    "mulligans": 0.8,
    "kept_at_7": 0.6,
    "commander_cast": 0.4,
}


@dataclass(frozen=True)
class _DepthPreset:
    """Search-breadth knobs for one ``search_depth`` preset."""

    pool: int
    out_targets: int
    max_land_rounds: int
    search_trials: int


_DEPTH_PRESETS: dict[SearchDepth, _DepthPreset] = {
    "quick": _DepthPreset(pool=20, out_targets=3, max_land_rounds=2, search_trials=400),
    "thorough": _DepthPreset(pool=40, out_targets=6, max_land_rounds=3, search_trials=400),
    "exhaustive": _DepthPreset(pool=80, out_targets=12, max_land_rounds=4, search_trials=500),
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


def _pinned(
    sim: PlaytestSimulateRequest, seed: int, *, trials: int | None = None
) -> PlaytestSimulateRequest:
    update: dict[str, int] = {"seed": seed}
    if trials is not None:
        update["trials"] = trials
    return sim.model_copy(update=update)


@dataclass
class _Progress:
    """Counts simulations and reports ticks to the caller's progress sink."""

    cb: ProgressCb
    total: int
    done: int = 0
    phase: str = ""

    async def sim(self, deck: DeckDetailResponse, sim: PlaytestSimulateRequest) -> PlaytestStats:
        """Run one simulation off the event loop and tick progress."""
        stats = await asyncio.to_thread(playtest_service.simulate, deck, sim)
        self.done += 1
        self.cb(self.phase, self.done, self.total)
        return stats


@dataclass(frozen=True)
class _WeakCard:
    """One in-deck card flagged as a likely swap source, with its rank score."""

    card: DeckCardItem
    weight: float
    reason: str


_BLOCKER_PRIORITY = {"colors": 3.0, "mana": 2.0, "never_drawn": 0.5}


def _is_basic_land(card: DeckCardItem) -> bool:
    return "Basic Land" in (card.type_line or "")


def _is_land(card: DeckCardItem) -> bool:
    return "Land" in (card.type_line or "")


def _rank_weak_cards(
    deck: DeckDetailResponse,
    stats: PlaytestStats,
    excluded_names: set[str],
) -> list[_WeakCard]:
    """Order in-deck nonland cards by how much swapping them out is likely to
    help. Combines ``top_stuck_cards`` (per-blocker priority) and per-card
    stuck-in-hand percentages. Lands, commanders/partners, and ``excluded_names``
    are skipped.
    """
    by_name: dict[str, DeckCardItem] = {c.name: c for c in deck.cards if not _is_land(c)}
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


def _land_disposability(card: DeckCardItem, source_by_color: dict[str, int]) -> float:
    """Score how freely a land can be swapped out. Higher = more disposable.

    Basics are always disposable (abundant-color basics most so). Nonbasic
    lands earn disposability for entering tapped, producing a single color, or
    only producing colors the deck is already rich in. Strong untapped
    multi-color lands score near zero and are tried last (or not at all).
    """
    produces = playtest_service._land_produces(card)
    abundance = float(max((source_by_color.get(c, 0) for c in produces), default=0))
    if _is_basic_land(card):
        return abundance + 1.0
    score = 0.0
    if playtest_service._is_enters_tapped(card):
        score += 5.0
    if len({c for c in produces}) <= 1:
        score += 3.0
    score += min(abundance, 10.0) * 0.3
    return score


def _rank_swappable_lands(deck: DeckDetailResponse) -> list[DeckCardItem]:
    """Rank in-deck lands by disposability (basics + weak nonbasics first).

    Lands scoring zero disposability (strong untapped fixers) are dropped.
    """
    report = mana_base_service.analyze_mana_base(deck)
    source_by_color = {c.color: c.source_count for c in report.colors}
    scored: list[tuple[float, DeckCardItem]] = []
    for land in deck.cards:
        if not _is_land(land) or land.quantity <= 0:
            continue
        weight = _land_disposability(land, source_by_color)
        if weight > 0:
            scored.append((weight, land))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [land for _, land in scored]


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


def _over_price(cand: CardSuggestion, max_price_cents: int | None) -> bool:
    return (
        max_price_cents is not None
        and cand.price_eur_cents is not None
        and cand.price_eur_cents > max_price_cents
    )


def _land_swap_reason(out_land: DeckCardItem, cand: CardSuggestion, stats: PlaytestStats) -> str:
    colors = "/".join(c for c in (cand.color_identity or []) if c in _FIVE_COLORS) or "fixing"
    if _is_basic_land(out_land):
        screw = stats.color_screw.pct_color_screw * 100
        return f"color screw {screw:.0f}% — {out_land.name} → {colors} source"
    return f"upgrading {out_land.name} → better {colors} land"


@dataclass
class _RunState:
    """Mutable accumulation threaded through the search phases."""

    variant_deck: DeckDetailResponse
    variant_stats: PlaytestStats
    current_score: float
    swaps: list[ProposedSwap]
    excluded_scryfall_ids: set[UUID]

    def commit(
        self, proposal: ProposedSwap, stats: PlaytestStats, deck: DeckDetailResponse
    ) -> None:
        self.swaps.append(proposal)
        self.current_score += proposal.score_delta
        self.variant_stats = stats
        self.variant_deck = deck
        self.excluded_scryfall_ids.add(proposal.in_scryfall_id)
        self.excluded_scryfall_ids.add(proposal.out_scryfall_id)


async def _best_land_swap(
    state: _RunState,
    prog: _Progress,
    out_targets: list[DeckCardItem],
    candidates: list[CardSuggestion],
    search_sim: PlaytestSimulateRequest,
    *,
    max_price_cents: int | None,
) -> tuple[ProposedSwap, PlaytestStats, DeckDetailResponse, UUID] | None:
    """Evaluate every (out land × candidate) pair; return the best improver."""
    best: tuple[ProposedSwap, PlaytestStats, DeckDetailResponse, UUID] | None = None
    best_delta = _SCORE_EPSILON
    for out_land in out_targets:
        for cand in candidates:
            if cand.scryfall_id in state.excluded_scryfall_ids or _over_price(
                cand, max_price_cents
            ):
                continue
            replacement = _candidate_to_card_item(cand, out_land, [])
            variant = _apply_swap_in_memory(state.variant_deck, out_land, replacement)
            stats = await prog.sim(variant, search_sim)
            delta = _health_score(stats) - state.current_score
            if delta <= best_delta:
                continue
            proposal = ProposedSwap(
                out_card_id=out_land.card_id,
                out_scryfall_id=out_land.scryfall_id,
                out_card_name=out_land.name,
                in_scryfall_id=cand.scryfall_id,
                in_card_name=cand.name,
                reason=_land_swap_reason(out_land, cand, state.variant_stats),
                score_delta=delta,
                price_delta_cents=_price_delta(out_land, cand),
            )
            best = (proposal, stats, variant, out_land.card_id)
            best_delta = delta
    return best


async def _run_land_search(
    state: _RunState,
    prog: _Progress,
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    search_sim: PlaytestSimulateRequest,
    *,
    max_price_cents: int | None,
    max_swaps: int,
    depth: _DepthPreset,
) -> None:
    """Try land swaps (basics + weak nonbasics → better sources) in rounds.

    Each round evaluates every (swap-out land × candidate) pair and commits the
    single best score-improving swap. Stops at ``max_swaps`` or when a round
    finds no improvement. Each distinct land is swapped at most once so the
    apply step's single-copy semantics stay unambiguous.
    """
    prog.phase = "searching lands"
    candidates = await mana_base_service.candidate_lands(
        pool,
        ai_client,
        qdrant_client,
        state.variant_deck,
        max_price_cents=max_price_cents,
        limit=depth.pool,
    )
    if not candidates:
        return
    used_out_ids: set[UUID] = set()
    for _round in range(depth.max_land_rounds):
        if len(state.swaps) >= max_swaps:
            break
        out_targets = [
            land
            for land in _rank_swappable_lands(state.variant_deck)
            if land.card_id not in used_out_ids
        ][: depth.out_targets]
        best = await _best_land_swap(
            state, prog, out_targets, candidates, search_sim, max_price_cents=max_price_cents
        )
        if best is None:
            break
        proposal, stats, variant, out_id = best
        used_out_ids.add(out_id)
        state.commit(proposal, stats, variant)


async def _try_swap(
    state: _RunState,
    prog: _Progress,
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    weak: _WeakCard,
    search_sim: PlaytestSimulateRequest,
    *,
    max_price_cents: int | None,
    account_id: UUID | None,
) -> tuple[ProposedSwap, PlaytestStats, DeckDetailResponse] | None:
    """Find the best score-improving replacement for ``weak.card`` or ``None``."""
    try:
        swap_resp = await swap_service.find_budget_swaps(
            pool,
            ai_client,
            qdrant_client,
            state.variant_deck,
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
        if cand.scryfall_id in state.excluded_scryfall_ids:
            continue
        replacement = _candidate_to_card_item(cand, weak.card, weak.card.qualifying_stages or [])
        variant = _apply_swap_in_memory(state.variant_deck, weak.card, replacement)
        stats = await prog.sim(variant, search_sim)
        delta = _health_score(stats) - state.current_score
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
        best = (proposal, stats, variant)
        best_delta = delta
    return best


async def _run_nonland_search(
    state: _RunState,
    prog: _Progress,
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    search_sim: PlaytestSimulateRequest,
    *,
    max_price_cents: int | None,
    account_id: UUID | None,
    max_swaps: int,
) -> None:
    """Swap weak nonland cards for cheaper functional replacements."""
    prog.phase = "searching cards"
    excluded_names: set[str] = set()
    while len(state.swaps) < max_swaps:
        weak_cards = _rank_weak_cards(state.variant_deck, state.variant_stats, excluded_names)
        if not weak_cards:
            break
        committed = False
        for weak in weak_cards[:_WEAK_CARD_ATTEMPTS]:
            outcome = await _try_swap(
                state,
                prog,
                pool,
                ai_client,
                qdrant_client,
                weak,
                search_sim,
                max_price_cents=max_price_cents,
                account_id=account_id,
            )
            if outcome is None:
                excluded_names.add(weak.card.name)
                continue
            proposal, stats, variant = outcome
            excluded_names.add(proposal.out_card_name)
            excluded_names.add(proposal.in_card_name)
            state.commit(proposal, stats, variant)
            committed = True
            break
        if not committed:
            break


def _estimate_total(depth: _DepthPreset) -> int:
    """Upper-bound number of sims for the progress bar (baseline + land grid +
    one nonland round + 2 confirm). The job clamps ``current`` to ``total`` on
    finish, so an early stop still completes the bar.
    """
    land = depth.max_land_rounds * depth.out_targets * depth.pool
    nonland = _WEAK_CARD_ATTEMPTS * _CANDIDATE_LIMIT
    return 1 + land + nonland + 2


async def run_search(
    pool: asyncpg.Pool,
    ai_client: LLMClient,
    qdrant_client: AsyncQdrantClient,
    deck: DeckDetailResponse,
    sim_request: PlaytestSimulateRequest,
    *,
    search_depth: SearchDepth = "thorough",
    max_price_cents: int | None,
    max_swaps: int = 3,
    account_id: UUID | None,
    progress_cb: ProgressCb = noop_progress,
) -> OptimizationProposal:
    """Run the broad land + nonland search and return the proposal.

    Args:
        pool: asyncpg connection pool.
        ai_client: LLM adapter (used by retrieval for query embedding).
        qdrant_client: Qdrant async client.
        deck: The deck to optimize. Not mutated.
        sim_request: Full-trial sim parameters; ``seed`` is pinned across every
            variant (derived from the deck id when omitted) and ``trials`` is
            used for the final confirm sims.
        search_depth: Breadth preset — larger presets try more candidates,
            swap-out targets, and rounds (and take longer).
        max_price_cents: Price ceiling applied to every candidate.
        max_swaps: Upper bound on total committed swaps (lands + nonland).
        account_id: Caller's account id (ownership annotations).
        progress_cb: Sink called ``(phase, current, total)`` per simulation.

    Returns:
        ``OptimizationProposal`` with full-trial baseline/final stats and the
        accepted swaps.
    """
    depth = _DEPTH_PRESETS[search_depth]
    seed = _resolve_seed(deck, sim_request)
    search_trials = min(depth.search_trials, sim_request.trials)
    search_sim = _pinned(sim_request, seed, trials=search_trials)
    full_sim = _pinned(sim_request, seed)

    prog = _Progress(cb=progress_cb, total=_estimate_total(depth), phase="searching lands")
    baseline_search = await prog.sim(deck, search_sim)
    state = _RunState(
        variant_deck=deck,
        variant_stats=baseline_search,
        current_score=_health_score(baseline_search),
        swaps=[],
        excluded_scryfall_ids=set(),
    )

    await _run_land_search(
        state,
        prog,
        pool,
        ai_client,
        qdrant_client,
        search_sim,
        max_price_cents=max_price_cents,
        max_swaps=max_swaps,
        depth=depth,
    )
    await _run_nonland_search(
        state,
        prog,
        pool,
        ai_client,
        qdrant_client,
        search_sim,
        max_price_cents=max_price_cents,
        account_id=account_id,
        max_swaps=max_swaps,
    )

    prog.phase = "confirming"
    baseline_full = await prog.sim(deck, full_sim)
    final_full = await prog.sim(state.variant_deck, full_sim) if state.swaps else baseline_full
    total_delta = _health_score(final_full) - _health_score(baseline_full)
    return OptimizationProposal(
        baseline_stats=baseline_full,
        final_stats=final_full,
        swaps=state.swaps,
        total_score_delta=total_delta,
        total_price_delta_cents=_sum_price_deltas(state.swaps),
    )
