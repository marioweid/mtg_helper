"""Models for commander-specific card-frequency recommendations."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from mtg_helper.models.ai import CollectionMembership

TopPickSource = Literal["combined", "moxfield", "archidekt"]


class TopPickSourceSummary(BaseModel):
    """Status and sample metadata for one recommendation source."""

    source: Literal["moxfield", "archidekt"]
    deck_count: int = 0
    fetched_at: datetime | None = None
    stale: bool = False
    error: str | None = None


class TopPickCard(BaseModel):
    """One commonly played card with transparent per-source evidence."""

    card_id: UUID
    scryfall_id: UUID
    oracle_id: UUID | None = None
    name: str
    mana_cost: str | None
    type_line: str | None
    image_uri: str | None
    price_eur_cents: int | None = None
    combined_score: float = 0.0
    moxfield_count: int = 0
    moxfield_sample_size: int = 0
    moxfield_rate: float = 0.0
    archidekt_count: int = 0
    archidekt_sample_size: int = 0
    archidekt_rate: float = 0.0
    physical_quantity: int = 0
    plan_direction: Literal["addition", "cut"] | None = None
    planned_quantity: int = 0
    owned_in: list[CollectionMembership] = Field(default_factory=list)


class TopPicksResponse(BaseModel):
    """Merged commander evidence and source health for one deck."""

    commander_name: str
    source: TopPickSource
    sources: list[TopPickSourceSummary] = Field(default_factory=list)
    picks: list[TopPickCard] = Field(default_factory=list)
