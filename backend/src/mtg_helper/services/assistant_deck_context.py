"""Compact, deterministic deck context for MTG Assistant."""

from collections import Counter
from typing import Literal

from pydantic import BaseModel

from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse

_MAX_INSPECTION_NAMES = 8


class InspectedDeckCard(BaseModel):
    """Exact current-deck card text and deck-relative evidence."""

    name: str
    mana_cost: str | None
    mana_value: float | None
    type_line: str | None
    oracle_text: str | None
    quantity: int
    categories: list[str]
    tags: list[str]
    deck_fit_score: int | None
    deck_fit_band: Literal["strong", "solid", "weak"] | None
    deck_fit_reasons: list[str]
    deck_fit_protected: bool


class DeckCardInspection(BaseModel):
    """Matched current-deck cards and names that were not found."""

    cards: list[InspectedDeckCard]
    unknown_names: list[str]


def build_deck_briefing(deck: DeckDetailResponse) -> dict[str, object]:
    """Build complete bounded deck context without repeating all Oracle text."""
    cards = sorted(deck.cards, key=lambda card: (card.cmc or 0, card.name))
    return {
        "name": deck.name,
        "description": deck.description,
        "bracket": deck.bracket,
        "colors": deck.commander_color_identity,
        "themes": deck.archetype_tags,
        "commander": _commander_row(deck.commander_card),
        "partner": _commander_row(deck.partner_card),
        "card_count": sum(card.quantity for card in cards),
        "role_counts": _role_counts(cards),
        "role_targets": deck.stage_targets,
        "type_counts": _type_counts(cards),
        "mana_curve": _mana_curve(cards),
        "cards": [_manifest_row(card) for card in cards],
    }


def inspect_deck_cards(deck: DeckDetailResponse, names: list[str]) -> DeckCardInspection:
    """Return exact text for up to eight named cards in the current deck."""
    if len(names) > _MAX_INSPECTION_NAMES:
        raise ValueError(f"inspect_deck_cards accepts at most {_MAX_INSPECTION_NAMES} names")
    by_name = {card.name.casefold(): card for card in deck.cards}
    cards: list[InspectedDeckCard] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for requested_name in names:
        normalized = requested_name.strip().casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        card = by_name.get(normalized)
        if card is None:
            unknown.append(requested_name)
        else:
            cards.append(_inspection_row(card))
    return DeckCardInspection(cards=cards, unknown_names=unknown)


def _commander_row(card: CommanderCardSummary | None) -> dict[str, object] | None:
    if card is None:
        return None
    return {
        "name": card.name,
        "mana_cost": card.mana_cost,
        "type_line": card.type_line,
        "oracle_text": card.oracle_text,
    }


def _manifest_row(card: DeckCardItem) -> dict[str, object]:
    return {
        "name": card.name,
        "quantity": card.quantity,
        "mana_value": float(card.cmc) if card.cmc is not None else None,
        "type_line": card.type_line,
        "categories": card.categories[:8],
        "tags": card.tags[:8],
        "deck_fit_score": card.deck_fit_score,
        "deck_fit_band": card.deck_fit_band,
        "deck_fit_reasons": card.deck_fit_reasons[:3],
        "deck_fit_protected": card.deck_fit_protected,
    }


def _inspection_row(card: DeckCardItem) -> InspectedDeckCard:
    return InspectedDeckCard(
        name=card.name,
        mana_cost=card.mana_cost,
        mana_value=float(card.cmc) if card.cmc is not None else None,
        type_line=card.type_line,
        oracle_text=card.oracle_text,
        quantity=card.quantity,
        categories=card.categories[:8],
        tags=card.tags[:8],
        deck_fit_score=card.deck_fit_score,
        deck_fit_band=card.deck_fit_band,
        deck_fit_reasons=card.deck_fit_reasons[:3],
        deck_fit_protected=card.deck_fit_protected,
    )


def _role_counts(cards: list[DeckCardItem]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for card in cards:
        for category in card.categories:
            counts[category] += card.quantity
    return dict(sorted(counts.items()))


def _type_counts(cards: list[DeckCardItem]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for card in cards:
        type_line = card.type_line or "Unknown"
        card_type = "Land" if "Land" in type_line else type_line.split(" — ", maxsplit=1)[0]
        counts[card_type] += card.quantity
    return dict(sorted(counts.items()))


def _mana_curve(cards: list[DeckCardItem]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for card in cards:
        if "Land" in (card.type_line or ""):
            continue
        mana_value = int(card.cmc or 0)
        counts["7+" if mana_value >= 7 else str(mana_value)] += card.quantity
    return dict(sorted(counts.items()))
