"""Validation helpers for Commander Coach specialist outputs."""

import re
from dataclasses import dataclass

from mtg_helper.models.ai import DeckDoctorResponse, DoctorCut, DoctorSwap
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse


@dataclass(frozen=True)
class ValidationIssue:
    """A rejected recommendation with an actionable reason."""

    item_type: str
    names: tuple[str, ...]
    reason: str


_ENGINE_WORDS: frozenset[str] = frozenset(
    {
        "counter",
        "counters",
        "sacrifice",
        "token",
        "tokens",
        "food",
        "saga",
        "enchantment",
        "aura",
        "equipment",
        "graveyard",
        "return",
        "draw",
        "add",
        "mana",
        "land",
        "proliferate",
        "dies",
        "whenever",
        "choose",
        "may",
        "mode",
        "option",
        "grave",
    }
)

_FLEXIBILITY_WORDS: frozenset[str] = frozenset(
    {
        "choose",
        "may",
        "or",
        "graveyard",
        "grave",
        "return",
        "exile",
        "draw",
        "token",
        "tokens",
    }
)


def _card_tags(card: DeckCardItem) -> set[str]:
    return set(card.tags or []) | set(card.categories or []) | set(card.qualifying_stages or [])


def _words(text: str | None) -> set[str]:
    if not text:
        return set()
    return {w for w in re.findall(r"[a-z_+]+", text.lower()) if len(w) >= 3}


def _card_engine_words(card: DeckCardItem) -> set[str]:
    return (_words(card.oracle_text) | _words(card.type_line) | _card_tags(card)) & _ENGINE_WORDS


def _add_words(swap: DoctorSwap) -> set[str]:
    words: set[str] = set()
    for card in swap.add:
        words.update(card.tags or [])
        words.update(_words(card.type_line))
        words.update(_words(card.oracle_text))
    return words


def _is_flexible_addition(swap: DoctorSwap) -> bool:
    words = _add_words(swap)
    return len(words & _FLEXIBILITY_WORDS) >= 2


def _commander_words(deck: DeckDetailResponse) -> set[str]:
    words: set[str] = set()
    for commander in (deck.commander_card, deck.partner_card):
        if commander is None:
            continue
        words.update(_words(commander.oracle_text))
        words.update(_words(commander.type_line))
    return words & _ENGINE_WORDS


def _memory_terms(coach_memory_notes: str | None) -> set[str]:
    words = _words(coach_memory_notes)
    terms: set[str] = set()
    if {"food", "squirrel", "token", "tokens", "sacrifice"} & words:
        terms.update(words & {"food", "squirrel", "token", "tokens", "sacrifice"})
    if {"counter", "counters", "proliferate"} & words:
        terms.update({"counter", "counters", "proliferate"} & words)
    return terms


def _memory_protected_names(
    deck: DeckDetailResponse,
    coach_memory_notes: str | None,
) -> set[str]:
    if not coach_memory_notes:
        return set()
    text = coach_memory_notes.lower()
    protect_words = ("protect", "preserve", "keep", "core", "engine", "don't cut", "do not cut")
    if not any(word in text for word in protect_words):
        return set()
    return {card.name for card in deck.cards if card.name.lower() in text}


def _theme_tags(deck: DeckDetailResponse, coach_memory_notes: str | None = None) -> set[str]:
    tags = set(deck.archetype_tags or []) | _memory_terms(coach_memory_notes)
    if "food_matters" in tags:
        tags.update({"food_matters", "food", "token", "sacrifice"})
    if "squirrel_tribal" in tags:
        tags.update({"squirrel", "token", "anthem"})
    if "aristocrats" in tags or "sacrifice" in tags:
        tags.update({"aristocrats", "sacrifice", "token", "graveyard"})
    if "treasure_matters" in tags:
        tags.update({"treasure_matters", "treasure", "token", "ramp"})
    if "clue_matters" in tags:
        tags.update({"clue_matters", "clue", "token", "draw"})
    return tags


def _deck_cards_by_name(deck: DeckDetailResponse) -> dict[str, DeckCardItem]:
    return {card.name: card for card in deck.cards}


def _add_tags(swap: DoctorSwap) -> set[str]:
    tags: set[str] = set()
    for card in swap.add:
        tags.update(card.tags or [])
    return tags


def _validate_cut(
    cut: DoctorCut,
    deck_cards: dict[str, DeckCardItem],
    theme: set[str],
    commander_words: set[str],
    protected_names: set[str],
) -> ValidationIssue | None:
    card = deck_cards.get(cut.card_name)
    if card is None:
        return ValidationIssue("cut", (cut.card_name,), "cut card is not in the deck")
    overlap = _card_tags(card) & theme
    commander_overlap = _card_engine_words(card) & commander_words
    if cut.card_name in protected_names and cut.confidence != "high":
        return ValidationIssue(
            "cut",
            (cut.card_name,),
            "cuts a card protected by persistent Coach memory without high confidence",
        )
    if commander_overlap and cut.confidence != "high":
        return ValidationIssue(
            "cut",
            (cut.card_name,),
            "cuts a card that directly overlaps the commander's engine "
            f"({', '.join(sorted(commander_overlap))}) without high confidence",
        )
    if overlap and cut.confidence != "high":
        return ValidationIssue(
            "cut",
            (cut.card_name,),
            f"cuts a theme-engine card ({', '.join(sorted(overlap))}) without high confidence",
        )
    return None


def _validate_swap(
    swap: DoctorSwap,
    deck_cards: dict[str, DeckCardItem],
    deck_names: set[str],
    theme: set[str],
    commander_words: set[str],
    protected_names: set[str],
) -> ValidationIssue | None:
    missing = [name for name in swap.remove if name not in deck_cards]
    if missing:
        return ValidationIssue("swap", tuple(swap.remove), f"remove card not in deck: {missing[0]}")
    duplicate_adds = [card.name for card in swap.add if card.name in deck_names]
    if duplicate_adds:
        return ValidationIssue(
            "swap", tuple(swap.remove), f"add card already in deck: {duplicate_adds[0]}"
        )

    has_each_reason = all(name.lower() in swap.reason.lower() for name in swap.remove)
    if len(swap.remove) > 2 and not has_each_reason:
        return ValidationIssue(
            "swap",
            tuple(swap.remove),
            "multi-cut swap lacks card-specific reasoning for every removed card",
        )

    add_tags = _add_tags(swap)
    added_words = _add_words(swap) | add_tags
    for name in swap.remove:
        removed = deck_cards[name]
        if name in protected_names:
            return ValidationIssue(
                "swap",
                tuple(swap.remove),
                f"removes {name}, which is protected by persistent Coach memory",
            )
        removed_tags = _card_tags(removed)
        theme_overlap = removed_tags & theme
        if not theme_overlap:
            continue
        preserves_theme = bool(add_tags & theme_overlap) or bool(add_tags & theme)
        preserves_role = bool(add_tags & removed_tags)
        removed_engine_words = _card_engine_words(removed)
        commander_overlap = removed_engine_words & commander_words
        preserves_engine_text = bool(removed_engine_words & added_words)
        preserves_commander_text = not commander_overlap or bool(commander_overlap & added_words)
        flexible_utility = _is_flexible_addition(swap) and bool(added_words & theme)
        if not preserves_commander_text:
            return ValidationIssue(
                "swap",
                tuple(swap.remove),
                f"removes {name}, which directly overlaps the commander's engine "
                f"({', '.join(sorted(commander_overlap))}), but additions do not preserve it",
            )
        if not (preserves_theme or preserves_role or preserves_engine_text or flexible_utility):
            return ValidationIssue(
                "swap",
                tuple(swap.remove),
                f"removes {name}, a theme/engine card "
                f"({', '.join(sorted(theme_overlap or removed_engine_words))}), "
                "but the additions do not preserve that theme, role, or engine text",
            )
    return None


def validate_doctor_output(
    deck: DeckDetailResponse,
    output: DeckDoctorResponse,
    coach_memory_notes: str | None = None,
) -> list[ValidationIssue]:
    """Return theme/legality issues found in a doctor response."""
    deck_cards = _deck_cards_by_name(deck)
    deck_names = set(deck_cards)
    theme = _theme_tags(deck, coach_memory_notes)
    commander_words = _commander_words(deck) | _memory_terms(coach_memory_notes)
    protected_names = _memory_protected_names(deck, coach_memory_notes)
    issues: list[ValidationIssue] = []
    for cut in output.cuts:
        if issue := _validate_cut(cut, deck_cards, theme, commander_words, protected_names):
            issues.append(issue)
    for swap in output.swaps:
        if issue := _validate_swap(
            swap,
            deck_cards,
            deck_names,
            theme,
            commander_words,
            protected_names,
        ):
            issues.append(issue)
    return issues


def filter_invalid_doctor_output(
    deck: DeckDetailResponse,
    output: DeckDoctorResponse,
    coach_memory_notes: str | None = None,
) -> list[ValidationIssue]:
    """Remove invalid cuts/swaps in-place and return the removed issues."""
    issues = validate_doctor_output(deck, output, coach_memory_notes)
    if not issues:
        return []
    invalid_cuts = {name for issue in issues if issue.item_type == "cut" for name in issue.names}
    invalid_swaps = {issue.names for issue in issues if issue.item_type == "swap"}
    output.cuts = [cut for cut in output.cuts if cut.card_name not in invalid_cuts]
    output.swaps = [swap for swap in output.swaps if tuple(swap.remove) not in invalid_swaps]
    return issues


def feedback_for_doctor(
    issues: list[ValidationIssue],
    coach_memory_notes: str | None = None,
) -> str:
    """Convert validation issues into concise revision instructions."""
    lines = ["Revise the recommendations to preserve core theme engines and Coach memory."]
    if coach_memory_notes:
        lines.extend(["Persistent Coach memory:", coach_memory_notes.strip()])
    lines.append("Rejected recommendations:")
    for issue in issues[:8]:
        lines.append(f"- {issue.item_type} {', '.join(issue.names)}: {issue.reason}")
    lines.append("Replace rejected swaps with role-compatible upgrades or omit them.")
    return "\n".join(lines)
