"""Tests for the pydantic-ai-based simulation analysis agent."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic_ai import models
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from mtg_helper.models.ai import (
    AnalysisFinding,
    CardSearchHit,
    SimulationAnalysisResponse,
    SwapSuggestion,
)
from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.models.playtest import (
    ColorScrewStats,
    CommanderStats,
    MulliganReasonStats,
    OpeningHandStats,
    PlaytestStats,
    TurnStat,
)
from mtg_helper.services import simulation_analysis_service as sas

# Block any actual model requests from leaking through to a real provider.
models.ALLOW_MODEL_REQUESTS = False


def _make_stats() -> PlaytestStats:
    turn = TurnStat(
        turn=1,
        avg_lands_in_play=1.0,
        avg_mana_available=1.0,
        avg_mana_spent=0.5,
        mana_utilization=0.5,
        avg_spells_cast_cumulative=0.4,
        pct_land_drop=1.0,
        pct_cast_any=0.4,
        avg_dead_cards=1.2,
        avg_color_dead_cards=0.1,
        avg_interaction_in_hand=0.3,
        avg_cards_drawn_extra=0.0,
        avg_selection_events=0.0,
        avg_tutors_cast=0.0,
        avg_cards_in_hand=6.0,
        lands_p25=1.0,
        lands_p50=1.0,
        lands_p75=1.0,
        mana_p25=1.0,
        mana_p50=1.0,
        mana_p75=1.0,
        avg_mana_unspent=0.5,
        avg_hand_lands=2.0,
        avg_hand_ramp=0.5,
        avg_hand_draw=0.5,
        avg_hand_interaction=0.5,
        avg_hand_tutors=0.0,
        avg_hand_other=2.5,
    )
    return PlaytestStats(
        trials=10,
        turns=1,
        on_the_play=True,
        avg_mulligans=0.5,
        mulligan_distribution=[6, 3, 1, 0],
        avg_total_spells_cast=0.4,
        total_spells_stddev=0.1,
        pct_flood=0.05,
        pct_screw=0.05,
        avg_first_missed_land_turn=4.5,
        opening_hand=OpeningHandStats(
            pct_screwed_mull=0.0,
            pct_balanced=1.0,
            pct_flood_mull=0.0,
            pct_kept_7=0.85,
            pct_kept_6=0.10,
            pct_kept_5=0.05,
            pct_kept_le4=0.0,
        ),
        color_screw=ColorScrewStats(pct_color_screw=0.0, shortages_by_color={}),
        commander=CommanderStats(name="Vorinclex", avg_cast_turn=6.1, pct_ever_cast=0.7),
        partner=None,
        mulligan_reasons=MulliganReasonStats(
            total=10, low_lands=0.1, high_lands=0.0, no_commander_color=0.0, no_early_play=0.05
        ),
        per_turn=[turn],
    )


def _make_deck() -> DeckDetailResponse:
    now = datetime(2026, 5, 18)
    cmdr = CommanderCardSummary(
        id=uuid4(),
        name="Vorinclex",
        mana_cost="{4}{G}{G}",
        cmc=Decimal("6"),
        type_line="Legendary Creature — Praetor",
        oracle_text=None,
        image_uri=None,
        color_identity=["G"],
        power=6,
        tags=[],
    )
    forest = DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name="Forest",
        mana_cost=None,
        cmc=Decimal("0"),
        type_line="Basic Land — Forest",
        oracle_text=None,
        color_identity=["G"],
        image_uri=None,
        rarity=None,
        quantity=37,
        categories=[],
        added_by="ai",
        ai_reasoning=None,
        qualifying_stages=["lands"],
        tags=[],
        power=None,
        price_eur_cents=None,
    )
    return DeckDetailResponse(
        id=uuid4(),
        name="Test Deck",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=cmdr.id,
        partner_id=None,
        commander_color_identity=["G"],
        commander_card=cmdr,
        partner_card=None,
        owner_email=None,
        created_at=now,
        updated_at=now,
        cards=[forest],
    )


def _final_response(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    """FunctionModel callback: emit a final ``SimulationAnalysisResponse`` as
    a ``final_result`` tool call so pydantic-ai accepts it as the output.
    """
    payload = SimulationAnalysisResponse(
        summary="Looks fine.",
        findings=[
            AnalysisFinding(
                category="mana_base",
                severity="info",
                title="Healthy",
                detail="No issues found.",
                evidence="Mulligan rate within range.",
            )
        ],
        swap_suggestions=[
            SwapSuggestion(
                remove=["Bear"],
                add=[CardSearchHit(name="Sol Ring")],
                reason="Better ramp.",
            )
        ],
    )
    return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args=payload.model_dump())])


def _tool_then_final(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """First request: call ``card_search``. Subsequent: final response.
    pydantic-ai threads the tool return into ``messages`` so we detect the
    second turn by looking for any ``ToolReturnPart``.
    """
    has_tool_return = any(
        isinstance(p, ToolReturnPart) for m in messages for p in getattr(m, "parts", [])
    )
    if not has_tool_return:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="card_search",
                    args={"text_query": "ramp", "limit": 3},
                )
            ]
        )
    return _final_response(messages, info)


@pytest.fixture
def mock_pool() -> MagicMock:
    return MagicMock()


async def test_analyze_returns_structured_response(mock_pool: MagicMock) -> None:
    agent = sas._get_agent()
    with agent.override(model=FunctionModel(_final_response)):
        result = await sas.analyze_simulation(
            pool=mock_pool,
            deck=_make_deck(),
            stats=_make_stats(),
        )
    assert isinstance(result, SimulationAnalysisResponse)
    assert result.summary == "Looks fine."
    assert len(result.findings) == 1
    assert result.findings[0].category == "mana_base"
    assert result.swap_suggestions == []
    assert result.tool_call_count == 0


async def test_analyze_runs_card_search_tool(
    monkeypatch: pytest.MonkeyPatch, mock_pool: MagicMock
) -> None:
    # Stub the DB-touching tool body so we don't need Postgres.
    fake_hits = [CardSearchHit(name="Arcane Signet", cmc=2.0)]
    monkeypatch.setattr(sas, "search_cards", AsyncMock(return_value=fake_hits))
    agent = sas._get_agent()
    with agent.override(model=FunctionModel(_tool_then_final)):
        result = await sas.analyze_simulation(
            pool=mock_pool,
            deck=_make_deck(),
            stats=_make_stats(),
        )
    assert result.tool_call_count == 1
    assert result.summary == "Looks fine."


async def test_analyze_handles_timeout(
    monkeypatch: pytest.MonkeyPatch, mock_pool: MagicMock
) -> None:
    async def _hang(*_a: object, **_kw: object) -> None:
        # Sleep longer than the wall-clock cap to force the asyncio.wait_for
        # path through TimeoutError.
        import asyncio

        await asyncio.sleep(60)

    monkeypatch.setattr(sas, "_WALL_CLOCK_SECONDS", 0.05)
    agent = sas._get_agent()
    monkeypatch.setattr(agent, "run", _hang)
    result = await sas.analyze_simulation(
        pool=mock_pool,
        deck=_make_deck(),
        stats=_make_stats(),
    )
    assert "timed out" in result.summary.lower()
