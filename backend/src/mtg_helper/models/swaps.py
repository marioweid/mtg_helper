"""Pydantic models for budget swap endpoints."""

from uuid import UUID

from pydantic import BaseModel, Field

from mtg_helper.models.ai import CardSuggestion


class SwapRequest(BaseModel):
    """Request body for finding budget swaps for a deck card."""

    max_price_cents: int | None = Field(default=None, gt=0)
    limit: int = Field(default=5, ge=1, le=20)


class SwapCandidate(CardSuggestion):
    """A cheaper alternative to a source card, with similarity scoring.

    ``price_delta_cents`` is negative when the candidate is cheaper.
    ``function_loss_pct`` is 0 (perfect substitute) to 100 (nothing in common).
    """

    price_delta_cents: int
    function_loss_pct: int = Field(ge=0, le=100)
    similarity_breakdown: dict[str, float] = Field(default_factory=dict)


class SwapResponse(BaseModel):
    """Response from a budget-swap lookup."""

    source_card_id: UUID
    source_price_cents: int | None
    candidates: list[SwapCandidate] = Field(default_factory=list)
