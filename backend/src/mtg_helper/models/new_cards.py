"""Transparent, source-grounded New Cards response models."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NewCardFace(BaseModel):
    name: str
    mana_cost: str | None = None
    type_line: str | None = None
    oracle_text: str = ""
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    defense: str | None = None


class CardFacts(NewCardFace):
    oracle_id: UUID
    color_identity: list[str] = Field(default_factory=list)
    commander_legality: str = "not_legal"
    layout: str = "normal"
    faces: list[NewCardFace] = Field(default_factory=list)
    game_changer: bool = False


class TagMatch(BaseModel):
    """One direct or descendant Scryfall tag explanation."""

    commander_tag_id: UUID
    commander_tag_label: str
    candidate_tag_id: UUID
    candidate_tag_label: str
    relation: Literal["direct", "descendant"]


class NewCardMatch(NewCardFace):
    oracle_id: UUID
    card_id: UUID
    scryfall_id: UUID
    faces: list[NewCardFace] = Field(default_factory=list)
    image_uri: str | None
    scryfall_uri: str
    released_at: date
    expires_at: date
    price_eur_cents: int | None
    matching_tag_count: int
    tag_matches: list[TagMatch]


class NewCardsResponse(BaseModel):
    """Read-only local Scryfall tag matches for one Commander-Konstellation."""

    status: Literal["ready", "unavailable", "source_stale", "source_mismatched"] = "ready"
    catalog_updated_at: datetime | None = None
    tag_updated_at: datetime | None = None
    stale: bool = False
    eligible_count: int = 0
    dismissed_count: int = 0
    error: str | None = None
    matches: list[NewCardMatch] = Field(default_factory=list)
