"""Pydantic models for deck feedback requests and responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    """Request body for submitting card feedback."""

    card_scryfall_id: UUID
    feedback: Literal["up", "down", "reject"]
    reason: str | None = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    """Feedback record returned from the API."""

    id: UUID
    deck_id: UUID
    card_id: UUID
    card_name: str
    feedback: str
    reason: str | None
    created_at: datetime
