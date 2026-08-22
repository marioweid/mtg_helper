"""Deterministic signal-lane extraction for Commander Coach specialists."""

import re
from dataclasses import dataclass
from typing import Literal

from mtg_helper.models.ai import (
    CoachRoleBudgetReport,
    CoachSignalLane,
    CoachSignalReport,
    CoachSynergyReport,
)
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse

LaneRole = Literal["engine", "payoff", "support", "interaction", "mana", "risk"]
LaneStrength = Literal["core", "present", "thin"]
LaneSource = Literal["commander", "tags", "cards", "memory", "role_budget", "synergy"]


@dataclass(frozen=True)
class LaneSpec:
    """Detection terms and role metadata for one MTG strategy lane."""

    name: str
    role: LaneRole
    terms: tuple[str, ...]
    protect: bool = False


_LANE_SPECS: tuple[LaneSpec, ...] = (
    LaneSpec("food_generation", "engine", ("food",), True),
    LaneSpec("squirrel_generation", "engine", ("squirrel",), True),
    LaneSpec("sacrifice", "engine", ("sacrifice",), True),
    LaneSpec("death_payoffs", "payoff", ("dies", "loses life", "whenever a creature dies")),
    LaneSpec("token_payoffs", "payoff", ("token", "tokens", "creatures you control")),
    LaneSpec("token_doubling", "payoff", ("twice", "additional token", "tokens instead")),
    LaneSpec("graveyard_value", "support", ("graveyard", "return target", "return a card")),
    LaneSpec("x_spells", "payoff", ("{x}", "x spell", "mana value x"), True),
    LaneSpec("hydras", "payoff", ("hydra",), True),
    LaneSpec("counter_scaling", "payoff", ("+1/+1 counter", "counters", "proliferate")),
    LaneSpec("voltron", "engine", ("equipment", "aura", "commander damage")),
    LaneSpec("blink", "engine", ("exile", "return it to the battlefield", "enters")),
    LaneSpec("lifegain", "engine", ("gain life", "lifegain")),
    LaneSpec("card_advantage", "support", ("draw", "look at the top", "impulse")),
    LaneSpec("interaction", "interaction", ("destroy", "exile", "counter target", "fight")),
    LaneSpec("mana_acceleration", "mana", ("add one mana", "search your library for a land")),
)

_TAG_TO_LANES: dict[str, tuple[str, ...]] = {
    "food_matters": ("food_generation", "token_payoffs", "sacrifice"),
    "squirrel_tribal": ("squirrel_generation", "token_payoffs"),
    "aristocrats": ("sacrifice", "death_payoffs", "token_payoffs"),
    "sacrifice": ("sacrifice", "death_payoffs"),
    "plus_one_counters": ("counter_scaling",),
    "proliferate": ("counter_scaling",),
    "voltron": ("voltron",),
    "equipment": ("voltron",),
    "blink": ("blink",),
    "lifegain": ("lifegain",),
    "graveyard": ("graveyard_value",),
    "reanimator": ("graveyard_value",),
    "token": ("token_payoffs",),
    "treasure_matters": ("mana_acceleration", "token_payoffs"),
    "clue_matters": ("card_advantage", "token_payoffs"),
}


def analyze_signals(
    deck: DeckDetailResponse,
    *,
    memory: str | None = None,
    roles: CoachRoleBudgetReport | None = None,
    synergy: CoachSynergyReport | None = None,
) -> CoachSignalReport:
    """Build a compact lane map from commander text, tags, cards, memory, and reports."""
    lanes: dict[str, CoachSignalLane] = {}
    commander_blob = _commander_blob(deck)
    tag_lanes = _lanes_from_tags(deck)
    memory_blob = (memory or "").lower()
    for spec in _LANE_SPECS:
        examples = _matching_cards(deck.cards, spec.terms)
        source = _source_for_lane(spec, commander_blob, tag_lanes, memory_blob, examples)
        if source is None:
            continue
        strength = _strength(spec.name, source, examples, synergy)
        lanes[spec.name] = CoachSignalLane(
            name=spec.name,
            role=spec.role,
            strength=strength,
            source=source,
            terms=list(spec.terms),
            examples=examples[:5],
            protect=spec.protect or strength == "core",
        )
    _merge_report_lanes(lanes, roles, synergy)
    lane_list = sorted(lanes.values(), key=_lane_sort_key)
    protected = _protected_cards(deck.cards, lane_list, memory_blob)
    core = [lane.name for lane in lane_list if lane.strength == "core"]
    weak = [lane.name for lane in lane_list if lane.strength == "thin"]
    return CoachSignalReport(
        summary=_summary(lane_list, core, weak),
        lanes=lane_list,
        core_lanes=core,
        weak_lanes=weak,
        protected_cards=protected,
    )


def lane_names(report: CoachSignalReport | None, *, core_only: bool = False) -> list[str]:
    """Return stable lane names for prompt payloads and deterministic filters."""
    if report is None:
        return []
    if core_only:
        return report.core_lanes
    return [lane.name for lane in report.lanes]


def card_overlaps_protected_lane(card: DeckCardItem, report: CoachSignalReport | None) -> bool:
    """Return whether a card appears to support a protected lane."""
    if report is None:
        return False
    blob = _card_blob(card)
    protected = [lane for lane in report.lanes if lane.protect]
    return any(_has_any(blob, tuple(lane.terms)) for lane in protected)


def _source_for_lane(
    spec: LaneSpec,
    commander_blob: str,
    tag_lanes: set[str],
    memory_blob: str,
    examples: list[str],
) -> LaneSource | None:
    if _has_any(commander_blob, spec.terms):
        return "commander"
    if spec.name in tag_lanes:
        return "tags"
    if _has_any(memory_blob, spec.terms):
        return "memory"
    if examples:
        return "cards"
    return None


def _strength(
    lane_name: str,
    source: LaneSource,
    examples: list[str],
    synergy: CoachSynergyReport | None,
) -> LaneStrength:
    if source in {"commander", "memory"}:
        return "core"
    if synergy and lane_name in synergy.weak_packages:
        return "thin"
    if source == "tags" and len(examples) >= 3:
        return "core"
    if len(examples) >= 5:
        return "core"
    return "present" if examples or source == "tags" else "thin"


def _merge_report_lanes(
    lanes: dict[str, CoachSignalLane],
    roles: CoachRoleBudgetReport | None,
    synergy: CoachSynergyReport | None,
) -> None:
    if roles:
        for role in roles.priority_roles:
            _upsert_lane(
                lanes,
                f"role_gap_{role}",
                "support",
                "thin",
                "role_budget",
                terms=[role],
            )
    if synergy:
        for package in synergy.weak_packages:
            _upsert_lane(lanes, package, "support", "thin", "synergy", terms=[package])


def _upsert_lane(
    lanes: dict[str, CoachSignalLane],
    name: str,
    role: LaneRole,
    strength: LaneStrength,
    source: LaneSource,
    *,
    terms: list[str],
) -> None:
    if name in lanes:
        return
    lanes[name] = CoachSignalLane(
        name=name,
        role=role,
        strength=strength,
        source=source,
        terms=terms,
    )


def _protected_cards(
    cards: list[DeckCardItem],
    lanes: list[CoachSignalLane],
    memory: str,
) -> list[str]:
    protected_terms = tuple(term for lane in lanes if lane.protect for term in lane.terms)
    names = [card.name for card in cards if _has_any(_card_blob(card), protected_terms)]
    if any(word in memory for word in ("protect", "keep", "preserve", "do not cut", "don't cut")):
        names.extend(card.name for card in cards if card.name.lower() in memory)
    return sorted(set(names))[:16]


def _matching_cards(cards: list[DeckCardItem], terms: tuple[str, ...]) -> list[str]:
    return [card.name for card in cards if _has_any(_card_blob(card), terms)]


def _lanes_from_tags(deck: DeckDetailResponse) -> set[str]:
    lanes: set[str] = set()
    for tag in deck.archetype_tags or []:
        lanes.update(_TAG_TO_LANES.get(tag, ()))
        if tag.endswith("_tribal"):
            lanes.add("token_payoffs")
    return lanes


def _lane_sort_key(lane: CoachSignalLane) -> tuple[int, int, str]:
    strength = {"core": 0, "thin": 1, "present": 2}[lane.strength]
    role = {"engine": 0, "payoff": 1, "support": 2, "interaction": 3, "mana": 4, "risk": 5}[
        lane.role
    ]
    return (strength, role, lane.name)


def _summary(lanes: list[CoachSignalLane], core: list[str], weak: list[str]) -> str:
    if not lanes:
        return "No clear signal lanes detected; use broad commander fundamentals."
    parts = [f"Core lanes: {', '.join(core[:4]) or 'none'}."]
    if weak:
        parts.append(f"Thin lanes to improve: {', '.join(weak[:4])}.")
    return " ".join(parts)


def _commander_blob(deck: DeckDetailResponse) -> str:
    parts: list[str] = []
    for commander in (deck.commander_card, deck.partner_card):
        if commander is None:
            continue
        parts.extend([commander.name, commander.oracle_text or ""])
    return _normalize(" ".join(parts))


def _card_blob(card: DeckCardItem) -> str:
    return _normalize(
        " ".join(
            [
                card.name,
                card.type_line or "",
                card.oracle_text or "",
                " ".join(card.tags or []),
                " ".join(card.categories or []),
                " ".join(card.qualifying_stages or []),
            ]
        )
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term and term.lower() in text for term in terms)
