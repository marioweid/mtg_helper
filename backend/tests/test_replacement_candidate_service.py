"""Characterization tests for deterministic replacement candidate scoring."""

from decimal import Decimal
from typing import cast
from uuid import uuid4

import asyncpg
import pytest

from mtg_helper.models.decks import DeckCardItem
from mtg_helper.services.commander_coach.replacement_candidate_service import _cmc_score

pytestmark = pytest.mark.no_db


def _target_card(cmc: Decimal | None) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name="Target",
        mana_cost="{2}{G}",
        cmc=cmc,
        type_line="Creature",
        oracle_text=None,
        color_identity=["G"],
        image_uri=None,
        rarity="rare",
        quantity=1,
        added_by="user",
        ai_reasoning=None,
    )


def test_replacement_mana_value_scoring_preserves_numeric_equivalence() -> None:
    integer_row = cast(asyncpg.Record, {"cmc": 4})
    decimal_row = cast(asyncpg.Record, {"cmc": Decimal("4.0")})

    integer_score = _cmc_score(_target_card(Decimal("3")), integer_row)
    decimal_score = _cmc_score(
        _target_card(Decimal("3.0")),
        decimal_row,
    )

    assert integer_score == decimal_score == (2.0, ["similar mana value"])
