"""Tests for deterministic Commander Coach synergy scoring."""

from datetime import UTC, datetime
from uuid import uuid4

from mtg_helper.models.ai import CardSearchHit, DeckIdentityReport
from mtg_helper.models.decks import CommanderCardSummary, DeckDetailResponse
from mtg_helper.services.commander_coach import synergy_scoring


def _deck(tags: list[str]) -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_id = uuid4()
    return DeckDetailResponse(
        id=uuid4(),
        name="Synergy Test",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["B", "G"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Camellia, the Seedmiser",
            oracle_text="Food and Squirrel tokens reward sacrifice.",
            color_identity=["B", "G"],
        ),
        partner_card=None,
        owner_email="test@example.com",
        created_at=now,
        updated_at=now,
        archetype_tags=tags,
        cards=[],
    )


def _identity() -> DeckIdentityReport:
    return DeckIdentityReport(
        archetype="Golgari Food Squirrel Aristocrats",
        main_plan="Make Food and Squirrel tokens, sacrifice them, and drain the table.",
        power_target="Bracket 3",
        must_preserve_themes=["food", "squirrel", "sacrifice"],
    )


def test_score_rewards_multi_package_camellia_card() -> None:
    card = CardSearchHit(
        name="Peregrin Took",
        type_line="Legendary Creature — Halfling Citizen",
        oracle_text="If one or more tokens would be created, create Food. Sacrifice Foods: draw.",
        tags=[],
    )

    scored = synergy_scoring.score_card(
        card,
        _deck(["food_matters", "squirrel_tribal", "aristocrats"]),
        _identity(),
        roles=None,
    )

    assert scored.status == "strong"
    assert "food_generation" in scored.packages
    assert scored.score >= 6.0


def test_score_penalizes_generic_ramp_when_not_needed() -> None:
    from mtg_helper.models.ai import CoachRoleBudgetReport, CoachRoleStatus

    card = CardSearchHit(
        name="Rampant Growth",
        type_line="Sorcery",
        oracle_text=(
            "Search your library for a basic land card, "
            "put it onto the battlefield tapped."
        ),
    )
    roles = CoachRoleBudgetReport(
        summary="ramp ok",
        roles=[
            CoachRoleStatus(
                role="ramp",
                count=10,
                target_min=8,
                target_max=12,
                status="ok",
                action="hold",
            )
        ],
        blocked_roles=["ramp"],
    )

    scored = synergy_scoring.score_card(
        card,
        _deck(["food_matters", "squirrel_tribal", "aristocrats"]),
        _identity(),
        roles=roles,
    )

    assert "ramp_not_needed" in scored.penalties
    assert scored.status == "weak"
