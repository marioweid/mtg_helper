"""Deterministic, deck-relative card fit scoring."""

import re
from collections.abc import Mapping, Set
from typing import Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field

from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.services.theme_service import score_themes

_DEFAULT_TARGETS = {"ramp": 12, "draw": 12, "interaction": 12, "lands": 38}
_SOURCE_SCORE_CEILING = 0.35
_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_IGNORED_WORDS = {
    "card",
    "create",
    "creature",
    "target",
    "token",
    "whenever",
    "with",
    "your",
}


class WeakCardEvidence(BaseModel):
    """One eligible cut candidate backed by deterministic deck-fit evidence."""

    name: str
    score: int = Field(ge=0, le=100)
    band: Literal["strong", "solid", "weak"]
    reasons: list[str] = Field(default_factory=list)


async def enrich_deck_fit(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    *,
    protected_names: Set[str] | None = None,
) -> None:
    """Attach current source-backed fit evidence to every card in a loaded deck."""
    scores = await score_themes(pool, deck.archetype_tags, deck.commander_color_identity)
    score_deck_cards(deck, scores, protected_names=protected_names)


def score_deck_cards(
    deck: DeckDetailResponse,
    source_scores: Mapping[UUID, float],
    *,
    protected_names: Set[str] | None = None,
) -> None:
    """Compute normalized card fit from source synergy and current deck context."""
    role_counts = _role_counts(deck.cards)
    role_targets = _DEFAULT_TARGETS | deck.stage_targets
    commander_words = _commander_words(deck)
    commander_ids = {card_id for card_id in (deck.commander_id, deck.partner_id) if card_id}
    deck_tags = {_normalize_tag(tag) for tag in deck.archetype_tags}
    protected = {name.casefold() for name in (protected_names or set())}

    for card in deck.cards:
        reasons: list[str] = []
        score = _base_score(card, source_scores, reasons)
        card_tags = {_normalize_tag(tag) for tag in card.tags}
        if deck_tags & card_tags:
            score += 15
            reasons.append("Matches a selected deck theme")
        if _word_overlap(commander_words, _card_words(card)):
            score += 10
            reasons.append("Overlaps the commander's game text")

        needed_roles = _needed_roles(card, role_counts, role_targets)
        if needed_roles:
            score += 10
            reasons.append(f"Fills low role: {', '.join(needed_roles[:2])}")

        protections = _protection_reasons(card, protected, needed_roles, commander_ids)
        card.deck_fit_score = min(100, round(score))
        card.deck_fit_band = _band(card.deck_fit_score)
        card.deck_fit_reasons = reasons[:3]
        card.deck_fit_protected = bool(protections)
        if protections:
            card.deck_fit_reasons = (protections + card.deck_fit_reasons)[:3]


def weak_card_evidence(deck: DeckDetailResponse, limit: int = 8) -> list[WeakCardEvidence]:
    """Return the lowest-fit cards that are eligible for ordinary replacement advice."""
    rows = [
        WeakCardEvidence(
            name=card.name,
            score=card.deck_fit_score,
            band=card.deck_fit_band or "weak",
            reasons=list(card.deck_fit_reasons),
        )
        for card in deck.cards
        if card.deck_fit_score is not None and not card.deck_fit_protected
    ]
    rows.sort(key=lambda item: (item.score, item.name.casefold()))
    return rows[: max(1, limit)]


def _base_score(
    card: DeckCardItem,
    source_scores: Mapping[UUID, float],
    reasons: list[str],
) -> float:
    raw_score = source_scores.get(card.card_id)
    if raw_score is None:
        reasons.append("Local deck evidence only")
        return 25.0
    normalized = min(1.0, max(0.0, raw_score) / _SOURCE_SCORE_CEILING)
    reasons.append("Supported by Moxfield/Archidekt theme data")
    return 30.0 + normalized * 50.0


def _band(score: int) -> str:
    if score >= 75:
        return "strong"
    if score >= 45:
        return "solid"
    return "weak"


def _role_counts(cards: list[DeckCardItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for card in cards:
        for role in card.categories or card.qualifying_stages:
            counts[role] = counts.get(role, 0) + max(1, card.quantity)
    return counts


def _needed_roles(
    card: DeckCardItem,
    counts: Mapping[str, int],
    targets: Mapping[str, int],
) -> list[str]:
    roles = card.categories or card.qualifying_stages
    return sorted(
        {role for role in roles if role in targets and counts.get(role, 0) < targets[role]}
    )


def _protection_reasons(
    card: DeckCardItem,
    protected_names: set[str],
    needed_roles: list[str],
    commander_ids: set[UUID],
) -> list[str]:
    reasons: list[str] = []
    if card.card_id in commander_ids:
        reasons.append("Protected as a commander")
    if "Land" in (card.type_line or ""):
        reasons.append("Protected from ordinary cuts: land")
    if card.name.casefold() in protected_names:
        reasons.append("Protected by your pet-card preference")
    normalized_tags = {_normalize_tag(tag) for tag in [*card.tags, *card.mtgjson_tags]}
    if normalized_tags & {"combo", "combo_piece", "combo_pieces"}:
        reasons.append("Protected as a known combo piece")
    if needed_roles:
        reasons.append("Protected because it fills an under-target role")
    return reasons


def _commander_words(deck: DeckDetailResponse) -> set[str]:
    cards = [card for card in (deck.commander_card, deck.partner_card) if card is not None]
    return {
        word
        for card in cards
        for word in _words(f"{card.name} {card.oracle_text or ''}")
        if word not in _IGNORED_WORDS
    }


def _card_words(card: DeckCardItem) -> set[str]:
    return _words(f"{card.name} {card.type_line or ''} {card.oracle_text or ''}")


def _words(value: str) -> set[str]:
    return {word for word in _WORD_PATTERN.findall(value.casefold()) if len(word) >= 4}


def _word_overlap(left: set[str], right: set[str]) -> bool:
    return bool(left & right)


def _normalize_tag(value: str) -> str:
    return value.split(":", maxsplit=1)[-1].replace("-", "_").casefold()
