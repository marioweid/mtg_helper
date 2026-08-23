"""Tests for the shared OpenAI Responses model and agent settings."""

from collections.abc import Callable
from typing import cast

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
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


def test_factory_uses_fixed_openai_responses_model() -> None:
    model = make_openai_model()

    assert isinstance(model, OpenAIResponsesModel)
    assert isinstance(model._provider, OpenAIProvider)
    assert model.model_name == "gpt-5.6-luna"


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
