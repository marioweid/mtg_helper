"""Pydantic models for the onboarding quickstart endpoint."""

from uuid import UUID

from pydantic import BaseModel, Field

from mtg_helper.models.decks import DeckResponse


class QuickstartRequest(BaseModel):
    """Request body for ``POST /onboarding/quickstart``."""

    commander_scryfall_id: UUID
    partner_scryfall_id: UUID | None = None
    bracket: int = Field(default=2, ge=1, le=4)
    max_price_cents: int | None = Field(default=None, gt=0)
    min_price_cents: int | None = Field(default=None, ge=0)
    name: str | None = Field(default=None, max_length=200)


class QuickstartStageResult(BaseModel):
    """Per-stage outcome of the quickstart pipeline."""

    stage: str
    target: int
    accepted: int


class QuickstartResponse(BaseModel):
    """Response from a successful quickstart."""

    deck: DeckResponse
    stages: list[QuickstartStageResult]
