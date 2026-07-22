"""Pydantic models for atomic deck revisions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DeckRevisionCreate(BaseModel):
    """Apply selected planned changes as one named deck revision."""

    title: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    plan_ids: list[UUID] = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        """Reject titles that contain only whitespace."""
        if not value.strip():
            raise ValueError("Title must not be blank")
        return value.strip()

    @field_validator("plan_ids")
    @classmethod
    def plans_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        """Prevent applying the same plan twice in one revision."""
        if len(value) != len(set(value)):
            raise ValueError("Plan IDs must be unique")
        return value


class DeckRevisionUpdate(BaseModel):
    """Edit mutable revision metadata; recorded changes remain immutable."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        """Reject whitespace-only replacement titles."""
        if value is None:
            raise ValueError("Title cannot be null")
        if not value.strip():
            raise ValueError("Title must not be blank")
        return value.strip()


class DeckRevisionChange(BaseModel):
    """Frozen record of one applied planned change."""

    card_id: UUID
    card_name: str
    direction: Literal["addition", "cut"]
    quantity: int
    categories: list[str] = Field(default_factory=list)
    added_by: Literal["user", "ai"]
    ai_reasoning: str | None
    collection_id: UUID | None
    collection_name: str | None
    plan_created_at: datetime
    plan_updated_at: datetime


class DeckRevision(BaseModel):
    """Named, immutable deck transition plus editable descriptive metadata."""

    id: UUID
    deck_id: UUID
    title: str
    note: str | None
    source: Literal["selected_plans", "single_plan"]
    before_snapshot_id: UUID
    after_snapshot_id: UUID
    created_at: datetime
    changes: list[DeckRevisionChange] = Field(default_factory=list)
