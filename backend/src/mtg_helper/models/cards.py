"""Pydantic models for card requests and responses."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CardResponse(BaseModel):
    """Full card data returned from the API."""

    id: UUID
    scryfall_id: UUID
    oracle_id: UUID | None
    name: str
    mana_cost: str | None
    cmc: Decimal | None
    type_line: str | None
    oracle_text: str | None
    color_identity: list[str]
    colors: list[str]
    keywords: list[str]
    power: str | None
    toughness: str | None
    legalities: dict
    image_uri: str | None
    prices: dict
    rarity: str | None
    set_code: str | None
    released_at: date | None
    edhrec_rank: int | None


class CardSearchParams(BaseModel):
    """Query parameters for card search."""

    q: str | None = None
    color_identity: str | None = None
    type: str | None = None
    cmc_min: Decimal | None = None
    cmc_max: Decimal | None = None
    keywords: str | None = None
    commander_legal: bool = True
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
