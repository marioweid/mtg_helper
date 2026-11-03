"""Shared OpenAI Responses model construction and settings."""

from typing import Literal

from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from mtg_helper.config import settings

ReasoningLevel = Literal["minimal", "low", "high"]
TextVerbosity = Literal["low", "medium"]
OPENAI_MODEL = "gpt-5.6-luna"


def make_openai_model(*, model_name: str = OPENAI_MODEL) -> OpenAIResponsesModel:
    """Build one OpenAI Responses model from application settings.

    Args:
        model_name: Explicit workflow model; defaults to the shared application model.
    """
    provider = OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())
    return OpenAIResponsesModel(model_name, provider=provider)


def openai_model_settings(
    *,
    max_tokens: int,
    reasoning: ReasoningLevel,
    verbosity: TextVerbosity = "low",
) -> OpenAIResponsesModelSettings:
    """Build private, low-verbosity settings for one OpenAI Responses run."""
    return OpenAIResponsesModelSettings(
        max_tokens=max_tokens,
        openai_reasoning_effort=reasoning,
        openai_store=False,
        openai_text_verbosity=verbosity,
    )
