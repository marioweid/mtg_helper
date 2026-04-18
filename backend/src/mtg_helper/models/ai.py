"""Pydantic models for AI deck building endpoints."""

from uuid import UUID

from pydantic import BaseModel, Field


class BuildRequest(BaseModel):
    """Request body for the staged deck build."""

    stage: str | None = None
    target: int | None = Field(default=None, ge=1, le=99)
    exclude: list[str] | None = Field(default=None, max_length=200)
    collection_id: UUID | None = None
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)


class CardSuggestion(BaseModel):
    """A single suggested card with reasoning."""

    scryfall_id: UUID
    name: str
    mana_cost: str | None
    type_line: str | None
    image_uri: str | None
    oracle_text: str | None = None
    power: str | None = None
    toughness: str | None = None
    rarity: str | None = None
    cmc: float | None = None
    category: str
    reasoning: str
    synergies: list[str]
    highlight_reasons: list[str] | None = None


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
    collection_id: UUID | None = None
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)


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


class DescribeMessage(BaseModel):
    """A single turn in the description agent conversation."""

    role: str
    content: str


class DescribeRequest(BaseModel):
    """Request body for the deck description agent."""

    commander_scryfall_id: UUID
    partner_scryfall_id: UUID | None = None
    bracket: int = Field(default=3, ge=1, le=4)
    history: list[DescribeMessage] = Field(default_factory=list)
    message: str = Field(default="", max_length=2000)


class DescribeResponse(BaseModel):
    """Response from the deck description agent."""

    reply: str
    done: bool
    description: str | None = None
    suggested_name: str | None = None
    stage_targets: dict[str, int] | None = None
