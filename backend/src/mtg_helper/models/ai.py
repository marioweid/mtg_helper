"""Pydantic models for AI deck building endpoints."""

from uuid import UUID

from pydantic import BaseModel, Field


class BuildRequest(BaseModel):
    """Request body for the staged deck build."""

    stage: str | None = None
    target: int | None = Field(default=None, ge=1, le=99)
    offset: int = Field(default=0, ge=0, le=1000)
    exclude: list[str] | None = Field(default=None, max_length=200)
    collection_ids: list[UUID] | None = None
    max_price_cents: int | None = Field(default=None, gt=0)
    min_price_cents: int | None = Field(default=None, ge=0)
    card_types: list[str] | None = Field(default=None, max_length=10)
    subtypes: list[str] | None = Field(default=None, max_length=10)


class CollectionMembership(BaseModel):
    """A collection that owns the suggested card."""

    id: UUID
    name: str


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
    price_eur_cents: int | None = None
    owned_in: list[CollectionMembership] = Field(default_factory=list)
    qualifying_stages: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


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
    collection_ids: list[UUID] | None = None
    max_price_cents: int | None = Field(default=None, gt=0)
    min_price_cents: int | None = Field(default=None, ge=0)
    card_types: list[str] | None = Field(default=None, max_length=10)
    subtypes: list[str] | None = Field(default=None, max_length=10)


class SuggestResponse(BaseModel):
    """Response from a card suggestion request."""

    suggestions: list[CardSuggestion]
    unresolved: list[str]


class DescribeMessage(BaseModel):
    """A single turn in the description agent conversation."""

    role: str
    content: str = Field(max_length=2000)


class DescribeRequest(BaseModel):
    """Request body for the deck description agent."""

    commander_scryfall_id: UUID
    partner_scryfall_id: UUID | None = None
    bracket: int = Field(default=3, ge=1, le=4)
    history: list[DescribeMessage] = Field(default_factory=list, max_length=24)
    message: str = Field(default="", max_length=2000)


class DescribeResponse(BaseModel):
    """Response from the deck description agent."""

    reply: str
    done: bool
    description: str | None = None
    suggested_name: str | None = None
    stage_targets: dict[str, int] | None = None


class KeywordExtractRequest(BaseModel):
    """Request body for the keyword-extracting deck agent.

    Mirrors ``DescribeRequest`` but the agent is asked to converge on a
    structured set of archetype keywords (Moxfield-style: ``voltron``,
    ``aristocrats``, ``squirrel_tribal``) rather than a free-form description.
    """

    commander_scryfall_id: UUID
    partner_scryfall_id: UUID | None = None
    bracket: int = Field(default=3, ge=1, le=4)
    history: list[DescribeMessage] = Field(default_factory=list, max_length=24)
    message: str = Field(default="", max_length=2000)


class CutsRequest(BaseModel):
    """Request body for AI-suggested cuts from a deck."""

    count: int = Field(default=10, ge=1, le=25)


class CutSuggestion(BaseModel):
    """A single card recommended for removal, with reasoning."""

    scryfall_id: UUID
    name: str
    type_line: str | None = None
    image_uri: str | None = None
    cmc: float | None = None
    reasoning: str


class CutsResponse(BaseModel):
    """Response from a cuts suggestion request."""

    cuts: list[CutSuggestion]
    protected_count: int


class KeywordExtractResponse(BaseModel):
    """Response from the keyword-extracting deck agent.

    ``archetype_tags`` is the running set of canonical keywords the agent has
    inferred from the conversation. The frontend mirrors them as live chips so
    the user can refine selection mid-conversation.
    """

    reply: str
    done: bool
    archetype_tags: list[str] = Field(default_factory=list)
    suggested_name: str | None = None
    stage_targets: dict[str, int] | None = None
