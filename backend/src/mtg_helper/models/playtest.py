"""Pydantic models for the goldfish playtest simulation endpoint."""

from pydantic import BaseModel, Field


class PlaytestSimulateRequest(BaseModel):
    """Request body for the goldfish sim.

    Defaults are tuned for interactive use — 1000 trials run in well under a
    second on a typical deck and give stable averages.
    """

    trials: int = Field(default=1000, ge=1, le=10000)
    turns: int = Field(default=4, ge=1, le=10)
    on_the_play: bool = Field(default=True)
    max_mulligans: int = Field(default=3, ge=0, le=6)
    seed: int | None = Field(default=None, ge=0)


class TurnStat(BaseModel):
    """Aggregates for a single turn across all trials."""

    turn: int
    avg_lands_in_play: float
    avg_mana_available: float
    avg_spells_cast_cumulative: float
    pct_land_drop: float
    pct_cast_any: float


class PlaytestStats(BaseModel):
    """Aggregate output of the goldfish sim across trials."""

    trials: int
    turns: int
    on_the_play: bool
    avg_mulligans: float
    mulligan_distribution: list[int]
    avg_total_spells_cast: float
    per_turn: list[TurnStat]
