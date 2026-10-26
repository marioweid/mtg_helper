"""Behavior tests for deterministic deck-relative card fit scoring."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services.deck_fit_service import score_deck_cards, weak_card_evidence

pytestmark = pytest.mark.no_db

SOURCE_TAG_ID = "10000000-0000-0000-0000-000000000010"


def _card(
    name: str,
    *,
    source_tag_ids: list[str] | None = None,
    categories: list[str] | None = None,
    type_line: str = "Creature",
) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost="{2}{G}",
        cmc=Decimal("3"),
        type_line=type_line,
        oracle_text="Create a Food token.",
        color_identity=["G"],
        image_uri=None,
        rarity="rare",
        quantity=1,
        categories=categories or [],
        added_by="user",
        ai_reasoning=None,
        oracle_tags=[{"id": tag_id, "label": "Source tag"} for tag_id in source_tag_ids or []],
    )


def _deck(cards: list[DeckCardItem]) -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_id = uuid4()
    return DeckDetailResponse(
        id=uuid4(),
        name="Food Test",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["G"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Food Commander",
            oracle_text="Whenever you create a Food token, draw a card.",
            color_identity=["G"],
        ),
        owner_email="test@example.com",
        created_at=now,
        updated_at=now,
        stage_targets={"draw": 2},
        archetype_tags=[SOURCE_TAG_ID],
        cards=cards,
    )


def test_source_synergy_ranks_a_card_above_an_unconnected_card() -> None:
    strong = _card("Strong Engine", source_tag_ids=[SOURCE_TAG_ID])
    weak = _card("Unconnected Body")
    deck = _deck([strong, weak])

    score_deck_cards(deck, {strong.card_id: 0.35})

    assert strong.deck_fit_score is not None
    assert weak.deck_fit_score is not None
    assert strong.deck_fit_score > weak.deck_fit_score
    assert strong.deck_fit_band == "strong"
    assert weak.deck_fit_band == "weak"


def test_local_fallback_is_labeled_when_source_statistics_are_missing() -> None:
    card = _card("Local Food Card", source_tag_ids=[SOURCE_TAG_ID])
    deck = _deck([card])

    score_deck_cards(deck, {})

    assert card.deck_fit_score is not None
    assert any("Local" in reason for reason in card.deck_fit_reasons)


def test_underfilled_roles_remain_protected_without_pet_card_protection() -> None:
    role_card = _card("Needed Draw", categories=["draw"])
    pet_card = _card("Favorite Card")
    ordinary = _card("Ordinary Weak Card")
    land = _card("Forest", type_line="Basic Land — Forest")
    deck = _deck([role_card, pet_card, ordinary, land])

    score_deck_cards(deck, {})
    weak = weak_card_evidence(deck, limit=8)

    assert [item.name for item in weak] == ["Favorite Card", "Ordinary Weak Card"]
    assert role_card.deck_fit_protected
    assert not pet_card.deck_fit_protected
    assert land.deck_fit_protected


def test_weak_card_order_is_deterministic() -> None:
    first = _card("Alpha")
    second = _card("Beta")
    deck = _deck([second, first])

    score_deck_cards(deck, {})

    assert [item.name for item in weak_card_evidence(deck, limit=8)] == ["Alpha", "Beta"]


def test_legacy_combo_tag_does_not_protect_a_card_from_ordinary_cuts() -> None:
    combo = _card("Combo Piece")
    ordinary = _card("Ordinary Card")
    deck = _deck([combo, ordinary])

    score_deck_cards(deck, {})

    assert not combo.deck_fit_protected
    assert [item.name for item in weak_card_evidence(deck)] == ["Combo Piece", "Ordinary Card"]


def test_commander_is_never_an_ordinary_cut_candidate() -> None:
    commander = _card("Food Commander", source_tag_ids=[SOURCE_TAG_ID])
    ordinary = _card("Ordinary Card")
    deck = _deck([commander, ordinary])
    deck.commander_id = commander.card_id

    score_deck_cards(deck, {})

    assert commander.deck_fit_protected
    assert [item.name for item in weak_card_evidence(deck)] == ["Ordinary Card"]


def test_unknown_source_ids_do_not_affect_deck_cards() -> None:
    card = _card("Known Card", source_tag_ids=[SOURCE_TAG_ID])
    deck = _deck([card])
    scores: dict[UUID, float] = {uuid4(): 1.0}

    score_deck_cards(deck, scores)

    assert card.deck_fit_score is not None
    assert card.deck_fit_score < 100
