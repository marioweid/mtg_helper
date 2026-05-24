"""Pydantic models for the deck optimizer endpoint."""

from uuid import UUID

from pydantic import BaseModel, Field

from mtg_helper.models.playtest import PlaytestSimulateRequest, PlaytestStats


class OptimizeRequest(BaseModel):
    """Request body for an optimization round.

    ``max_price_cents`` caps the price of every candidate the optimizer
    considers (per-swap), so the user can constrain the search to budget
    cards. ``max_swaps`` bounds the iterative loop.
    """

    sim: PlaytestSimulateRequest = Field(default_factory=PlaytestSimulateRequest)
    max_price_cents: int | None = Field(default=None, gt=0)
    max_swaps: int = Field(default=3, ge=1, le=5)


class ProposedSwap(BaseModel):
    """A single swap the optimizer wants to apply: remove ``out`` and add ``in``."""

    out_card_id: UUID
    out_scryfall_id: UUID
    out_card_name: str
    in_scryfall_id: UUID
    in_card_name: str
    reason: str
    score_delta: float
    price_delta_cents: int | None


class OptimizationProposal(BaseModel):
    """Result of an optimization round — baseline vs. final stats and the
    swaps proposed to get from one to the other.
    """

    baseline_stats: PlaytestStats
    final_stats: PlaytestStats
    swaps: list[ProposedSwap] = Field(default_factory=list)
    total_score_delta: float = 0.0
    total_price_delta_cents: int | None = None
