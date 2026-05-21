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
    avg_mana_spent: float
    mana_utilization: float
    avg_spells_cast_cumulative: float
    pct_land_drop: float
    pct_cast_any: float
    avg_dead_cards: float
    avg_interaction_in_hand: float
    avg_cards_drawn_extra: float
    avg_selection_events: float
    avg_tutors_cast: float
    lands_p25: float
    lands_p50: float
    lands_p75: float
    mana_p25: float
    mana_p50: float
    mana_p75: float


class OpeningHandStats(BaseModel):
    """Distribution of opening-hand land counts before any mulligan decision."""

    pct_screwed_mull: float
    pct_balanced: float
    pct_flood_mull: float
    pct_kept_7: float
    pct_kept_6: float
    pct_kept_5: float
    pct_kept_le4: float


class PlaytestStats(BaseModel):
    """Aggregate output of the goldfish sim across trials."""

    trials: int
    turns: int
    on_the_play: bool
    avg_mulligans: float
    mulligan_distribution: list[int]
    avg_total_spells_cast: float
    total_spells_stddev: float
    pct_flood: float
    pct_screw: float
    avg_first_missed_land_turn: float
    opening_hand: OpeningHandStats
    per_turn: list[TurnStat]
