"""Tests for compact deck context supplied to MTG Assistant."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services.assistant_deck_context import build_deck_briefing, inspect_deck_cards

pytestmark = pytest.mark.no_db


def _card(
    name: str,
    *,
    cmc: str,
    type_line: str,
    oracle_text: str,
    categories: list[str],
    score: int,
    protected: bool = False,
) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost="{2}{G}",
        cmc=Decimal(cmc),
        type_line=type_line,
        oracle_text=oracle_text,
        color_identity=["B", "G"],
        image_uri=None,
        rarity="rare",
        quantity=1,
        categories=categories,
        added_by="user",
        ai_reasoning=None,
        tags=["food", "token"],
        deck_fit_score=score,
        deck_fit_band="strong" if score >= 70 else "weak",
        deck_fit_reasons=["Food theme", "Draw role", "Commander overlap", "Extra reason"],
        deck_fit_protected=protected,
    )


def _deck() -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_id = uuid4()
    return DeckDetailResponse(
        id=uuid4(),
        name="Camellia Food",
        description="Sacrifice Food for value.",
        bracket=3,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["B", "G"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Camellia, the Seedmiser",
            oracle_text=(
                "Whenever one or more Foods you control are put into a graveyard, "
                "create a Squirrel."
            ),
            color_identity=["B", "G"],
        ),
        partner_card=None,
        owner_email="owner@example.com",
        created_at=now,
        updated_at=now,
        stage_targets={"draw": 10, "ramp": 10},
        archetype_tags=["food_matters", "aristocrats"],
        cards=[
            _card(
                "Food Engine",
                cmc="3",
                type_line="Creature",
                oracle_text="Create a Food token.",
                categories=["food_generation"],
                score=88,
                protected=True,
            ),
            _card(
                "Skullclamp",
                cmc="1",
                type_line="Artifact — Equipment",
                oracle_text="Whenever equipped creature dies, draw two cards.",
                categories=["draw"],
                score=79,
            ),
            _card(
                "Weak Value Card",
                cmc="5",
                type_line="Creature",
                oracle_text="A low-synergy value card.",
                categories=[],
                score=20,
            ),
        ],
    )


def test_build_deck_briefing_contains_complete_compact_manifest() -> None:
    briefing = build_deck_briefing(_deck())
    cards = briefing["cards"]

    assert isinstance(cards, list)
    assert {card["name"] for card in cards} == {
        "Food Engine",
        "Skullclamp",
        "Weak Value Card",
    }
    assert all("oracle_text" in card for card in cards)
    skullclamp = next(card for card in cards if card["name"] == "Skullclamp")
    assert skullclamp["oracle_text"] == "Whenever equipped creature dies, draw two cards."
    assert briefing["commander"]["oracle_text"].startswith("Whenever one or more Foods")
    assert briefing["role_counts"] == {"draw": 1, "food_generation": 1}
    assert briefing["role_targets"] == {"draw": 10, "ramp": 10}
    assert briefing["mana_curve"] == {"1": 1, "3": 1, "5": 1}


def test_build_deck_briefing_bounds_per_card_evidence() -> None:
    briefing = build_deck_briefing(_deck())
    food_engine = next(card for card in briefing["cards"] if card["name"] == "Food Engine")

    assert food_engine["deck_fit_reasons"] == [
        "Food theme",
        "Draw role",
        "Commander overlap",
    ]
    assert food_engine["deck_fit_protected"] is True


def test_inspect_deck_cards_matches_case_insensitively_in_request_order() -> None:
    result = inspect_deck_cards(_deck(), ["skullclamp", "FOOD ENGINE", "Missing Card"])

    assert [card.name for card in result.cards] == ["Skullclamp", "Food Engine"]
    assert result.cards[0].oracle_text == "Whenever equipped creature dies, draw two cards."
    assert result.cards[1].deck_fit_score == 88
    assert result.unknown_names == ["Missing Card"]


def test_inspect_deck_cards_deduplicates_names() -> None:
    result = inspect_deck_cards(_deck(), ["Skullclamp", "skullclamp"])

    assert [card.name for card in result.cards] == ["Skullclamp"]
    assert result.unknown_names == []


def test_inspect_deck_cards_rejects_more_than_eight_names() -> None:
    with pytest.raises(ValueError, match="at most 8"):
        inspect_deck_cards(_deck(), [f"Card {index}" for index in range(9)])
