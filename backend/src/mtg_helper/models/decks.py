"""Pydantic models for deck requests and responses."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field

from mtg_helper.models.ai import CollectionMembership
from mtg_helper.models.mana_curve import DeckManaCurve


class DeckCreate(BaseModel):
    """Request body for creating a new deck."""

    commander_scryfall_id: UUID
    partner_scryfall_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    bracket: int = Field(default=3, ge=1, le=5)
    stage_targets: dict[str, int] | None = None
    suggestion_collection_ids: list[UUID] = Field(default_factory=list)
    archetype_tags: list[str] = Field(default_factory=list)


class DeckUpdate(BaseModel):
    """Request body for updating deck metadata. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    bracket: int | None = Field(default=None, ge=1, le=5)
    stage: str | None = None
    stage_targets: dict[str, int] | None = None
    suggestion_collection_ids: list[UUID] | None = None
    archetype_tags: list[str] | None = None


class DeckSummary(BaseModel):
    """Lightweight deck info for list views."""

    id: UUID
    name: str
    commander_name: str
    commander_image: str | None
    commander_color_identity: list[str] = Field(default_factory=list)
    bracket: int | None
    stage: str
    card_count: int
    created_at: datetime
    updated_at: datetime


class DeckResponse(BaseModel):
    """Full deck metadata."""

    id: UUID
    name: str
    description: str | None
    bracket: int | None
    stage: str
    commander_id: UUID
    partner_id: UUID | None
    owner_email: str | None
    created_at: datetime
    updated_at: datetime
    stage_targets: dict[str, int] = Field(default_factory=dict)
    suggestion_collection_ids: list[UUID] = Field(default_factory=list)
    archetype_tags: list[str] = Field(default_factory=list)


class DeckCardItem(BaseModel):
    """A single card within a deck, with full card info."""

    deck_card_id: UUID
    card_id: UUID
    scryfall_id: UUID
    name: str
    mana_cost: str | None
    cmc: Decimal | None
    type_line: str | None
    oracle_text: str | None
    color_identity: list[str]
    image_uri: str | None
    rarity: str | None
    quantity: int
    categories: list[str] = Field(default_factory=list)
    added_by: str
    ai_reasoning: str | None
    qualifying_stages: list[str] = Field(default_factory=list)
    role_reasons: dict[str, list[str]] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    edhrec_tags: list[str] = Field(default_factory=list)
    mtgjson_tags: list[str] = Field(default_factory=list)
    power: int | None = None
    price_eur_cents: int | None = None
    owned_in: list[CollectionMembership] = Field(default_factory=list)
    game_changer: bool = False


class CommanderCardSummary(BaseModel):
    """Minimal commander/partner card fields needed for the detail-page preview
    and the goldfish sim. ``cmc``, ``power``, and ``tags`` are sim inputs.
    """

    id: UUID
    name: str
    mana_cost: str | None = None
    cmc: Decimal | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    image_uri: str | None = None
    color_identity: list[str] = Field(default_factory=list)
    power: int | None = None
    tags: list[str] = Field(default_factory=list)
    edhrec_tags: list[str] = Field(default_factory=list)
    mtgjson_tags: list[str] = Field(default_factory=list)
    game_changer: bool = False


class DeckDetailResponse(BaseModel):
    """Deck metadata plus all cards."""

    id: UUID
    name: str
    description: str | None
    bracket: int | None
    stage: str
    commander_id: UUID
    partner_id: UUID | None
    commander_color_identity: list[str] = Field(default_factory=list)
    commander_card: CommanderCardSummary | None = None
    partner_card: CommanderCardSummary | None = None
    owner_email: str | None
    created_at: datetime
    updated_at: datetime
    stage_targets: dict[str, int] = Field(default_factory=dict)
    suggestion_collection_ids: list[UUID] = Field(default_factory=list)
    archetype_tags: list[str] = Field(default_factory=list)
    mana_curve: DeckManaCurve | None = None
    cards: list[DeckCardItem]


class DeckCardAdd(BaseModel):
    """Request body for adding a card to a deck."""

    card_scryfall_id: UUID
    quantity: int = Field(default=1, ge=1)
    categories: list[str] = Field(default_factory=list)
    added_by: str = Field(default="user", pattern="^(user|ai)$")
    ai_reasoning: str | None = None


class DeckCardResponse(BaseModel):
    """Response for a card added to a deck."""

    deck_card_id: UUID
    deck_id: UUID
    card_id: UUID
    scryfall_id: UUID
    name: str
    quantity: int
    categories: list[str]
    added_by: str


class DeckImportRequest(BaseModel):
    """Request body for importing a deck from a pasted deck list."""

    deck_list: str = Field(min_length=1, max_length=50000)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    bracket: int = Field(default=3, ge=1, le=5)


class DeckUrlImportRequest(BaseModel):
    """Request body for importing a deck from a Moxfield/Archidekt URL."""

    url: AnyHttpUrl
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    bracket: int = Field(default=3, ge=1, le=5)


class DeckImportResponse(BaseModel):
    """Response from a deck import operation."""

    deck: DeckResponse
    imported_count: int
    unresolved: list[str]
    color_violations: list[str]
    suggested_archetype_tags: list[str] = Field(default_factory=list)
