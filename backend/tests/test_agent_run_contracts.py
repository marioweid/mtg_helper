"""Behavioral contracts for all Pydantic AI run sites."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import ModuleType, SimpleNamespace
from typing import Any, Literal, cast
from uuid import uuid4

import asyncpg
import pytest
from pydantic_ai import RunUsage, UsageLimits, models

from mtg_helper.models.ai import (
    CommanderCoachRequest,
    CommanderCoachResponse,
    CommanderSuggestResponse,
    DeckDoctorResponse,
    DescribeResponse,
    KeywordExtractResponse,
    SimulationAnalysisResponse,
)
from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services import mtg_assistant, simulation_analysis_service
from mtg_helper.services.agents import (
    commander_suggestor_agent,
    deck_doctor_agent,
    describe_agent,
    extract_agent,
)
from mtg_helper.services.agents.commander_suggestor_agent import CommanderSuggestAgentOutput

models.ALLOW_MODEL_REQUESTS = False
pytestmark = pytest.mark.no_db

_Invoke = Callable[[pytest.MonkeyPatch], Awaitable[object]]


@dataclass(frozen=True)
class _RunCase:
    name: str
    module: ModuleType
    agent_accessor: str
    invoke: _Invoke
    output: object
    limits: UsageLimits
    workflow: str
    operation: str
    failure_policy: Literal["propagate", "fallback"]
    failure_result: object | None = None


class _FakeResult:
    def __init__(self, output: object, usage: RunUsage) -> None:
        self.output = output
        self._usage = usage

    def usage(self) -> RunUsage:
        return self._usage


class _FakeAgent:
    def __init__(self, output: object, usage: RunUsage, error: Exception | None = None) -> None:
        self._result = _FakeResult(output, usage)
        self._error = error
        self.usage_limits: list[UsageLimits] = []

    async def run(self, *_args: object, **kwargs: object) -> _FakeResult:
        self.usage_limits.append(cast(UsageLimits, kwargs["usage_limits"]))
        if self._error is not None:
            raise self._error
        return self._result


def _deck() -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_id = uuid4()
    card = DeckCardItem(
        deck_card_id=uuid4(),
        card_id=uuid4(),
        scryfall_id=uuid4(),
        name="Test Card",
        mana_cost="{2}{G}",
        cmc=Decimal("3"),
        type_line="Creature",
        oracle_text="Test oracle text.",
        color_identity=["G"],
        image_uri=None,
        rarity="common",
        quantity=1,
        added_by="user",
        ai_reasoning=None,
    )
    return DeckDetailResponse(
        id=uuid4(),
        name="Contract Test Deck",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["G"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Test Commander",
            mana_cost="{2}{G}",
            oracle_text="Test commander text.",
            color_identity=["G"],
        ),
        owner_email=None,
        created_at=now,
        updated_at=now,
        cards=[card],
    )


async def _value(value: object) -> object:
    return value


async def _invoke_suggest(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setattr(
        commander_suggestor_agent, "load_theme_prompt_catalog", lambda _: _value("")
    )
    monkeypatch.setattr(
        commander_suggestor_agent, "load_keyword_prompt_catalog", lambda _: _value("")
    )
    monkeypatch.setattr(
        commander_suggestor_agent,
        "build_response",
        lambda *_args, **kwargs: _value(
            CommanderSuggestResponse(
                reply=kwargs["reply"],
                done=kwargs["done"],
                intent=kwargs["intent"],
                commanders=[],
            )
        ),
    )
    return await commander_suggestor_agent.suggest_turn(
        cast(asyncpg.Pool, None), [], "brew", None, limit=1
    )


def _patch_card_lookup(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    card = SimpleNamespace(
        name="Test Commander",
        type_line="Legendary Creature",
        oracle_text="Test text.",
        color_identity=["G"],
    )
    monkeypatch.setattr(module.card_service, "get_card_by_scryfall_id", lambda *_: _value(card))


async def _invoke_describe(monkeypatch: pytest.MonkeyPatch) -> object:
    _patch_card_lookup(monkeypatch, describe_agent)
    return await describe_agent.describe_turn(
        cast(asyncpg.Pool, None), uuid4(), None, 3, [], message="brew"
    )


async def _invoke_extract(monkeypatch: pytest.MonkeyPatch) -> object:
    _patch_card_lookup(monkeypatch, extract_agent)
    monkeypatch.setattr(extract_agent, "load_theme_prompt_catalog", lambda _: _value(""))
    monkeypatch.setattr(extract_agent, "load_theme_tags", lambda _: _value(set()))
    return await extract_agent.extract_turn(
        cast(asyncpg.Pool, None), uuid4(), None, 3, [], message="brew"
    )


async def _invoke_doctor(_monkeypatch: pytest.MonkeyPatch) -> object:
    return await deck_doctor_agent.doctor_deck(cast(asyncpg.Pool, None), _deck())


async def _invoke_assistant(_monkeypatch: pytest.MonkeyPatch) -> object:
    return await mtg_assistant.run_assistant(
        cast(asyncpg.Pool, None), _deck(), CommanderCoachRequest(message="hello")
    )


async def _invoke_simulation(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setattr(simulation_analysis_service, "_build_prompt", lambda *_: "prompt")
    monkeypatch.setattr(
        simulation_analysis_service, "_enforce_severity_floor", lambda output, _: output
    )
    return await simulation_analysis_service.analyze_simulation(
        cast(asyncpg.Pool, None), _deck(), cast(Any, object())
    )


def _limits(requests: int, tools: int, inputs: int, outputs: int) -> UsageLimits:
    return UsageLimits(
        request_limit=requests,
        tool_calls_limit=tools,
        input_tokens_limit=inputs,
        output_tokens_limit=outputs,
    )


_CASES = [
    _RunCase(
        "commander_suggestor",
        commander_suggestor_agent,
        "get_agent",
        _invoke_suggest,
        CommanderSuggestAgentOutput(reply="question"),
        _limits(2, 0, 24_000, 3_000),
        "commander_suggestor",
        "suggest",
        "fallback",
        CommanderSuggestResponse(
            reply="Do you have a color identity in mind, or any colors you want to avoid?",
            done=False,
            intent={"direction": "brew"},
            commanders=[],
        ),
    ),
    _RunCase(
        "describe",
        describe_agent,
        "get_agent",
        _invoke_describe,
        DescribeResponse(reply="done", done=True),
        _limits(2, 0, 16_000, 3_000),
        "describe",
        "turn",
        "propagate",
    ),
    _RunCase(
        "extract",
        extract_agent,
        "get_agent",
        _invoke_extract,
        KeywordExtractResponse(reply="done", done=True),
        _limits(2, 0, 24_000, 3_000),
        "extract",
        "turn",
        "propagate",
    ),
    _RunCase(
        "deck_doctor",
        deck_doctor_agent,
        "_get_agent",
        _invoke_doctor,
        DeckDoctorResponse(summary="done", game_plan="test"),
        _limits(17, 14, 128_000, 16_000),
        "deck_doctor",
        "diagnose",
        "propagate",
    ),
    _RunCase(
        "assistant",
        mtg_assistant,
        "get_agent",
        _invoke_assistant,
        mtg_assistant.AssistantAnswer(reply="done"),
        _limits(8, 6, 64_000, 8_000),
        "mtg_assistant",
        "answer",
        "fallback",
        CommanderCoachResponse(
            mode="chat",
            reply="I couldn't complete a verified answer. Please try the request again.",
        ),
    ),
    _RunCase(
        "simulation",
        simulation_analysis_service,
        "_get_agent",
        _invoke_simulation,
        SimulationAnalysisResponse(summary="done"),
        _limits(12, 10, 96_000, 16_000),
        "simulation_analysis",
        "analyze",
        "propagate",
    ),
]


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
async def test_run_site_forwards_limits_and_logs_success_once(
    monkeypatch: pytest.MonkeyPatch, case: _RunCase
) -> None:
    usage = RunUsage(requests=1, input_tokens=2, output_tokens=3)
    agent = _FakeAgent(case.output, usage)
    logged: list[tuple[str, str, RunUsage]] = []
    monkeypatch.setattr(case.module, case.agent_accessor, lambda: agent)
    monkeypatch.setattr(case.module, "log_run_usage", lambda *args: logged.append(args))

    await case.invoke(monkeypatch)

    assert agent.usage_limits == [case.limits]
    assert logged == [(case.workflow, case.operation, usage)]


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
async def test_run_failure_preserves_policy_and_does_not_log_success(
    monkeypatch: pytest.MonkeyPatch, case: _RunCase
) -> None:
    agent = _FakeAgent(case.output, RunUsage(), RuntimeError("run failed"))
    logged: list[tuple[str, str, RunUsage]] = []
    monkeypatch.setattr(case.module, case.agent_accessor, lambda: agent)
    monkeypatch.setattr(case.module, "log_run_usage", lambda *args: logged.append(args))

    if case.failure_policy == "propagate":
        with pytest.raises(RuntimeError, match="run failed"):
            await case.invoke(monkeypatch)
    else:
        result = await case.invoke(monkeypatch)
        assert case.failure_result is not None
        assert type(result) is type(case.failure_result)
        assert result == case.failure_result

    assert agent.usage_limits == [case.limits]
    assert logged == []


@pytest.mark.parametrize(
    "case",
    [case for case in _CASES if case.failure_policy == "fallback"],
    ids=lambda case: case.name,
)
async def test_fallback_logging_does_not_expose_exception_data(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    case: _RunCase,
) -> None:
    secret = "private prompt and output"
    agent = _FakeAgent(case.output, RunUsage(), RuntimeError(secret))
    monkeypatch.setattr(case.module, case.agent_accessor, lambda: agent)
    caplog.set_level(logging.ERROR)

    await case.invoke(monkeypatch)

    assert f"workflow={case.workflow}" in caplog.text
    assert f"operation={case.operation}" in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert secret not in caplog.text
    assert "Traceback" not in caplog.text
