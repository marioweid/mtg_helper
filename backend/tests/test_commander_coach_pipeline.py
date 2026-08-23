"""Tests for the Commander Coach specialist pipeline."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg
import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelRequest, ModelResponse
from pydantic_ai.models.test import TestModel
from starlette.requests import Request

from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.ai import (
    CardSearchHit,
    ColorStatus,
    CommanderCoachRequest,
    CommanderCoachResponse,
    ManaBaseReport,
    ReplacementOption,
    TargetedReplacementResponse,
)
from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.routers import ai
from mtg_helper.services import mtg_assistant
from mtg_helper.services.commander_coach import orchestrator, signal_lanes
from mtg_helper.services.mtg_assistant import (
    AssistantAnswer,
    AssistantCut,
    AssistantDeps,
    AssistantRecommendation,
    _bounded_history,
    _prompt_payload,
    _to_response,
)
from mtg_helper.services.mtg_assistant_tools import AssistantManaBaseAnalysis, ManaBaseSwap
from mtg_helper.services.mtg_card_search import (
    CardEvidenceSource,
    CardSearchCandidate,
    CardSearchResult,
)

pytestmark = pytest.mark.no_db


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


def test_coach_request_accepts_role_aware_history() -> None:
    request = CommanderCoachRequest(
        message="What should I add for draw?",
        history=[
            {"role": "user", "content": "Keep this Food-first."},
            {"role": "assistant", "content": "I will prioritize Food engines."},
        ],
    )

    assert [turn.role for turn in request.history] == ["user", "assistant"]
    assert request.message == "What should I add for draw?"


@pytest.mark.parametrize(
    "payload",
    [
        {"message": ""},
        {"message": "Question", "history": [{"role": "user", "content": ""}]},
        {"message": "Question", "history": [{"role": "system", "content": "No"}]},
        {
            "message": "Question",
            "history": [{"role": "user", "content": str(index)} for index in range(13)],
        },
    ],
    ids=["empty-message", "empty-history", "unknown-role", "too-many-turns"],
)
def test_coach_request_rejects_invalid_history(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CommanderCoachRequest.model_validate(payload)


def test_coach_response_defaults_to_no_recommendations() -> None:
    response = CommanderCoachResponse(mode="chat", reply="Answer")

    assert response.recommendations == []


def test_bounded_history_keeps_newest_complete_pairs() -> None:
    request = CommanderCoachRequest(
        message="Latest",
        history=[
            {"role": "user", "content": f"user-{index}-" + "x" * 1990}
            if index % 2 == 0
            else {"role": "assistant", "content": f"assistant-{index}-" + "x" * 1990}
            for index in range(12)
        ],
    )

    history = _bounded_history(request)

    assert len(history) % 2 == 0
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[1], ModelResponse)
    assert "user-6" in str(history[0])
    assert "assistant-11" in str(history[-1])


def test_bounded_history_handles_irregular_roles_without_dropping_newest_user() -> None:
    request = CommanderCoachRequest(
        message="Latest",
        history=[
            {"role": "user", "content": "old-" + "x" * 3996},
            {"role": "user", "content": "middle-" + "x" * 3993},
            {"role": "assistant", "content": "answer-" + "x" * 3993},
            {"role": "user", "content": "newest-user"},
        ],
    )

    history = _bounded_history(request)

    assert len(history) == 3
    assert "middle" in str(history[0])
    assert "newest-user" in str(history[-1])


def test_prompt_payload_contains_complete_deck_and_preferences() -> None:
    deck = _deck()
    deck.cards[0].deck_fit_score = 25
    deck.stage_targets = {"draw": 10}
    request = CommanderCoachRequest(
        message="What should I add for draw?",
        coach_memory_notes="Keep this Food-first.",
    )

    payload = _prompt_payload(deck, request)

    assert payload["current_request"] == request.message
    assert payload["preferences"] == "Keep this Food-first."
    assert payload["deck"]["role_targets"] == {"draw": 10}
    assert {card["name"] for card in payload["deck"]["cards"]} == {
        "Medium Value Card",
        "Food Engine",
    }
    medium_card = next(
        card for card in payload["deck"]["cards"] if card["name"] == "Medium Value Card"
    )
    assert medium_card["deck_fit_score"] == 25


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
        result = await orchestrator.run_coach(
            cast(asyncpg.Pool, None), _deck(), CommanderCoachRequest()
        )

    assert result.mode == "doctor"
    assert result.doctor is not None
    assert result.replacement is None
    assert result.doctor.cuts[0].card_name == "Medium Value Card"
    assert result.doctor.tool_call_count == 1
    assert model.last_model_request_parameters is not None
    tool_names = {tool.name for tool in model.last_model_request_parameters.function_tools}
    assert "search_cards" in tool_names
    assert "find_theme_cards" not in tool_names


async def test_assistant_can_inspect_exact_current_deck_cards() -> None:
    model = TestModel(
        call_tools=["inspect_deck_cards"],
        custom_output_args={
            "mode": "chat",
            "reply": "Food Engine creates Food.",
        },
    )
    with mtg_assistant.get_agent().override(model=model):
        result = await orchestrator.run_coach(
            cast(asyncpg.Pool, None),
            _deck(),
            CommanderCoachRequest(message="What does Food Engine do?"),
        )

    assert result.reply == "Food Engine creates Food."
    assert model.last_model_request_parameters is not None
    tool_names = {tool.name for tool in model.last_model_request_parameters.function_tools}
    assert "inspect_deck_cards" in tool_names


async def test_landbase_request_uses_grounded_mana_analysis_tool() -> None:
    candidate_id = uuid4()
    analysis = AssistantManaBaseAnalysis(
        report=ManaBaseReport(
            total_lands=35,
            total_colored_pips=30,
            colors=[ColorStatus(color="G", pip_count=30, source_count=12, target=16, deficit=4)],
            recommended_lands=36,
            land_delta=1,
        ),
        recommended_land_range=(35, 37),
        tapped_land_count=0,
        utility_land_count=0,
        swaps=[
            ManaBaseSwap(
                remove_card="Medium Value Card",
                add=CardSearchHit(
                    scryfall_id=candidate_id, name="Llanowar Wastes", type_line="Land"
                ),
                reason="Adds a needed green source.",
            )
        ],
    )
    model = TestModel(
        call_tools=["analyze_mana_base"],
        custom_output_args={
            "mode": "doctor",
            "reply": "Improve the green source count.",
            "recommendations": [
                {
                    "scryfall_id": candidate_id,
                    "reason": "Adds a needed green source.",
                    "replaces": ["Medium Value Card"],
                }
            ],
            "cuts": [],
        },
    )
    with (
        patch.object(mtg_assistant, "analyze_mana_base_service", AsyncMock(return_value=analysis)),
        mtg_assistant.get_agent().override(model=model),
    ):
        result = await orchestrator.run_coach(
            cast(asyncpg.Pool, None),
            _deck(),
            CommanderCoachRequest(message="Can we improve my landbase?"),
        )

    assert result.doctor is not None
    assert result.doctor.tool_call_count == 1
    assert result.doctor.adds[0].card.name == "Llanowar Wastes"


async def test_run_coach_returns_grounded_replacement() -> None:
    candidate_id = uuid4()
    search_result = CardSearchResult(
        evidence_source=CardEvidenceSource.GLOBAL_SEARCH,
        candidates=[
            CardSearchCandidate(
                card=CardSearchHit(scryfall_id=candidate_id, name="Squirrel Sovereign"),
                evidence_source=CardEvidenceSource.GLOBAL_SEARCH,
                role_matches=["anthem"],
            )
        ],
    )
    model = TestModel(
        call_tools=["search_cards"],
        custom_output_args={
            "mode": "replacement",
            "reply": "Replace the generic creature with a squirrel anthem.",
            "target_card_name": "Medium Value Card",
            "recommendations": [
                {
                    "scryfall_id": candidate_id,
                    "reason": "It supports the deck's squirrel plan.",
                    "role_match": "theme_upgrade",
                    "tradeoff": "It is narrower outside the tribal plan.",
                }
            ],
        },
    )
    with (
        patch.object(mtg_assistant, "search_cards_service", AsyncMock(return_value=search_result)),
        mtg_assistant.get_agent().override(model=model),
    ):
        result = await orchestrator.run_coach(
            cast(asyncpg.Pool, None),
            _deck(),
            CommanderCoachRequest(message="Replace Medium Value Card."),
        )

    assert result.mode == "replacement"
    assert result.doctor is None
    assert result.replacement is not None
    assert result.replacement.target_card_name == "Medium Value Card"
    assert result.replacement.best_pick is not None
    assert result.replacement.best_pick.name == "Squirrel Sovereign"
    assert result.replacement.options[0].role_match == "theme_upgrade"
    assert result.replacement.tool_call_count == 1


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
    assert result.replacement is None


def test_assistant_chat_returns_only_grounded_recommendations() -> None:
    candidate_id = uuid4()
    deps = AssistantDeps(pool=cast(asyncpg.Pool, None), deck=_deck())
    deps.retrieved[candidate_id] = CardSearchCandidate(
        card=CardSearchHit(scryfall_id=candidate_id, name="Grounded Card"),
        evidence_source=CardEvidenceSource.GLOBAL_SEARCH,
    )
    output = AssistantAnswer(
        mode="chat",
        reply="Here is a conversational answer.",
        target_card_name="Medium Value Card",
        recommendations=[
            AssistantRecommendation(scryfall_id=candidate_id, reason="Grounded recommendation."),
            AssistantRecommendation(scryfall_id=uuid4(), reason="Unknown recommendation."),
        ],
        cuts=[AssistantCut(card_name="Medium Value Card", reason="Not requested.")],
    )

    result = _to_response(output, deps)

    assert result.mode == "chat"
    assert [option.card.name for option in result.recommendations] == ["Grounded Card"]
    assert result.doctor is None
    assert result.replacement is None


@pytest.mark.parametrize(
    "output",
    [
        AssistantAnswer(
            mode="replacement",
            reply="That target is not in this deck.",
            target_card_name="Unknown Card",
        ),
        AssistantAnswer(
            mode="replacement",
            reply="The suggested card was not returned by a tool.",
            target_card_name="Medium Value Card",
            recommendations=[
                AssistantRecommendation(
                    scryfall_id=uuid4(),
                    reason="Ungrounded recommendation.",
                    role_match="same_role",
                )
            ],
        ),
    ],
    ids=["invalid-target", "ungrounded-recommendation"],
)
def test_assistant_replacement_rejects_non_actionable_output(output: AssistantAnswer) -> None:
    result = _to_response(
        output,
        AssistantDeps(pool=cast(asyncpg.Pool, None), deck=_deck()),
    )

    assert result.mode == "chat"
    assert result.doctor is None
    assert result.replacement is None


def test_assistant_replacement_matches_target_case_insensitively() -> None:
    deps = AssistantDeps(pool=cast(asyncpg.Pool, None), deck=_deck())
    output = AssistantAnswer(
        mode="replacement",
        reply="Keeping the card is reasonable.",
        target_card_name="  medium value card  ",
        keep_reason="It remains useful at this mana value.",
    )

    result = _to_response(output, deps)

    assert result.mode == "replacement"
    assert result.doctor is None
    assert result.replacement is not None
    assert result.replacement.target_card_name == "Medium Value Card"
    assert result.replacement.keep_reason == "It remains useful at this mana value."


def test_assistant_replacement_allows_grounded_keep_only_advice() -> None:
    output = AssistantAnswer(
        mode="replacement",
        reply="No available option is a clear upgrade.",
        target_card_name="Medium Value Card",
        keep_reason="Keep it until a candidate preserves both its role and curve slot.",
    )

    result = _to_response(
        output,
        AssistantDeps(pool=cast(asyncpg.Pool, None), deck=_deck()),
    )

    assert result.mode == "replacement"
    assert result.doctor is None
    assert result.replacement is not None
    assert result.replacement.best_pick is None
    assert result.replacement.options == []
    assert result.replacement.keep_reason == (
        "Keep it until a candidate preserves both its role and curve slot."
    )


async def test_coach_endpoint_serializes_targeted_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deck = _deck()
    replacement = TargetedReplacementResponse(
        target_card_name="Medium Value Card",
        summary="Use the grounded anthem.",
        best_pick=CardSearchHit(name="Squirrel Sovereign"),
        options=[
            ReplacementOption(
                card=CardSearchHit(name="Squirrel Sovereign"),
                reason="Supports squirrels.",
                role_match="theme_upgrade",
                tradeoff="Narrower outside this deck.",
            )
        ],
        tool_call_count=1,
    )
    response = CommanderCoachResponse(
        mode="replacement",
        reply=replacement.summary,
        replacement=replacement,
    )

    async def return_deck(*_args: object, **_kwargs: object) -> DeckDetailResponse:
        return deck

    async def return_body(*_args: object, **_kwargs: object) -> CommanderCoachRequest:
        return CommanderCoachRequest(message="Replace Medium Value Card")

    async def no_memory(*_args: object, **_kwargs: object) -> None:
        return None

    async def return_response(*_args: object, **_kwargs: object) -> CommanderCoachResponse:
        return response

    monkeypatch.setattr(ai, "_require_deck", return_deck)
    monkeypatch.setattr(ai, "_request_with_memory", return_body)
    monkeypatch.setattr(ai, "_handle_assistant_memory", no_memory)
    monkeypatch.setattr(ai.commander_coach, "run_coach", return_response)
    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(db_pool=None))})
    account = AccountResponse(
        id=uuid4(),
        display_name="Coach Tester",
        email="coach@example.com",
        created_at=datetime.now(UTC),
    )

    result = await ai.coach_deck(
        deck.id,
        CommanderCoachRequest(message="Replace Medium Value Card"),
        request,
        account,
    )

    payload = result.model_dump(mode="json")["data"]
    assert payload["mode"] == "replacement"
    assert payload["doctor"] is None
    assert payload["replacement"] == {
        "target_card_name": "Medium Value Card",
        "summary": "Use the grounded anthem.",
        "keep_reason": None,
        "best_pick": CardSearchHit(name="Squirrel Sovereign").model_dump(mode="json"),
        "options": [
            {
                "card": CardSearchHit(name="Squirrel Sovereign").model_dump(mode="json"),
                "reason": "Supports squirrels.",
                "role_match": "theme_upgrade",
                "tradeoff": "Narrower outside this deck.",
            }
        ],
        "tool_call_count": 1,
    }
