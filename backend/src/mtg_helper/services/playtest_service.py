"""Goldfish playtest simulator.

Runs N trial games per deck and reports turn-by-turn aggregates. The sim is
pure-Python and deterministic when a ``seed`` is supplied. The mana model is
deliberately rough — basics by name, non-basics by ``color_identity`` — which
is enough fidelity to surface curve and land-count problems but won't catch
ETB-tapped or filter-land nuances.
"""

import random
import re
from dataclasses import dataclass

from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.models.playtest import PlaytestSimulateRequest, PlaytestStats, TurnStat

_COLORS: tuple[str, ...] = ("W", "U", "B", "R", "G", "C")
_SYMBOL_RE = re.compile(r"\{([^}]+)\}")

_BASIC_LAND_PRODUCES: dict[str, str] = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
    "Wastes": "C",
}


@dataclass(frozen=True)
class ParsedCost:
    """A mana cost split into generic + colored multiset. X costs treat X=0."""

    generic: int
    colored: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class SimCard:
    """Immutable per-card data the sim needs. Built once per deck."""

    name: str
    cmc: int
    is_land: bool
    produces: tuple[str, ...]
    cost: ParsedCost | None


@dataclass
class TrialResult:
    mulligans: int
    lands_in_play_by_turn: list[int]
    spells_cast_by_turn: list[int]
    cumulative_spells_by_turn: list[int]


def _basic_land_color(name: str) -> str | None:
    base = name.split(" // ")[0]
    base = base.removeprefix("Snow-Covered ")
    return _BASIC_LAND_PRODUCES.get(base)


def _land_produces(card: DeckCardItem) -> tuple[str, ...]:
    basic = _basic_land_color(card.name)
    if basic is not None:
        return (basic,)
    identity = tuple(c for c in (card.color_identity or []) if c in _COLORS)
    return identity if identity else ("C",)


def parse_cost(mana_cost: str | None) -> ParsedCost:
    """Parse a Scryfall mana cost into generic + colored requirements.

    Hybrid (``{W/U}``) collapses to the first listed color — a v1 simplification
    that may slightly under-count castability for decks heavy on hybrid costs.
    """
    if not mana_cost:
        return ParsedCost(generic=0, colored=())
    generic = 0
    colored: dict[str, int] = {}
    for raw in _SYMBOL_RE.findall(mana_cost):
        sym = raw.upper()
        if sym in {"X", "Y", "Z"}:
            continue
        if sym.isdigit():
            generic += int(sym)
            continue
        if sym in _COLORS:
            colored[sym] = colored.get(sym, 0) + 1
            continue
        if "/" in sym:
            parts = [p for p in sym.split("/") if p in _COLORS]
            if parts:
                colored[parts[0]] = colored.get(parts[0], 0) + 1
                continue
        generic += 1
    return ParsedCost(generic=generic, colored=tuple(sorted(colored.items())))


def _to_sim_card(card: DeckCardItem) -> SimCard:
    is_land = "Land" in (card.type_line or "")
    produces = _land_produces(card) if is_land else ()
    cost = None if is_land else parse_cost(card.mana_cost)
    cmc = int(card.cmc) if card.cmc is not None else 0
    return SimCard(name=card.name, cmc=cmc, is_land=is_land, produces=produces, cost=cost)


def _expand_deck(cards: list[DeckCardItem]) -> list[SimCard]:
    out: list[SimCard] = []
    for card in cards:
        sim = _to_sim_card(card)
        qty = max(1, card.quantity)
        out.extend([sim] * qty)
    return out


def _can_cast(cost: ParsedCost, lands: list[SimCard]) -> bool:
    """Return True iff ``lands`` can collectively pay ``cost``.

    Solves the colored-requirement assignment with backtracking, then pays
    generic from any remaining land. Lands.length must be at least the cost's
    total mana value for any chance of success.
    """
    required: list[str] = []
    for color, count in cost.colored:
        required.extend([color] * count)
    needed = len(required) + cost.generic
    if len(lands) < needed:
        return False
    used = [False] * len(lands)
    if not _assign_colored(required, 0, lands, used):
        return False
    remaining = sum(1 for u in used if not u)
    return remaining >= cost.generic


def _assign_colored(required: list[str], idx: int, lands: list[SimCard], used: list[bool]) -> bool:
    if idx >= len(required):
        return True
    color = required[idx]
    for i, land in enumerate(lands):
        if used[i] or color not in land.produces:
            continue
        used[i] = True
        if _assign_colored(required, idx + 1, lands, used):
            return True
        used[i] = False
    return False


def _pay_cost(cost: ParsedCost, lands: list[SimCard]) -> list[SimCard]:
    """Return the subset of lands consumed to pay ``cost``. Caller must have
    verified ``_can_cast`` first; mirrors that function's assignment order.
    """
    required: list[str] = []
    for color, count in cost.colored:
        required.extend([color] * count)
    used = [False] * len(lands)
    _assign_colored(required, 0, lands, used)
    for i in range(len(lands)):
        if cost.generic <= 0:
            break
        if not used[i]:
            used[i] = True
            cost = ParsedCost(generic=cost.generic - 1, colored=cost.colored)
    return [lands[i] for i in range(len(lands)) if used[i]]


def _count_lands(hand: list[SimCard]) -> int:
    return sum(1 for c in hand if c.is_land)


def _should_keep(hand: list[SimCard], mulligans_taken: int, max_mulligans: int) -> bool:
    if mulligans_taken >= max_mulligans:
        return True
    lands = _count_lands(hand)
    return 2 <= lands <= 5


def _bottom_hand(hand: list[SimCard], n: int) -> tuple[list[SimCard], list[SimCard]]:
    """Pick ``n`` cards to put on the bottom of the library after London mulligan.

    Heuristic: if hand has > 4 lands, bottom the extra lands first; otherwise
    bottom highest-CMC non-lands first (keep curve cheap and lands available).
    Returns ``(kept_hand, bottomed)``.
    """
    if n <= 0:
        return hand, []
    lands = [c for c in hand if c.is_land]
    nonlands = sorted([c for c in hand if not c.is_land], key=lambda c: -c.cmc)
    bottomed: list[SimCard] = []
    excess_lands = max(0, len(lands) - 4)
    while bottomed.__len__() < n and excess_lands > 0 and lands:
        bottomed.append(lands.pop())
        excess_lands -= 1
    while len(bottomed) < n and nonlands:
        bottomed.append(nonlands.pop(0))
    while len(bottomed) < n and lands:
        bottomed.append(lands.pop())
    kept = lands + nonlands
    return kept, bottomed


def _draw_opening(
    library_template: list[SimCard], rng: random.Random, max_mulligans: int
) -> tuple[list[SimCard], list[SimCard], int]:
    """Simulate the London mulligan: draw 7 until keep, then bottom N cards."""
    mulligans = 0
    while True:
        library = library_template.copy()
        rng.shuffle(library)
        hand = library[:7]
        library = library[7:]
        if _should_keep(hand, mulligans, max_mulligans):
            kept, bottomed = _bottom_hand(hand, mulligans)
            library.extend(bottomed)
            return kept, library, mulligans
        mulligans += 1


def _play_land(hand: list[SimCard], battlefield: list[SimCard]) -> bool:
    for i, card in enumerate(hand):
        if card.is_land:
            battlefield.append(card)
            hand.pop(i)
            return True
    return False


def _cast_greedy(hand: list[SimCard], available_lands: list[SimCard]) -> int:
    """Repeatedly cast the highest-CMC castable spell until none remain."""
    cast_count = 0
    while True:
        nonlands = [c for c in hand if not c.is_land]
        castable = [
            c for c in nonlands if c.cost is not None and _can_cast(c.cost, available_lands)
        ]
        if not castable:
            return cast_count
        spell = max(castable, key=lambda c: c.cmc)
        assert spell.cost is not None
        consumed = _pay_cost(spell.cost, available_lands)
        for land in consumed:
            available_lands.remove(land)
        hand.remove(spell)
        cast_count += 1


def _run_trial(
    library_template: list[SimCard],
    rng: random.Random,
    turns: int,
    on_the_play: bool,
    max_mulligans: int,
) -> TrialResult:
    hand, library, mulligans = _draw_opening(library_template, rng, max_mulligans)
    battlefield_lands: list[SimCard] = []
    lands_by_turn: list[int] = []
    cast_by_turn: list[int] = []
    cumulative_by_turn: list[int] = []
    total_cast = 0
    for turn in range(1, turns + 1):
        if turn > 1 or not on_the_play:
            if library:
                hand.append(library.pop(0))
        _play_land(hand, battlefield_lands)
        cast = _cast_greedy(hand, battlefield_lands.copy())
        total_cast += cast
        lands_by_turn.append(len(battlefield_lands))
        cast_by_turn.append(cast)
        cumulative_by_turn.append(total_cast)
    return TrialResult(
        mulligans=mulligans,
        lands_in_play_by_turn=lands_by_turn,
        spells_cast_by_turn=cast_by_turn,
        cumulative_spells_by_turn=cumulative_by_turn,
    )


def _aggregate(
    trials: list[TrialResult], turns: int, on_the_play: bool, max_mulligans: int
) -> PlaytestStats:
    n = len(trials)
    distribution = [0] * (max_mulligans + 1)
    for t in trials:
        idx = min(t.mulligans, max_mulligans)
        distribution[idx] += 1
    per_turn: list[TurnStat] = []
    for turn_idx in range(turns):
        lands = [t.lands_in_play_by_turn[turn_idx] for t in trials]
        cast_cum = [t.cumulative_spells_by_turn[turn_idx] for t in trials]
        cast_this = [t.spells_cast_by_turn[turn_idx] for t in trials]
        played_land = sum(1 for t in trials if _played_land(t, turn_idx))
        cast_any = sum(1 for c in cast_this if c > 0)
        per_turn.append(
            TurnStat(
                turn=turn_idx + 1,
                avg_lands_in_play=sum(lands) / n,
                avg_spells_cast_cumulative=sum(cast_cum) / n,
                pct_land_drop=played_land / n,
                pct_cast_any=cast_any / n,
            )
        )
    avg_mulls = sum(t.mulligans for t in trials) / n
    avg_total = sum(t.cumulative_spells_by_turn[-1] for t in trials) / n if turns > 0 else 0.0
    return PlaytestStats(
        trials=n,
        turns=turns,
        on_the_play=on_the_play,
        avg_mulligans=avg_mulls,
        mulligan_distribution=distribution,
        avg_total_spells_cast=avg_total,
        per_turn=per_turn,
    )


def _played_land(trial: TrialResult, turn_idx: int) -> bool:
    prev = trial.lands_in_play_by_turn[turn_idx - 1] if turn_idx > 0 else 0
    return trial.lands_in_play_by_turn[turn_idx] > prev


def simulate(deck: DeckDetailResponse, request: PlaytestSimulateRequest) -> PlaytestStats:
    """Run ``request.trials`` goldfish games and return aggregate stats.

    Args:
        deck: The deck to simulate. Commander is intentionally excluded — it
            starts in the command zone, not the library.
        request: Sim parameters (trials, turns, on_the_play, mulligan cap, seed).

    Returns:
        Aggregate ``PlaytestStats`` across all trials.
    """
    library_template = _expand_deck(deck.cards)
    rng = random.Random(request.seed)
    results = [
        _run_trial(library_template, rng, request.turns, request.on_the_play, request.max_mulligans)
        for _ in range(request.trials)
    ]
    return _aggregate(results, request.turns, request.on_the_play, request.max_mulligans)
