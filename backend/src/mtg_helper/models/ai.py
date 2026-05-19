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
    color_identity: list[str] = Field(default_factory=list)
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


class RiskyCard(BaseModel):
    """A non-land card whose colored pip requirement exceeds available sources.

    ``sources_required`` is the Karsten heuristic for the card's CMC turn and
    solid pip count in the given color.
    """

    card_id: UUID
    name: str
    mana_cost: str | None
    cmc: int = Field(ge=0)
    color: str = Field(pattern="^[WUBRG]$")
    pips_required: int = Field(ge=1)
    sources_available: int = Field(ge=0)
    sources_required: int = Field(ge=0)


class ColorStatus(BaseModel):
    """Per-color mana-base health for a deck."""

    color: str = Field(pattern="^[WUBRG]$")
    pip_count: float = Field(ge=0.0)
    source_count: int = Field(ge=0)
    target: int = Field(ge=0)
    deficit: int = Field(ge=0)
    turn_demand: int = Field(default=0, ge=0)
    turn_deficit: int = Field(default=0, ge=0)
    risky_cards: list[RiskyCard] = Field(default_factory=list)


class ManaBaseReport(BaseModel):
    """Mana-base analysis for a deck — per-color requirements vs sources."""

    total_lands: int = Field(ge=0)
    total_colored_pips: float = Field(ge=0.0)
    colors: list[ColorStatus] = Field(default_factory=list)
    avg_cmc: float = Field(default=0.0, ge=0.0)
    ramp_count: int = Field(default=0, ge=0)
    recommended_lands: int = Field(default=0, ge=0)
    land_delta: int = Field(default=0)


class ManaFixResponse(BaseModel):
    """Mana-base report plus suggested lands to fix deficient colors."""

    report: ManaBaseReport
    suggestions: list[CardSuggestion] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


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
