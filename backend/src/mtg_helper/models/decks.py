"""Pydantic models for deck requests and responses."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class DeckCreate(BaseModel):
    """Request body for creating a new deck."""

    commander_scryfall_id: UUID
    partner_scryfall_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    bracket: int = Field(default=3, ge=1, le=4)


class DeckUpdate(BaseModel):
    """Request body for updating deck metadata. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    bracket: int | None = Field(default=None, ge=1, le=4)
    stage: str | None = None


class DeckSummary(BaseModel):
    """Lightweight deck info for list views."""

    id: UUID
    name: str
    commander_name: str
    commander_image: str | None
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
    created_at: datetime
    updated_at: datetime


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
    category: str | None
    added_by: str
    ai_reasoning: str | None


class DeckDetailResponse(BaseModel):
    """Deck metadata plus all cards."""

    id: UUID
    name: str
    description: str | None
    bracket: int | None
    stage: str
    commander_id: UUID
    partner_id: UUID | None
    created_at: datetime
    updated_at: datetime
    cards: list[DeckCardItem]


class DeckCardAdd(BaseModel):
    """Request body for adding a card to a deck."""

    card_scryfall_id: UUID
    quantity: int = Field(default=1, ge=1)
    category: str | None = None
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
    category: str | None
    added_by: str
