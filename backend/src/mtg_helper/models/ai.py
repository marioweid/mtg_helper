"""Pydantic models for AI deck building endpoints."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class BuildRequest(BaseModel):
    """Request body for advancing the staged deck build."""

    action: Literal["next_stage"] = "next_stage"


class CardSuggestion(BaseModel):
    """A single AI-suggested card with reasoning."""

    scryfall_id: UUID
    name: str
    mana_cost: str | None
    type_line: str | None
    image_uri: str | None
    category: str
    reasoning: str
    synergies: list[str]


class BuildResponse(BaseModel):
    """Response from a staged deck build step."""

    stage: str
    stage_number: int
    total_stages: int
    suggestions: list[CardSuggestion]
    unresolved: list[str]


class SuggestRequest(BaseModel):
    """Request body for free-form card suggestions."""

    prompt: str = Field(min_length=1, max_length=500)
    count: int = Field(default=10, ge=1, le=25)


class SuggestResponse(BaseModel):
    """Response from a card suggestion request."""

    suggestions: list[CardSuggestion]
    unresolved: list[str]


class ChatRequest(BaseModel):
    """Request body for free-form deck chat."""

    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    """Response from a deck chat message."""

    reply: str
    suggestions: list[CardSuggestion]
