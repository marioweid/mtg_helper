"""Behavior tests for deterministic deck-relative card fit scoring."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services.deck_fit_service import score_deck_cards, weak_card_evidence


def _card(
    name: str,
    *,
    tags: list[str] | None = None,
    stages: list[str] | None = None,
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
        categories=[],
        added_by="user",
        ai_reasoning=None,
        qualifying_stages=stages or [],
        tags=tags or [],
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
        archetype_tags=["food_matters"],
        cards=cards,
    )


def test_source_synergy_ranks_a_card_above_an_unconnected_card() -> None:
    strong = _card("Strong Engine", tags=["food_matters"])
    weak = _card("Unconnected Body", tags=["vanilla"])
    deck = _deck([strong, weak])

    score_deck_cards(deck, {strong.card_id: 0.35})

    assert strong.deck_fit_score is not None
    assert weak.deck_fit_score is not None
    assert strong.deck_fit_score > weak.deck_fit_score
    assert strong.deck_fit_band == "strong"
    assert weak.deck_fit_band == "weak"


def test_local_fallback_is_labeled_when_source_statistics_are_missing() -> None:
    card = _card("Local Food Card", tags=["food_matters"])
    deck = _deck([card])

    score_deck_cards(deck, {})

    assert card.deck_fit_score is not None
    assert any("Local" in reason for reason in card.deck_fit_reasons)


def test_underfilled_role_and_pet_cards_are_protected_from_weak_list() -> None:
    role_card = _card("Needed Draw", tags=["draw"], stages=["draw"])
    pet_card = _card("Favorite Card", tags=["vanilla"])
    ordinary = _card("Ordinary Weak Card", tags=["vanilla"])
    land = _card("Forest", type_line="Basic Land — Forest")
    deck = _deck([role_card, pet_card, ordinary, land])

    score_deck_cards(deck, {}, protected_names={"Favorite Card"})
    weak = weak_card_evidence(deck, limit=8)

    assert [item.name for item in weak] == ["Ordinary Weak Card"]
    assert role_card.deck_fit_protected
    assert pet_card.deck_fit_protected
    assert land.deck_fit_protected


def test_weak_card_order_is_deterministic() -> None:
    first = _card("Alpha", tags=["vanilla"])
    second = _card("Beta", tags=["vanilla"])
    deck = _deck([second, first])

    score_deck_cards(deck, {})

    assert [item.name for item in weak_card_evidence(deck, limit=8)] == ["Alpha", "Beta"]


def test_known_combo_tags_protect_a_card_from_ordinary_cuts() -> None:
    combo = _card("Combo Piece", tags=["combo_piece"])
    ordinary = _card("Ordinary Card", tags=["vanilla"])
    deck = _deck([combo, ordinary])

    score_deck_cards(deck, {})

    assert combo.deck_fit_protected
    assert [item.name for item in weak_card_evidence(deck)] == ["Ordinary Card"]


def test_commander_is_never_an_ordinary_cut_candidate() -> None:
    commander = _card("Food Commander", tags=["food_matters"])
    ordinary = _card("Ordinary Card", tags=["vanilla"])
    deck = _deck([commander, ordinary])
    deck.commander_id = commander.card_id

    score_deck_cards(deck, {})

    assert commander.deck_fit_protected
    assert [item.name for item in weak_card_evidence(deck)] == ["Ordinary Card"]


def test_unknown_source_ids_do_not_affect_deck_cards() -> None:
    card = _card("Known Card", tags=["food_matters"])
    deck = _deck([card])
    scores: dict[UUID, float] = {uuid4(): 1.0}

    score_deck_cards(deck, scores)

    assert card.deck_fit_score is not None
    assert card.deck_fit_score < 100
