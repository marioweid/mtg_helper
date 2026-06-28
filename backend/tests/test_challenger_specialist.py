"""Tests for Commander Coach Challenger review guardrails."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from mtg_helper.models.ai import (
    CoachCutCandidate,
    CoachCutReport,
    CoachUpgradeReport,
)
from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services.commander_coach import signal_lanes
from mtg_helper.services.commander_coach.specialists import challenger


def _food_card() -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name="Food Engine",
        mana_cost="{2}{G}",
        cmc=Decimal("3"),
        type_line="Creature",
        oracle_text="When this enters, create a Food token.",
        color_identity=["B", "G"],
        image_uri=None,
        rarity="rare",
        quantity=1,
        categories=[],
        added_by="user",
        ai_reasoning=None,
        qualifying_stages=[],
        tags=["food"],
    )


def _deck(card: DeckCardItem) -> DeckDetailResponse:
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
        commander_color_identity=["B", "G"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Food Commander",
            oracle_text="Whenever you sacrifice a Food, draw a card.",
            color_identity=["B", "G"],
        ),
        partner_card=None,
        owner_email="test@example.com",
        created_at=now,
        updated_at=now,
        archetype_tags=["food_matters"],
        cards=[card],
    )


def test_apply_review_filters_blocked_protected_cut() -> None:
    deck = _deck(_food_card())
    signals = signal_lanes.analyze_signals(deck)
    cuts = CoachCutReport(
        summary="cut food",
        candidates=[
            CoachCutCandidate(
                card_name="Food Engine",
                cut_score=6.0,
                reason="Medium three-drop.",
            )
        ],
    )
    review = challenger.CoachReviewReport(
        summary="block",
        issues=challenger._deterministic_issues(
            deck,
            cuts,
            CoachUpgradeReport(summary="none"),
            signals,
            None,
        ),
        approved=False,
    )

    filtered_cuts, _filtered_upgrades = challenger.apply_review(
        cuts,
        CoachUpgradeReport(summary="none"),
        review,
    )

    assert filtered_cuts.candidates == []
