"""Pydantic models for deck snapshots and deck comparison."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SnapshotCardItem(BaseModel):
    """A single card within a snapshot, with the card fields needed to render."""

    card_id: UUID
    scryfall_id: UUID
    name: str
    mana_cost: str | None
    cmc: Decimal | None
    type_line: str | None
    color_identity: list[str] = Field(default_factory=list)
    image_uri: str | None
    quantity: int
    categories: list[str] = Field(default_factory=list)
    added_by: str
    ai_reasoning: str | None = None


class SnapshotSummary(BaseModel):
    """List-view metadata for a deck snapshot."""

    id: UUID
    deck_id: UUID
    label: str | None
    source: Literal["manual", "auto_stage"]
    stage: str
    deck_name: str
    bracket: int | None
    card_count: int
    created_at: datetime


class SnapshotResponse(BaseModel):
    """Result of creating a snapshot."""

    id: UUID
    deck_id: UUID
    label: str | None
    source: Literal["manual", "auto_stage"]
    stage: str
    deck_name: str
    bracket: int | None
    stage_targets: dict[str, int] = Field(default_factory=dict)
    archetype_tags: list[str] = Field(default_factory=list)
    created_at: datetime


class SnapshotDetailResponse(BaseModel):
    """Full snapshot: metadata + cards."""

    id: UUID
    deck_id: UUID
    label: str | None
    source: Literal["manual", "auto_stage"]
    stage: str
    deck_name: str
    bracket: int | None
    stage_targets: dict[str, int] = Field(default_factory=dict)
    archetype_tags: list[str] = Field(default_factory=list)
    created_at: datetime
    cards: list[SnapshotCardItem]


class SnapshotCreate(BaseModel):
    """Request body for creating a manual snapshot."""

    label: str | None = Field(default=None, max_length=200)


class DiffCardInfo(BaseModel):
    """Card fields carried with a diff entry so the UI can render without a refetch."""

    card_id: UUID
    scryfall_id: UUID
    name: str
    mana_cost: str | None = None
    type_line: str | None = None
    image_uri: str | None = None
    color_identity: list[str] = Field(default_factory=list)


class DiffEntry(BaseModel):
    """One card-level diff row."""

    card: DiffCardInfo
    left_quantity: int = 0
    right_quantity: int = 0
    left_categories: list[str] = Field(default_factory=list)
    right_categories: list[str] = Field(default_factory=list)


class DeckDiff(BaseModel):
    """Bucketed diff between two card compositions."""

    added: list[DiffEntry] = Field(default_factory=list)
    removed: list[DiffEntry] = Field(default_factory=list)
    quantity_changed: list[DiffEntry] = Field(default_factory=list)
    common: list[DiffEntry] = Field(default_factory=list)


class ComparisonSideMeta(BaseModel):
    """Metadata describing one side of a comparison."""

    kind: Literal["deck", "snapshot"]
    id: UUID
    deck_id: UUID
    deck_name: str
    label: str | None = None
    stage: str
    bracket: int | None = None
    card_count: int


class DeckCompareResponse(BaseModel):
    """Result of comparing two compositions."""

    left: ComparisonSideMeta
    right: ComparisonSideMeta
    diff: DeckDiff
