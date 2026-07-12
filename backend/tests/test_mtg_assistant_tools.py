"""Behavior tests for deterministic MTG Assistant tools."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services.mtg_assistant_tools import (
    _structural_issues,
    _theme_match_score,
    check_bracket,
)


def _card(name: str, *, quantity: int = 1, game_changer: bool = False) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost="{2}{G}",
        cmc=Decimal("3"),
        type_line="Creature",
        oracle_text="Create a token.",
        color_identity=["G"],
        image_uri=None,
        rarity="rare",
        quantity=quantity,
        categories=[],
        added_by="user",
        ai_reasoning=None,
        game_changer=game_changer,
    )


def _deck(cards: list[DeckCardItem], *, bracket: int = 3) -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_id = uuid4()
    return DeckDetailResponse(
        id=uuid4(),
        name="Assistant Test",
        description=None,
        bracket=bracket,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["G"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Test Commander",
            color_identity=["G"],
        ),
        owner_email="test@example.com",
        created_at=now,
        updated_at=now,
        cards=cards,
    )


class _ThemeRow(dict[str, object]):
    def __getitem__(self, key: str) -> object:
        return super().__getitem__(key)


def test_theme_match_uses_aliases_and_description() -> None:
    row = _ThemeRow(
        tag="x_spells",
        label="X Spells",
        description="Variable-cost spells and scalable mana payoffs.",
        aliases=["big x spells", "variable mana"],
        source="group",
    )

    assert _theme_match_score("big x spells", row) == 1.0
    assert _theme_match_score("scalable mana", row) > 0.0


def test_structural_legality_rejects_wrong_size_and_duplicates() -> None:
    deck = _deck([_card("Repeated Card", quantity=2)])

    issues = _structural_issues(deck)

    assert {issue.code for issue in issues} == {"deck_size", "singleton"}


@pytest.mark.parametrize("bracket", [1, 2])
def test_bracket_check_is_deterministic_for_game_changers(bracket: int) -> None:
    cards = [_card("Power Card", game_changer=True)]

    report = check_bracket(_deck(cards, bracket=bracket))

    assert not report.acceptable
    assert report.ruleset == "project-commander-brackets-v1"
    assert any("Game Changers" in warning for warning in report.warnings)
