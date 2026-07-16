"""Tests for shared Gemini model selection and compatible settings."""

from collections.abc import Callable

import pytest
from pydantic_ai import Agent

from mtg_helper.config import Settings, settings
from mtg_helper.services.agents._model import (
    fast_google_model_settings,
    google_model_settings,
    make_fast_google_model,
    make_google_model,
)
from mtg_helper.services.agents.commander_suggestor_agent import (
    _build_agent as build_commander_suggestor,
)
from mtg_helper.services.agents.deck_doctor_agent import _build_agent as build_deck_doctor
from mtg_helper.services.agents.describe_agent import _build_agent as build_describe
from mtg_helper.services.agents.extract_agent import _build_agent as build_extract
from mtg_helper.services.commander_coach.router_agent import _build_agent as build_router
from mtg_helper.services.commander_coach.specialists.challenger import (
    _build_agent as build_challenger,
)
from mtg_helper.services.commander_coach.specialists.cuts import _build_agent as build_cuts
from mtg_helper.services.commander_coach.specialists.identity import (
    _build_agent as build_identity,
)
from mtg_helper.services.commander_coach.specialists.replacement import (
    _build_agent as build_replacement,
)
from mtg_helper.services.commander_coach.specialists.upgrades import (
    _build_agent as build_upgrades,
)
from mtg_helper.services.mtg_assistant import _build_agent as build_mtg_assistant
from mtg_helper.services.simulation_analysis_service import (
    _build_agent as build_simulation_analysis,
)


def test_settings_default_to_stable_gemini_35(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHAT_MODEL", raising=False)
    monkeypatch.delenv("FAST_MODEL", raising=False)

    app_settings = Settings(_env_file=None, database_url="postgresql://unused")

    assert app_settings.chat_model == "gemini-3.5-flash"
    assert app_settings.fast_model == "gemini-3.1-flash-lite"


def test_chat_model_environment_override_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAT_MODEL", "gemini-2.5-flash")

    app_settings = Settings(_env_file=None, database_url="postgresql://unused")

    assert app_settings.chat_model == "gemini-2.5-flash"


def test_fast_model_environment_override_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAST_MODEL", "gemini-2.5-flash-lite")

    app_settings = Settings(_env_file=None, database_url="postgresql://unused")

    assert app_settings.fast_model == "gemini-2.5-flash-lite"


def test_gemini_35_settings_omit_temperature() -> None:
    model_settings = google_model_settings(
        model_name="gemini-3.5-flash",
        max_tokens=2048,
        temperature=0.2,
        thinking="low",
    )

    assert model_settings == {"max_tokens": 2048, "thinking": "low"}


def test_legacy_override_retains_temperature() -> None:
    model_settings = google_model_settings(
        model_name="gemini-2.5-flash",
        max_tokens=2048,
        temperature=0.2,
        thinking="medium",
    )

    assert model_settings == {
        "max_tokens": 2048,
        "temperature": 0.2,
        "thinking": "medium",
    }


def test_fast_model_settings_use_fast_model_compatibility() -> None:
    model_settings = fast_google_model_settings(
        max_tokens=512,
        temperature=0.2,
        thinking="minimal",
    )

    assert model_settings == {
        "max_tokens": 512,
        "temperature": 0.2,
        "thinking": "minimal",
    }


def test_default_google_model_uses_gemini_35() -> None:
    model = make_google_model()

    assert model.model_name == "gemini-3.5-flash"


def test_default_fast_google_model_uses_gemini_31_flash_lite() -> None:
    model = make_fast_google_model()

    assert model.model_name == "gemini-3.1-flash-lite"


@pytest.mark.parametrize(
    ("builder", "uses_fast_model", "thinking"),
    [
        (build_router, True, "minimal"),
        (build_describe, True, "minimal"),
        (build_extract, True, "minimal"),
        (build_commander_suggestor, True, "low"),
        (build_identity, True, "low"),
        (build_mtg_assistant, False, "low"),
        (build_deck_doctor, False, "medium"),
        (build_simulation_analysis, False, "medium"),
        (build_challenger, False, "low"),
        (build_cuts, False, "medium"),
        (build_replacement, False, "low"),
        (build_upgrades, False, "medium"),
    ],
)
def test_agents_use_expected_cost_tier_and_thinking_level(
    builder: Callable[[], Agent],
    uses_fast_model: bool,
    thinking: str,
) -> None:
    agent = builder()
    expected_model = settings.fast_model if uses_fast_model else settings.chat_model

    assert agent.model.model_name == expected_model
    assert agent.model_settings["thinking"] == thinking
