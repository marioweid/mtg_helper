"""Goldfish playtest simulator.

Runs N trial games per deck and reports turn-by-turn aggregates. The sim is
pure-Python and deterministic when a ``seed`` is supplied. The mana model is
deliberately rough — basics by name, non-basics by ``color_identity`` — which
is enough fidelity to surface curve and land-count problems but won't catch
ETB-tapped or filter-land nuances.
"""

import random
import re
import statistics
from dataclasses import dataclass, field

from mtg_helper.models.decks import (
    CommanderCardSummary,
    DeckCardItem,
    DeckDetailResponse,
)
from mtg_helper.models.playtest import (
    ColorScrewStats,
    CommanderStats,
    OpeningHandStats,
    PlaytestSimulateRequest,
    PlaytestStats,
    TurnStat,
)

_COLORS: tuple[str, ...] = ("W", "U", "B", "R", "G", "C")
_SYMBOL_RE = re.compile(r"\{([^}]+)\}")
_DRAW_RE = re.compile(r"draw (a|one|two|three|four|five|\d+) cards?", re.IGNORECASE)
_DRAW_MAX = 5
_WORD_TO_INT: dict[str, int] = {
    "a": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}

_BASIC_LAND_PRODUCES: dict[str, str] = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
    "Wastes": "C",
}

# Basic-fetch detection: a land with no color identity (it doesn't tap for
# mana itself) whose oracle text describes searching the library. Captures
# Evolving Wilds, Terramorphic Expanse, Prismatic Vista. Excludes shock-fetches
# (Misty et al.) — those have non-empty color_identity and stay dual.
_FETCH_LIBRARY_RE = re.compile(r"search your library for", re.IGNORECASE)
# Tapped detection: covers "enters tapped", "enters the battlefield tapped"
# (older phrasing), and "onto the battlefield tapped" (fetched-land effects
# like Evolving Wilds).
_TAPPED_RE = re.compile(
    r"\b(?:enters\s+(?:the battlefield\s+)?tapped|battlefield\s+tapped)\b",
    re.IGNORECASE,
)
# Conditional-tapped escape hatches: shock lands ("you may pay 2 life…"),
# check lands and slow lands ("enters tapped unless…"). Assumes the player
# usually meets the condition — treat those as untapped.
_CONDITIONAL_UNTAPPED_RE = re.compile(
    r"(tapped\s+unless\b|you may pay)",
    re.IGNORECASE,
)
_ALL_COLORS_NON_C: tuple[str, ...] = ("W", "U", "B", "R", "G")

_INTERACTION_TAGS: frozenset[str] = frozenset({"removal", "board_wipe", "counterspell"})
_SELECTION_TAG = "card_selection"
_TUTOR_TAG = "tutor"

# Flood: hit a turn ≥ 4 with at least 2 more lands than the turn number AND
# used less than half the mana that turn. Screw: a turn ≥ 3 where the deck
# fell at least 2 lands behind on the curve. Thresholds tuned for Commander.
_FLOOD_TURN_FLOOR = 4
_FLOOD_LAND_EXCESS = 2
_FLOOD_UTILIZATION_CEIL = 0.5
_SCREW_TURN_FLOOR = 3
_SCREW_LAND_DEFICIT = 2

# Color screw: a turn ≥ this where the hand contains an affordable-by-CMC
# spell that can't be paid due to missing colored pips.
_COLOR_SCREW_TURN_FLOOR = 3


@dataclass(frozen=True)
class ParsedCost:
    """A mana cost split into generic + colored multiset. X costs treat X=0."""

    generic: int
    colored: tuple[tuple[str, int], ...]

    @property
    def total_mana_value(self) -> int:
        return self.generic + sum(count for _, count in self.colored)


@dataclass(frozen=True)
class SimCard:
    """Immutable per-card data the sim needs. Built once per deck."""

    name: str
    cmc: int
    is_land: bool
    produces: tuple[str, ...]
    cost: ParsedCost | None
    is_ramp: bool = False
    is_draw: bool = False
    draw_count: int = 0
    ramp_produces: tuple[str, ...] = ()
    is_interaction: bool = False
    is_selection: bool = False
    is_tutor: bool = False
    enters_tapped: bool = False


@dataclass(frozen=True)
class ManaSource:
    """A mana source on the battlefield. Lands enter immediately; ramp spells
    create sources usable from the following turn (no same-turn fast mana).
    """

    produces: tuple[str, ...]
    available_from_turn: int


@dataclass
class TurnCounts:
    """Per-turn effect counts produced by a single casting phase."""

    spells: int = 0
    mana_spent: int = 0
    cards_drawn_extra: int = 0
    selections: int = 0
    tutors: int = 0


@dataclass
class TrialResult:
    mulligans: int
    opening_lands: int
    lands_in_play_by_turn: list[int]
    mana_available_by_turn: list[int]
    mana_spent_by_turn: list[int]
    spells_cast_by_turn: list[int]
    cumulative_spells_by_turn: list[int]
    dead_cards_by_turn: list[int]
    color_dead_cards_by_turn: list[int]
    interaction_in_hand_by_turn: list[int]
    cards_drawn_extra_by_turn: list[int]
    selection_events_by_turn: list[int]
    tutors_cast_by_turn: list[int]
    cards_in_hand_by_turn: list[int]
    color_screw_shortages: set[str] = field(default_factory=set)
    first_color_screw_turn: int | None = None
    first_missed_land_turn: int | None = None
    total_mana_spent: int = field(default=0)
    commander_cast_turn: int | None = None
    partner_cast_turn: int | None = None


def _basic_land_color(name: str) -> str | None:
    base = name.split(" // ")[0]
    base = base.removeprefix("Snow-Covered ")
    return _BASIC_LAND_PRODUCES.get(base)


def _is_basic_fetch(card: DeckCardItem) -> bool:
    """Detect a 'fetch any basic' land: type_line contains Land, empty
    ``color_identity``, and oracle text describes a library search. Catches
    Evolving Wilds / Terramorphic Expanse / Prismatic Vista. Shock-fetches
    (Misty et al.) have non-empty color_identity and are excluded.
    """
    if "Land" not in (card.type_line or ""):
        return False
    if card.color_identity:
        return False
    text = card.oracle_text or ""
    return bool(_FETCH_LIBRARY_RE.search(text))


def _is_enters_tapped(card: DeckCardItem) -> bool:
    """Oracle-text heuristic: True when the land (or its fetched basic) enters
    tapped *unconditionally*. Shock lands ("you may pay 2 life"), check lands
    and slow lands ("enters tapped unless…") are treated as untapped on the
    assumption that the player meets the condition or pays the life.
    """
    text = card.oracle_text or ""
    if not _TAPPED_RE.search(text):
        return False
    if _CONDITIONAL_UNTAPPED_RE.search(text):
        return False
    return True


def _land_produces(card: DeckCardItem) -> tuple[str, ...]:
    basic = _basic_land_color(card.name)
    if basic is not None:
        return (basic,)
    identity = tuple(c for c in (card.color_identity or []) if c in _COLORS)
    if identity:
        return identity
    if _is_basic_fetch(card):
        return _ALL_COLORS_NON_C
    return ("C",)


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


def _parse_draw_count(oracle_text: str | None) -> int:
    if not oracle_text:
        return 1
    match = _DRAW_RE.search(oracle_text)
    if not match:
        return 1
    token = match.group(1).lower()
    if token.isdigit():
        return min(int(token), _DRAW_MAX)
    return _WORD_TO_INT.get(token, 1)


def _ramp_produces_for(card: DeckCardItem) -> tuple[str, ...]:
    identity = tuple(c for c in (card.color_identity or []) if c in _COLORS)
    return identity if identity else ("C",)


def _to_sim_card(card: DeckCardItem) -> SimCard:
    type_line = card.type_line or ""
    is_land = "Land" in type_line
    produces = _land_produces(card) if is_land else ()
    cost = None if is_land else parse_cost(card.mana_cost)
    cmc = int(card.cmc) if card.cmc is not None else 0
    stages = card.qualifying_stages or []
    tags = set(card.tags or [])
    is_ramp = not is_land and "ramp" in stages
    is_draw = not is_land and "draw" in stages
    draw_count = _parse_draw_count(card.oracle_text) if is_draw else 0
    ramp_produces = _ramp_produces_for(card) if is_ramp else ()
    is_interaction = not is_land and bool(tags & _INTERACTION_TAGS)
    is_selection = not is_land and _SELECTION_TAG in tags
    is_tutor = not is_land and _TUTOR_TAG in tags
    enters_tapped = is_land and _is_enters_tapped(card)
    return SimCard(
        name=card.name,
        cmc=cmc,
        is_land=is_land,
        produces=produces,
        cost=cost,
        is_ramp=is_ramp,
        is_draw=is_draw,
        draw_count=draw_count,
        ramp_produces=ramp_produces,
        is_interaction=is_interaction,
        is_selection=is_selection,
        is_tutor=is_tutor,
        enters_tapped=enters_tapped,
    )


def _summary_to_sim_card(summary: CommanderCardSummary) -> SimCard:
    """Build a sim card from a ``CommanderCardSummary``. Mirrors ``_to_sim_card``
    but reads tags directly from the summary (no ``qualifying_stages`` plumbing).
    """
    type_line = summary.type_line or ""
    is_land = "Land" in type_line
    cost = None if is_land else parse_cost(summary.mana_cost)
    cmc = int(summary.cmc) if summary.cmc is not None else 0
    tags = set(summary.tags or [])
    is_ramp = not is_land and "ramp" in tags
    is_draw = not is_land and "draw" in tags
    draw_count = _parse_draw_count(summary.oracle_text) if is_draw else 0
    identity = tuple(c for c in (summary.color_identity or []) if c in _COLORS)
    ramp_produces = (identity if identity else ("C",)) if is_ramp else ()
    is_interaction = not is_land and bool(tags & _INTERACTION_TAGS)
    is_selection = not is_land and _SELECTION_TAG in tags
    is_tutor = not is_land and _TUTOR_TAG in tags
    return SimCard(
        name=summary.name,
        cmc=cmc,
        is_land=is_land,
        produces=(),
        cost=cost,
        is_ramp=is_ramp,
        is_draw=is_draw,
        draw_count=draw_count,
        ramp_produces=ramp_produces,
        is_interaction=is_interaction,
        is_selection=is_selection,
        is_tutor=is_tutor,
    )


def _commander_sim_cards(deck: DeckDetailResponse) -> list[SimCard]:
    """Build command-zone sim cards (commander + optional partner)."""
    out: list[SimCard] = []
    if deck.commander_card is not None:
        out.append(_summary_to_sim_card(deck.commander_card))
    if deck.partner_card is not None:
        out.append(_summary_to_sim_card(deck.partner_card))
    return out


def _expand_deck(cards: list[DeckCardItem]) -> list[SimCard]:
    out: list[SimCard] = []
    for card in cards:
        sim = _to_sim_card(card)
        qty = max(1, card.quantity)
        out.extend([sim] * qty)
    return out


def _can_cast(cost: ParsedCost, sources: list[ManaSource]) -> bool:
    """Return True iff ``sources`` can collectively pay ``cost``.

    Solves the colored-requirement assignment with backtracking, then pays
    generic from any remaining source. ``sources.length`` must be at least the
    cost's total mana value for any chance of success.
    """
    required: list[str] = []
    for color, count in cost.colored:
        required.extend([color] * count)
    needed = len(required) + cost.generic
    if len(sources) < needed:
        return False
    used = [False] * len(sources)
    if not _assign_colored(required, 0, sources, used):
        return False
    remaining = sum(1 for u in used if not u)
    return remaining >= cost.generic


def _assign_colored(
    required: list[str], idx: int, sources: list[ManaSource], used: list[bool]
) -> bool:
    if idx >= len(required):
        return True
    color = required[idx]
    for i, source in enumerate(sources):
        if used[i] or color not in source.produces:
            continue
        used[i] = True
        if _assign_colored(required, idx + 1, sources, used):
            return True
        used[i] = False
    return False


def _pay_cost(cost: ParsedCost, sources: list[ManaSource]) -> list[ManaSource]:
    """Return the subset of sources consumed to pay ``cost``. Caller must have
    verified ``_can_cast`` first; mirrors that function's assignment order.
    """
    required: list[str] = []
    for color, count in cost.colored:
        required.extend([color] * count)
    used = [False] * len(sources)
    _assign_colored(required, 0, sources, used)
    for i in range(len(sources)):
        if cost.generic <= 0:
            break
        if not used[i]:
            used[i] = True
            cost = ParsedCost(generic=cost.generic - 1, colored=cost.colored)
    return [sources[i] for i in range(len(sources)) if used[i]]


def _color_shortage_for(cost: ParsedCost, sources: list[ManaSource]) -> set[str]:
    """Return the set of colors short for this cost. A color is short when the
    number of sources that can produce it is less than the cost's requirement
    for that color. Loose attribution for dual lands (counts a multi-color
    source toward each of its colors independently).
    """
    shortages: set[str] = set()
    for color, count in cost.colored:
        producers = sum(1 for s in sources if color in s.produces)
        if producers < count:
            shortages.add(color)
    return shortages


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
) -> tuple[list[SimCard], list[SimCard], int, int]:
    """Simulate the London mulligan. Returns ``(hand, library, mulligans,
    opening_lands)`` where opening_lands is the land count in the final
    pre-bottom 7-card hand.
    """
    mulligans = 0
    while True:
        library = library_template.copy()
        rng.shuffle(library)
        hand = library[:7]
        library = library[7:]
        if _should_keep(hand, mulligans, max_mulligans):
            opening_lands = _count_lands(hand)
            kept, bottomed = _bottom_hand(hand, mulligans)
            library.extend(bottomed)
            return kept, library, mulligans, opening_lands
        mulligans += 1


def _play_land(
    hand: list[SimCard], battlefield_lands: list[SimCard], mana_sources: list[ManaSource], turn: int
) -> bool:
    for i, card in enumerate(hand):
        if card.is_land:
            battlefield_lands.append(card)
            available_from = turn + 1 if card.enters_tapped else turn
            mana_sources.append(
                ManaSource(produces=card.produces, available_from_turn=available_from)
            )
            hand.pop(i)
            return True
    return False


def _resolve_card_draw_effect(spell: SimCard, hand: list[SimCard], library: list[SimCard]) -> int:
    """Apply a spell's draw/tutor effect to ``hand``. Tutors approximate as
    ``draw 1`` from top of library. Returns the number of cards moved from
    library to hand.
    """
    to_draw = spell.draw_count
    if spell.is_tutor and to_draw == 0:
        to_draw = 1
    if to_draw <= 0:
        return 0
    actual = min(to_draw, len(library))
    if actual <= 0:
        return 0
    drawn = library[:actual]
    del library[:actual]
    hand.extend(drawn)
    return actual


def _remove_cast_spell(spell: SimCard, hand: list[SimCard], zone: list[SimCard]) -> bool:
    """Remove a resolved spell from its source list. Returns ``True`` if the
    spell came from the command zone (identity check), else ``False``.
    """
    if any(s is spell for s in zone):
        zone.remove(spell)
        return True
    hand.remove(spell)
    return False


def _apply_spell_effects(
    spell: SimCard,
    counts: TurnCounts,
    hand: list[SimCard],
    library: list[SimCard],
    mana_sources: list[ManaSource],
    turn: int,
) -> None:
    """Apply a resolved spell's effects to counts and game state."""
    counts.spells += 1
    counts.mana_spent += spell.cmc
    if spell.is_selection:
        counts.selections += 1
    if spell.is_tutor:
        counts.tutors += 1
    drawn = _resolve_card_draw_effect(spell, hand, library)
    counts.cards_drawn_extra += drawn
    if spell.is_ramp:
        mana_sources.append(ManaSource(produces=spell.ramp_produces, available_from_turn=turn + 1))


def _cast_turn(
    hand: list[SimCard],
    library: list[SimCard],
    mana_sources: list[ManaSource],
    turn: int,
    command_zone: list[SimCard] | None = None,
) -> tuple[TurnCounts, list[SimCard]]:
    """Repeatedly cast the highest-CMC castable spell until none remain.
    Commands from ``command_zone`` are included in the candidate pool and
    removed from there when chosen.
    """
    counts = TurnCounts()
    zone = command_zone if command_zone is not None else []
    resolved_from_zone: list[SimCard] = []
    available = [s for s in mana_sources if s.available_from_turn <= turn]
    while True:
        candidates = [c for c in hand if not c.is_land] + zone
        castable = [c for c in candidates if c.cost is not None and _can_cast(c.cost, available)]
        if not castable:
            return counts, resolved_from_zone
        spell = max(castable, key=lambda c: c.cmc)
        assert spell.cost is not None
        consumed = _pay_cost(spell.cost, available)
        for src in consumed:
            available.remove(src)
        if _remove_cast_spell(spell, hand, zone):
            resolved_from_zone.append(spell)
        _apply_spell_effects(spell, counts, hand, library, mana_sources, turn)


def _count_hand_state(
    hand: list[SimCard], turn_available: list[ManaSource]
) -> tuple[int, int, int, set[str]]:
    """For the end-of-turn hand, return (dead, color_dead, interaction, color_shortages).

    - ``dead``: non-land non-interaction cards that can't be cast with this turn's mana.
    - ``color_dead``: subset of dead where total mana would suffice but colors block.
    - ``interaction``: removal/board wipe/counterspell cards held in hand.
    - ``color_shortages``: union of missing-color sets across all color-dead cards.
    """
    dead = 0
    color_dead = 0
    interaction = 0
    shortages: set[str] = set()
    total_available = len(turn_available)
    for card in hand:
        if card.is_land:
            continue
        if card.is_interaction:
            interaction += 1
            continue
        if card.cost is None or not _can_cast(card.cost, turn_available):
            dead += 1
            if card.cost is not None and total_available >= card.cost.total_mana_value:
                color_dead += 1
                shortages |= _color_shortage_for(card.cost, turn_available)
    return dead, color_dead, interaction, shortages


def _record_commander_casts(
    resolved_zone: list[SimCard],
    template: list[SimCard],
    commander_cast_turn: int | None,
    partner_cast_turn: int | None,
    turn: int,
) -> tuple[int | None, int | None]:
    if not resolved_zone or not template:
        return commander_cast_turn, partner_cast_turn
    primary = template[0].name
    partner = template[1].name if len(template) > 1 else None
    for resolved in resolved_zone:
        if commander_cast_turn is None and resolved.name == primary:
            commander_cast_turn = turn
        elif partner_cast_turn is None and partner is not None and resolved.name == partner:
            partner_cast_turn = turn
    return commander_cast_turn, partner_cast_turn


def _run_trial(
    library_template: list[SimCard],
    rng: random.Random,
    turns: int,
    on_the_play: bool,
    max_mulligans: int,
    command_zone_template: list[SimCard],
) -> TrialResult:
    hand, library, mulligans, opening_lands = _draw_opening(library_template, rng, max_mulligans)
    battlefield_lands: list[SimCard] = []
    mana_sources: list[ManaSource] = []
    lands_by_turn: list[int] = []
    mana_by_turn: list[int] = []
    mana_spent_by_turn: list[int] = []
    cast_by_turn: list[int] = []
    cumulative_by_turn: list[int] = []
    dead_by_turn: list[int] = []
    color_dead_by_turn: list[int] = []
    interaction_by_turn: list[int] = []
    drawn_extra_by_turn: list[int] = []
    selection_by_turn: list[int] = []
    tutors_by_turn: list[int] = []
    hand_by_turn: list[int] = []
    color_shortages: set[str] = set()
    first_color_screw: int | None = None
    command_zone: list[SimCard] = list(command_zone_template)
    commander_cast_turn: int | None = None
    partner_cast_turn: int | None = None
    total_cast = 0
    total_mana_spent = 0
    first_missed = None
    prev_lands = 0
    for turn in range(1, turns + 1):
        if turn > 1 or not on_the_play:
            if library:
                hand.append(library.pop(0))
        _play_land(hand, battlefield_lands, mana_sources, turn)
        active = sum(1 for s in mana_sources if s.available_from_turn <= turn)
        counts, resolved_zone = _cast_turn(hand, library, mana_sources, turn, command_zone)
        commander_cast_turn, partner_cast_turn = _record_commander_casts(
            resolved_zone, command_zone_template, commander_cast_turn, partner_cast_turn, turn
        )
        total_cast += counts.spells
        total_mana_spent += counts.mana_spent
        turn_available = [s for s in mana_sources if s.available_from_turn <= turn]
        dead, color_dead, held_interaction, turn_shortages = _count_hand_state(hand, turn_available)
        if turn >= _COLOR_SCREW_TURN_FLOOR and color_dead > 0:
            if first_color_screw is None:
                first_color_screw = turn
            color_shortages |= turn_shortages
        lands_now = len(battlefield_lands)
        if first_missed is None and lands_now == prev_lands:
            first_missed = turn
        prev_lands = lands_now
        lands_by_turn.append(lands_now)
        mana_by_turn.append(active)
        mana_spent_by_turn.append(counts.mana_spent)
        cast_by_turn.append(counts.spells)
        cumulative_by_turn.append(total_cast)
        dead_by_turn.append(dead)
        color_dead_by_turn.append(color_dead)
        interaction_by_turn.append(held_interaction)
        drawn_extra_by_turn.append(counts.cards_drawn_extra)
        selection_by_turn.append(counts.selections)
        tutors_by_turn.append(counts.tutors)
        hand_by_turn.append(len(hand))
    return TrialResult(
        mulligans=mulligans,
        opening_lands=opening_lands,
        lands_in_play_by_turn=lands_by_turn,
        mana_available_by_turn=mana_by_turn,
        mana_spent_by_turn=mana_spent_by_turn,
        spells_cast_by_turn=cast_by_turn,
        cumulative_spells_by_turn=cumulative_by_turn,
        dead_cards_by_turn=dead_by_turn,
        color_dead_cards_by_turn=color_dead_by_turn,
        interaction_in_hand_by_turn=interaction_by_turn,
        cards_drawn_extra_by_turn=drawn_extra_by_turn,
        selection_events_by_turn=selection_by_turn,
        tutors_cast_by_turn=tutors_by_turn,
        cards_in_hand_by_turn=hand_by_turn,
        color_screw_shortages=color_shortages,
        first_color_screw_turn=first_color_screw,
        first_missed_land_turn=first_missed,
        total_mana_spent=total_mana_spent,
        commander_cast_turn=commander_cast_turn,
        partner_cast_turn=partner_cast_turn,
    )


def _classify_flood_screw(trial: TrialResult) -> str:
    """Return ``"flood"``, ``"screw"``, or ``"ok"`` for a trial.

    Flood: a turn ≥ ``_FLOOD_TURN_FLOOR`` had at least ``_FLOOD_LAND_EXCESS`` more
    lands than the turn number AND mana utilization below ``_FLOOD_UTILIZATION_CEIL``.
    Screw: a turn ≥ ``_SCREW_TURN_FLOOR`` had at least ``_SCREW_LAND_DEFICIT``
    fewer lands than the turn number. Screw takes priority if both apply.
    """
    for idx, lands in enumerate(trial.lands_in_play_by_turn):
        turn = idx + 1
        if turn >= _SCREW_TURN_FLOOR and lands <= turn - _SCREW_LAND_DEFICIT:
            return "screw"
    for idx, lands in enumerate(trial.lands_in_play_by_turn):
        turn = idx + 1
        if turn < _FLOOD_TURN_FLOOR or lands < turn + _FLOOD_LAND_EXCESS:
            continue
        available = trial.mana_available_by_turn[idx]
        spent = trial.mana_spent_by_turn[idx]
        utilization = spent / available if available > 0 else 0.0
        if utilization < _FLOOD_UTILIZATION_CEIL:
            return "flood"
    return "ok"


def _quantiles_or_zero(values: list[int]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    if len(values) == 1:
        only = float(values[0])
        return only, only, only
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[0], q[1], q[2]


def _opening_hand_stats(
    trials: list[TrialResult], mulligan_distribution: list[int]
) -> OpeningHandStats:
    n = len(trials)
    screwed = sum(1 for t in trials if t.opening_lands <= 1)
    flood = sum(1 for t in trials if t.opening_lands >= 6)
    balanced = n - screwed - flood
    kept_7 = mulligan_distribution[0] if len(mulligan_distribution) > 0 else 0
    kept_6 = mulligan_distribution[1] if len(mulligan_distribution) > 1 else 0
    kept_5 = mulligan_distribution[2] if len(mulligan_distribution) > 2 else 0
    kept_le4 = sum(mulligan_distribution[3:]) if len(mulligan_distribution) > 3 else 0
    return OpeningHandStats(
        pct_screwed_mull=screwed / n,
        pct_balanced=balanced / n,
        pct_flood_mull=flood / n,
        pct_kept_7=kept_7 / n,
        pct_kept_6=kept_6 / n,
        pct_kept_5=kept_5 / n,
        pct_kept_le4=kept_le4 / n,
    )


def _build_color_screw(trials: list[TrialResult]) -> ColorScrewStats:
    n = len(trials)
    if n == 0:
        return ColorScrewStats(pct_color_screw=0.0, shortages_by_color={})
    screwed = sum(1 for t in trials if t.first_color_screw_turn is not None)
    by_color: dict[str, int] = {color: 0 for color in _COLORS}
    for t in trials:
        for color in t.color_screw_shortages:
            if color in by_color:
                by_color[color] += 1
    shortages = {color: count / n for color, count in by_color.items() if count > 0}
    return ColorScrewStats(pct_color_screw=screwed / n, shortages_by_color=shortages)


def _build_turn_stat(turn_idx: int, trials: list[TrialResult]) -> TurnStat:
    n = len(trials)
    lands = [t.lands_in_play_by_turn[turn_idx] for t in trials]
    mana = [t.mana_available_by_turn[turn_idx] for t in trials]
    spent = [t.mana_spent_by_turn[turn_idx] for t in trials]
    cast_cum = [t.cumulative_spells_by_turn[turn_idx] for t in trials]
    cast_this = [t.spells_cast_by_turn[turn_idx] for t in trials]
    dead = [t.dead_cards_by_turn[turn_idx] for t in trials]
    color_dead = [t.color_dead_cards_by_turn[turn_idx] for t in trials]
    interaction = [t.interaction_in_hand_by_turn[turn_idx] for t in trials]
    drawn = [t.cards_drawn_extra_by_turn[turn_idx] for t in trials]
    selection = [t.selection_events_by_turn[turn_idx] for t in trials]
    tutors = [t.tutors_cast_by_turn[turn_idx] for t in trials]
    hand = [t.cards_in_hand_by_turn[turn_idx] for t in trials]
    played_land = sum(1 for t in trials if _played_land(t, turn_idx))
    cast_any = sum(1 for c in cast_this if c > 0)
    util_samples = [s / m for s, m in zip(spent, mana, strict=True) if m > 0]
    utilization = sum(util_samples) / len(util_samples) if util_samples else 0.0
    lands_p25, lands_p50, lands_p75 = _quantiles_or_zero(lands)
    mana_p25, mana_p50, mana_p75 = _quantiles_or_zero(mana)
    return TurnStat(
        turn=turn_idx + 1,
        avg_lands_in_play=sum(lands) / n,
        avg_mana_available=sum(mana) / n,
        avg_mana_spent=sum(spent) / n,
        mana_utilization=utilization,
        avg_spells_cast_cumulative=sum(cast_cum) / n,
        pct_land_drop=played_land / n,
        pct_cast_any=cast_any / n,
        avg_dead_cards=sum(dead) / n,
        avg_color_dead_cards=sum(color_dead) / n,
        avg_interaction_in_hand=sum(interaction) / n,
        avg_cards_drawn_extra=sum(drawn) / n,
        avg_selection_events=sum(selection) / n,
        avg_tutors_cast=sum(tutors) / n,
        avg_cards_in_hand=sum(hand) / n,
        lands_p25=lands_p25,
        lands_p50=lands_p50,
        lands_p75=lands_p75,
        mana_p25=mana_p25,
        mana_p50=mana_p50,
        mana_p75=mana_p75,
    )


def _commander_stats(trials: list[TrialResult], turns: int, name: str, slot: str) -> CommanderStats:
    n = len(trials)
    sentinel = float(turns + 1)
    raw_turns = [
        (t.commander_cast_turn if slot == "commander" else t.partner_cast_turn) for t in trials
    ]
    cast_turns = [v if v is not None else turns + 1 for v in raw_turns]
    avg = sum(cast_turns) / n if n else sentinel
    pct_ever = sum(1 for v in raw_turns if v is not None) / n if n else 0.0
    return CommanderStats(name=name, avg_cast_turn=avg, pct_ever_cast=pct_ever)


def _aggregate(
    trials: list[TrialResult],
    turns: int,
    on_the_play: bool,
    max_mulligans: int,
    deck: DeckDetailResponse,
) -> PlaytestStats:
    n = len(trials)
    distribution = [0] * (max_mulligans + 1)
    for t in trials:
        idx = min(t.mulligans, max_mulligans)
        distribution[idx] += 1
    per_turn = [_build_turn_stat(i, trials) for i in range(turns)]
    avg_mulls = sum(t.mulligans for t in trials) / n
    totals = [t.cumulative_spells_by_turn[-1] for t in trials] if turns > 0 else []
    avg_total = sum(totals) / n if totals else 0.0
    total_stddev = statistics.pstdev(totals) if len(totals) > 1 else 0.0
    classifications = [_classify_flood_screw(t) for t in trials]
    pct_flood = classifications.count("flood") / n
    pct_screw = classifications.count("screw") / n
    miss_turns = [
        t.first_missed_land_turn if t.first_missed_land_turn is not None else turns + 1
        for t in trials
    ]
    avg_first_missed = sum(miss_turns) / n if miss_turns else float(turns + 1)
    commander_stats = (
        _commander_stats(trials, turns, deck.commander_card.name, "commander")
        if deck.commander_card is not None
        else None
    )
    partner_stats = (
        _commander_stats(trials, turns, deck.partner_card.name, "partner")
        if deck.partner_card is not None
        else None
    )
    return PlaytestStats(
        trials=n,
        turns=turns,
        on_the_play=on_the_play,
        avg_mulligans=avg_mulls,
        mulligan_distribution=distribution,
        avg_total_spells_cast=avg_total,
        total_spells_stddev=total_stddev,
        pct_flood=pct_flood,
        pct_screw=pct_screw,
        avg_first_missed_land_turn=avg_first_missed,
        opening_hand=_opening_hand_stats(trials, distribution),
        color_screw=_build_color_screw(trials),
        commander=commander_stats,
        partner=partner_stats,
        per_turn=per_turn,
    )


def _played_land(trial: TrialResult, turn_idx: int) -> bool:
    prev = trial.lands_in_play_by_turn[turn_idx - 1] if turn_idx > 0 else 0
    return trial.lands_in_play_by_turn[turn_idx] > prev


def simulate(deck: DeckDetailResponse, request: PlaytestSimulateRequest) -> PlaytestStats:
    """Run ``request.trials`` goldfish games and return aggregate stats.

    The commander (and partner, when present) is modeled as a virtual card in
    the command zone and cast as soon as affordable. Its tag-derived effects
    (ramp/draw/tutor/interaction) apply normally on cast.
    """
    library_template = _expand_deck(deck.cards)
    rng = random.Random(request.seed)
    command_zone_template = _commander_sim_cards(deck)
    results = [
        _run_trial(
            library_template,
            rng,
            request.turns,
            request.on_the_play,
            request.max_mulligans,
            command_zone_template,
        )
        for _ in range(request.trials)
    ]
    return _aggregate(
        results,
        request.turns,
        request.on_the_play,
        request.max_mulligans,
        deck,
    )
