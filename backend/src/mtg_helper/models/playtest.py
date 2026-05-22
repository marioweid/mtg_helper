"""Pydantic models for the goldfish playtest simulation endpoint."""

from enum import StrEnum

from pydantic import BaseModel, Field


class EngineClass(StrEnum):
    """Commander engine archetypes. Each class has a fixed per-turn yield that
    fires once the commander is in play. Auto-classified from commander tags.
    """

    NONE = "none"
    TOKEN_GENERATOR = "token_generator"
    COUNTER_DISTRIBUTOR = "counter_distributor"
    SAC_PAYOFF = "sac_payoff"
    RAMP_ENGINE = "ramp_engine"
    DRAW_ENGINE = "draw_engine"


class ManaEngineThreshold(BaseModel):
    """Big-mana / X-spell engine threshold. Hit when mana pool is full enough
    to dump and you still have cards to spend it on.
    """

    min_mana: int = Field(default=12, ge=0)
    min_hand: int = Field(default=3, ge=0)


class BoardStateThreshold(BaseModel):
    """Go-wide / token / tribal threshold. Hit by either compounding power or
    raw creature count — whichever the deck is built around.
    """

    min_power: int = Field(default=30, ge=0)
    min_creatures: int = Field(default=10, ge=0)


class VelocityThreshold(BaseModel):
    """Spellslinger / storm / enchantress threshold. Hit when a single turn
    chains a lot of spells without emptying the hand.
    """

    min_spells_per_turn: int = Field(default=5, ge=0)
    min_hand: int = Field(default=4, ge=0)


class EngineThresholdConfig(BaseModel):
    """Per-archetype thresholds. Defaults match the user's spec."""

    mana_engine: ManaEngineThreshold = Field(default_factory=ManaEngineThreshold)
    board_state: BoardStateThreshold = Field(default_factory=BoardStateThreshold)
    velocity: VelocityThreshold = Field(default_factory=VelocityThreshold)


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
    thresholds: EngineThresholdConfig | None = None


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
    avg_creatures_on_board: float
    avg_total_power: float
    avg_cards_in_hand: float
    pct_mana_engine_hit_cum: float
    pct_board_state_hit_cum: float
    pct_velocity_hit_cum: float
    pct_any_threshold_hit_cum: float


class EngineThresholdSummary(BaseModel):
    """Aggregate threshold-crossing stats across all trials. ``avg_first_*``
    uses ``turns + 1`` as a sentinel for trials that never crossed.
    """

    avg_first_mana_engine_turn: float
    avg_first_board_state_turn: float
    avg_first_velocity_turn: float
    avg_first_any_threshold_turn: float
    pct_ever_mana_engine: float
    pct_ever_board_state: float
    pct_ever_velocity: float
    pct_ever_any: float


class OpeningHandStats(BaseModel):
    """Distribution of opening-hand land counts before any mulligan decision."""

    pct_screwed_mull: float
    pct_balanced: float
    pct_flood_mull: float
    pct_kept_7: float
    pct_kept_6: float
    pct_kept_5: float
    pct_kept_le4: float


class CommanderStats(BaseModel):
    """Per-commander cast-turn stats. ``avg_cast_turn`` uses ``turns + 1`` as a
    sentinel for trials where the commander was never cast.
    """

    name: str
    avg_cast_turn: float
    pct_ever_cast: float


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
    engine_thresholds: EngineThresholdSummary
    commander: CommanderStats | None = None
    partner: CommanderStats | None = None
    engine_class: EngineClass = EngineClass.NONE
    per_turn: list[TurnStat]
