"""Tests for Commander Coach Theme Guardian validation."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from mtg_helper.models.ai import CardSearchHit, DeckDoctorResponse, DoctorSwap
from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services.commander_coach.validators import validate_doctor_output


def _card(name: str, *, tags: list[str], oracle_text: str) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost="{2}{G}",
        cmc=Decimal("3"),
        type_line="Creature",
        oracle_text=oracle_text,
        color_identity=["G", "B"],
        image_uri=None,
        rarity="rare",
        quantity=1,
        categories=[],
        added_by="user",
        ai_reasoning=None,
        qualifying_stages=[],
        tags=tags,
    )


def _deck(card: DeckCardItem) -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_id = uuid4()
    return DeckDetailResponse(
        id=uuid4(),
        name="Food Deck",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["G", "B"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Food Commander",
            oracle_text="Whenever you sacrifice a Food, draw a card.",
            color_identity=["G", "B"],
        ),
        partner_card=None,
        owner_email="test@example.com",
        created_at=now,
        updated_at=now,
        archetype_tags=["food_matters"],
        cards=[card],
    )


def test_theme_guardian_allows_flexible_card_that_preserves_core_theme() -> None:
    removed = _card(
        "Simple Food Maker",
        tags=["food"],
        oracle_text="When this enters, create a Food token.",
    )
    output = DeckDoctorResponse(
        summary="Upgrade flexible food utility.",
        game_plan="Food value.",
        swaps=[
            DoctorSwap(
                remove=["Simple Food Maker"],
                add=[
                    CardSearchHit(
                        name="Flexible Food Recursion",
                        type_line="Creature",
                        oracle_text=(
                            "When this enters, create a Food token. You may return a card "
                            "from your graveyard to your hand."
                        ),
                        tags=[],
                    )
                ],
                reason="Keeps Food production while adding graveyard utility.",
            )
        ],
    )

    issues = validate_doctor_output(_deck(removed), output)

    assert issues == []
