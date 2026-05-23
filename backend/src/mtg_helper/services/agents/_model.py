"""Shared Gemini ``GoogleModel`` construction for every pydantic-ai agent."""

from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from mtg_helper.config import settings


def make_google_model(model_name: str | None = None) -> GoogleModel:
    """Build a ``GoogleModel`` from app settings.

    Args:
        model_name: Optional model override; defaults to ``settings.chat_model``.

    Returns:
        Configured ``GoogleModel`` ready to attach to an ``Agent``.
    """
    provider = GoogleProvider(api_key=settings.gemini_api_key)
    return GoogleModel(model_name or settings.chat_model, provider=provider)
