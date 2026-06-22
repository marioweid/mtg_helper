"""Tests for the Commander Coach specialist pipeline."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from mtg_helper.models.ai import (
    CardSearchHit,
    CoachCurveReport,
    CoachCutCandidate,
    CoachCutReport,
    CoachManaReport,
    CoachUpgradeCandidate,
    CoachUpgradeReport,
    CommanderCoachRequest,
    DeckIdentityReport,
)
from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services.commander_coach import orchestrator
from mtg_helper.services.commander_coach.specialists import cuts, identity, upgrades

pytestmark = pytest.mark.asyncio


def _card(name: str, *, tags: list[str] | None = None) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name=name,
        mana_cost="{2}{G}",
        cmc=Decimal("3"),
        type_line="Creature",
        oracle_text="A medium value creature.",
        color_identity=["B", "G"],
        image_uri=None,
        rarity="rare",
        quantity=1,
        categories=[],
        added_by="user",
        ai_reasoning=None,
        qualifying_stages=[],
        tags=tags or [],
    )


def _deck() -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_id = uuid4()
    return DeckDetailResponse(
        id=uuid4(),
        name="Camellia Test",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["B", "G"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Camellia, the Seedmiser",
            mana_cost="{1}{B}{G}",
            oracle_text="Food and Squirrel tokens reward sacrifice.",
            color_identity=["B", "G"],
        ),
        partner_card=None,
        owner_email="test@example.com",
        created_at=now,
        updated_at=now,
        archetype_tags=["food_matters", "squirrel_tribal", "aristocrats"],
        cards=[_card("Medium Value Card"), _card("Food Engine", tags=["food"])],
    )


async def test_run_coach_uses_specialist_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_identity(*_args: object, **_kwargs: object) -> DeckIdentityReport:
        return DeckIdentityReport(
            archetype="Golgari Food Squirrel Aristocrats",
            main_plan="Make Food and Squirrels, sacrifice them, and drain the table.",
            secondary_plan="Go-wide combat.",
            power_target="Bracket 3",
            deck_tension=["too many medium 3-drops"],
            must_preserve_themes=["food", "squirrel", "sacrifice"],
        )

    async def fake_cuts(*_args: object, **_kwargs: object) -> CoachCutReport:
        return CoachCutReport(
            summary="Cut weak value cards.",
            candidates=[
                CoachCutCandidate(
                    card_name="Medium Value Card",
                    cut_score=8.0,
                    reason="Three-mana value card with no Food, Squirrel, or sacrifice text.",
                    tags=["low_synergy"],
                )
            ],
        )

    async def fake_upgrades(*_args: object, **_kwargs: object) -> CoachUpgradeReport:
        return CoachUpgradeReport(
            summary="Add cheap engines.",
            candidates=[
                CoachUpgradeCandidate(
                    card=CardSearchHit(name="Experimental Confectioner", tags=["food"]),
                    reason="Repeatable Food and token engine for the deck identity.",
                    role="food_engine",
                    replaces=["Medium Value Card"],
                )
            ],
            tool_call_count=1,
        )

    monkeypatch.setattr(identity, "identify_deck", fake_identity)
    monkeypatch.setattr(cuts, "recommend_cuts", fake_cuts)
    monkeypatch.setattr(upgrades, "recommend_upgrades", fake_upgrades)
    monkeypatch.setattr(
        orchestrator.pipeline,
        "analyze_mana",
        lambda _deck: CoachManaReport(
            summary="36 lands; land count matches the recommendation.",
            total_lands=36,
            recommended_lands=36,
            land_delta=0,
            ramp_count=8,
        ),
    )
    monkeypatch.setattr(
        orchestrator.pipeline,
        "analyze_curve",
        lambda _deck: CoachCurveReport(summary="Curve is playable.", curve={"3": 10}),
    )

    result = await orchestrator.run_coach(None, _deck(), CommanderCoachRequest())

    assert result.mode == "doctor"
    assert result.doctor is not None
    assert result.doctor.game_plan.startswith("Make Food and Squirrels")
    assert result.doctor.cuts[0].card_name == "Medium Value Card"
    assert result.doctor.adds[0].card.name == "Experimental Confectioner"
    assert result.doctor.tool_call_count == 1
