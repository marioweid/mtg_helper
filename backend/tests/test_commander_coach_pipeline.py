"""Tests for the Commander Coach specialist pipeline."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import uuid4

import asyncpg
import pytest
from pydantic_ai.models.test import TestModel

from mtg_helper.models.ai import CommanderCoachRequest
from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services import mtg_assistant
from mtg_helper.services.commander_coach import orchestrator, signal_lanes
from mtg_helper.services.mtg_assistant import (
    AssistantAnswer,
    AssistantCut,
    AssistantDeps,
    AssistantRecommendation,
    _to_response,
)

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


async def test_run_coach_uses_one_tool_selecting_assistant() -> None:
    model = TestModel(
        call_tools=["analyze_deck"],
        custom_output_args={
            "mode": "doctor",
            "reply": "The deck has one weak generic value card.",
            "recommendations": [],
            "cuts": [
                {
                    "card_name": "Medium Value Card",
                    "reason": "It does not support the selected themes.",
                }
            ],
        },
    )
    with mtg_assistant.get_agent().override(model=model):
        result = await orchestrator.run_coach(None, _deck(), CommanderCoachRequest())

    assert result.mode == "doctor"
    assert result.doctor is not None
    assert result.doctor.cuts[0].card_name == "Medium Value Card"
    assert result.doctor.tool_call_count == 1
    tool_names = {tool.name for tool in model.last_model_request_parameters.function_tools}
    assert "search_cards" in tool_names
    assert "find_theme_cards" not in tool_names


async def test_signal_lanes_detect_core_commander_packages() -> None:
    report = signal_lanes.analyze_signals(_deck())

    assert "food_generation" in report.core_lanes
    assert "squirrel_generation" in signal_lanes.lane_names(report)
    assert "Food Engine" in report.protected_cards


def test_assistant_drops_ungrounded_cards_and_unknown_cuts() -> None:
    output = AssistantAnswer(
        mode="doctor",
        reply="Unverified suggestions must not become actionable cards.",
        recommendations=[
            AssistantRecommendation(
                scryfall_id=uuid4(),
                reason="The model named a card that no retrieval tool returned.",
            )
        ],
        cuts=[AssistantCut(card_name="Not In Deck", reason="Unknown card")],
    )

    deps = AssistantDeps(pool=cast(asyncpg.Pool, None), deck=_deck())
    result = _to_response(output, deps)

    assert result.mode == "chat"
    assert result.doctor is None
