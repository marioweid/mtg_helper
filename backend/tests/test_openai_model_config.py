"""Tests for the shared OpenAI Responses model and agent settings."""

from collections.abc import Callable
from typing import cast

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import ModelRequestParameters, ModelSettings
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.openai import OpenAIProvider

from mtg_helper.config import Settings
from mtg_helper.services.agents._model import make_openai_model, openai_model_settings
from mtg_helper.services.agents.commander_suggestor_agent import (
    _build_agent as build_commander_suggestor,
)
from mtg_helper.services.agents.deck_doctor_agent import _build_agent as build_deck_doctor
from mtg_helper.services.agents.describe_agent import _build_agent as build_describe
from mtg_helper.services.agents.extract_agent import _build_agent as build_extract
from mtg_helper.services.mtg_assistant import _build_agent as build_mtg_assistant
from mtg_helper.services.simulation_analysis_service import (
    _build_agent as build_simulation_analysis,
)

pytestmark = pytest.mark.no_db


class CapturingModel(TestModel):
    """Retain settings sent through a real Pydantic AI model request."""

    request_settings: list[ModelSettings | None]
    parameters: list[ModelRequestParameters]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.request_settings = []
        self.parameters = []

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        self.request_settings.append(model_settings)
        self.parameters.append(model_request_parameters)
        return await super().request(messages, model_settings, model_request_parameters)


def test_openai_api_key_is_required() -> None:
    with pytest.raises(ValueError, match="openai_api_key"):
        Settings(_env_file=None, database_url="postgresql://unused", openai_api_key="")


def test_openai_settings_are_private_and_low_verbosity() -> None:
    model_settings = openai_model_settings(max_tokens=2048, reasoning="minimal")

    assert model_settings == {
        "max_tokens": 2048,
        "openai_reasoning_effort": "minimal",
        "openai_store": False,
        "openai_text_verbosity": "low",
    }


def test_openai_settings_allow_workflow_specific_verbosity() -> None:
    model_settings = openai_model_settings(
        max_tokens=4096,
        reasoning="low",
        verbosity="medium",
    )

    assert model_settings["max_tokens"] == 4096
    assert model_settings["openai_text_verbosity"] == "medium"


def test_openai_settings_omit_an_output_limit_when_a_workflow_does_not_set_one() -> None:
    """A workflow can defer output length to its provider without changing other settings."""
    model_settings = openai_model_settings(reasoning="high", verbosity="medium")

    assert "max_tokens" not in model_settings
    assert model_settings["openai_reasoning_effort"] == "high"
    assert model_settings["openai_text_verbosity"] == "medium"


def test_factory_uses_fixed_openai_responses_model() -> None:
    model = make_openai_model()

    assert isinstance(model, OpenAIResponsesModel)
    assert isinstance(model._provider, OpenAIProvider)
    assert model.model_name == "gpt-5.6-luna"


def test_tutor_uses_its_approved_model_without_changing_the_shared_default() -> None:
    """Tutor opts in while Coach and Discover retain their existing default model."""
    from mtg_helper.services.recommendations.budget import MODEL as DISCOVER_MODEL
    from mtg_helper.services.tutor.teaching import _agent

    tutor = _agent("test")
    coach = build_mtg_assistant()

    assert isinstance(tutor.model, OpenAIResponsesModel)
    assert tutor.model.model_name == "gpt-6.1-sol"
    assert tutor.model_settings["openai_reasoning_effort"] == "high"
    assert "max_tokens" not in tutor.model_settings
    assert isinstance(coach.model, OpenAIResponsesModel)
    assert coach.model.model_name == "gpt-5.6-luna"
    assert DISCOVER_MODEL == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_tutor_model_disables_sdk_retries_without_changing_shared_defaults() -> None:
    """Tutor owns a zero-retry SDK client while ordinary models retain the SDK default."""
    from mtg_helper.services.tutor.teaching import _agent

    tutor = _agent("test")
    shared = make_openai_model()

    try:
        assert tutor.model.client.max_retries == 0
        assert shared.client.max_retries == 2
    finally:
        await tutor.model.client.close()


@pytest.mark.asyncio
async def test_tutor_request_spy_receives_high_reasoning_without_an_output_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tutor sends its approved settings through one real agent request."""
    from mtg_helper.models.tutor import TutorCardFact, TutorEvidence
    from mtg_helper.services.tutor import teaching

    model = CapturingModel(
        call_tools=[],
        custom_output_args={
            "title": "Bounded guide",
            "content": "Interpretation: use the supplied cards.",
            "keep": {"cards": ["Forest"] * 7, "explanation": "Keep mana."},
            "mulligan": {"cards": ["Forest"] * 7, "explanation": "No action."},
            "context_dependent": {"cards": ["Forest"] * 7, "explanation": "Table dependent."},
        },
    )
    requested_models: list[str] = []
    requested_retry_budgets: list[int | None] = []
    usage_limit_calls: list[dict[str, int]] = []
    usage_limits = teaching.UsageLimits

    def make_capturing_model(
        *, model_name: str, sdk_max_retries: int | None = None
    ) -> CapturingModel:
        requested_models.append(model_name)
        requested_retry_budgets.append(sdk_max_retries)
        return model

    monkeypatch.setattr(teaching, "make_openai_model", make_capturing_model)

    def capture_usage_limits(**kwargs: int) -> object:
        usage_limit_calls.append(kwargs)
        return usage_limits(**kwargs)

    monkeypatch.setattr(teaching, "UsageLimits", capture_usage_limits)
    guide_input = teaching.TeachingInput(
        mode="commander",
        description=None,
        bracket=None,
        evidence=TutorEvidence(
            commanders=[],
            cards=[
                TutorCardFact(
                    oracle_id=None,
                    name="Forest",
                    quantity=7,
                    type_line="Basic Land",
                    oracle_text="{T}: Add {G}.",
                )
            ],
        ),
    )

    await teaching.run_agent(guide_input, "Commander", "test")

    assert len(model.request_settings) == 1
    assert model.request_settings[0] is not None
    assert model.request_settings[0]["openai_reasoning_effort"] == "high"
    assert "max_tokens" not in model.request_settings[0]
    assert len(model.parameters) == 1
    assert requested_models == ["gpt-6.1-sol"]
    assert requested_retry_budgets == [0]
    assert usage_limit_calls == [{"request_limit": 1, "tool_calls_limit": 0}]


@pytest.mark.parametrize(
    ("builder", "reasoning", "verbosity"),
    [
        (build_describe, "minimal", "low"),
        (build_extract, "minimal", "low"),
        (build_commander_suggestor, "low", "low"),
        (build_mtg_assistant, "low", "medium"),
        (build_deck_doctor, "low", "low"),
        (build_simulation_analysis, "low", "low"),
    ],
)
def test_agents_use_openai_responses_with_expected_reasoning(
    builder: Callable[[], Agent],
    reasoning: str,
    verbosity: str,
) -> None:
    agent = builder()

    assert isinstance(agent.model, OpenAIResponsesModel)
    assert agent.model.model_name == "gpt-5.6-luna"
    assert isinstance(agent.model_settings, dict)
    model_settings = cast(OpenAIResponsesModelSettings, agent.model_settings)
    assert model_settings["openai_store"] is False
    assert model_settings["openai_text_verbosity"] == verbosity
    assert model_settings["openai_reasoning_effort"] == reasoning


def test_mtg_assistant_uses_quality_output_settings() -> None:
    agent = build_mtg_assistant()

    assert isinstance(agent.model_settings, dict)
    model_settings = cast(OpenAIResponsesModelSettings, agent.model_settings)
    assert model_settings["max_tokens"] == 4096
    assert model_settings["openai_text_verbosity"] == "medium"
