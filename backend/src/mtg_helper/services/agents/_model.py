"""Shared OpenAI Responses model construction and settings."""

from typing import Literal

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from mtg_helper.config import settings

ReasoningLevel = Literal["minimal", "low", "high"]
TextVerbosity = Literal["low", "medium"]
OPENAI_MODEL = "gpt-5.6-luna"


def make_openai_model(
    *, model_name: str = OPENAI_MODEL, sdk_max_retries: int | None = None
) -> OpenAIResponsesModel:
    """Build one OpenAI Responses model from application settings.

    Args:
        model_name: Explicit workflow model; defaults to the shared application model.
        sdk_max_retries: Optional OpenAI SDK retry budget for an isolated workflow client.
    """
    api_key = settings.openai_api_key.get_secret_value()
    provider = (
        OpenAIProvider(api_key=api_key)
        if sdk_max_retries is None
        else OpenAIProvider(openai_client=AsyncOpenAI(api_key=api_key, max_retries=sdk_max_retries))
    )
    return OpenAIResponsesModel(model_name, provider=provider)


def openai_model_settings(
    *,
    max_tokens: int | None = None,
    reasoning: ReasoningLevel,
    verbosity: TextVerbosity = "low",
) -> OpenAIResponsesModelSettings:
    """Build private OpenAI Responses settings, omitting an unset provider output limit."""
    model_settings = OpenAIResponsesModelSettings(
        openai_reasoning_effort=reasoning,
        openai_store=False,
        openai_text_verbosity=verbosity,
    )
    if max_tokens is not None:
        model_settings["max_tokens"] = max_tokens
    return model_settings
