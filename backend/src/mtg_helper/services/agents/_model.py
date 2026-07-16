"""Shared Gemini model construction and settings for pydantic-ai agents."""

from typing import Literal

from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from mtg_helper.config import settings

ThinkingLevel = Literal["minimal", "low", "medium", "high"]


def make_google_model(model_name: str | None = None) -> GoogleModel:
    """Build a ``GoogleModel`` from app settings.

    Args:
        model_name: Optional model override; defaults to ``settings.chat_model``.

    Returns:
        Configured ``GoogleModel`` ready to attach to an ``Agent``.
    """
    provider = GoogleProvider(api_key=settings.gemini_api_key)
    return GoogleModel(model_name or settings.chat_model, provider=provider)


def make_fast_google_model() -> GoogleModel:
    """Build the lower-cost Gemini model used for lightweight agent tasks."""
    return make_google_model(settings.fast_model)


def fast_google_model_settings(
    *,
    max_tokens: int,
    temperature: float | None = None,
    thinking: ThinkingLevel | None = None,
) -> dict[str, object]:
    """Build generation settings for the configured lower-cost model."""
    return google_model_settings(
        max_tokens=max_tokens,
        temperature=temperature,
        model_name=settings.fast_model,
        thinking=thinking,
    )


def google_model_settings(
    *,
    max_tokens: int,
    temperature: float | None = None,
    model_name: str | None = None,
    thinking: ThinkingLevel | None = None,
) -> dict[str, object]:
    """Build settings compatible with the selected Gemini generation model.

    Gemini 3.5 does not receive legacy sampling parameters. Explicit thinking
    levels keep reasoning cost proportional to each agent's task. Older model
    overrides retain their existing temperature configuration.
    """
    model_settings: dict[str, object] = {"max_tokens": max_tokens}
    if thinking is not None:
        model_settings["thinking"] = thinking
    selected_model = model_name or settings.chat_model
    if temperature is not None and "gemini-3.5" not in selected_model.lower():
        model_settings["temperature"] = temperature
    return model_settings
