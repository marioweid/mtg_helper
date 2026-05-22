"""Pydantic models for the goldfish playtest simulation endpoint."""

from typing import Literal

from pydantic import BaseModel, Field

_COLORS: tuple[str, ...] = ("W", "U", "B", "R", "G", "C")


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
    avg_color_dead_cards: float
    avg_interaction_in_hand: float
    avg_cards_drawn_extra: float
    avg_selection_events: float
    avg_tutors_cast: float
    avg_cards_in_hand: float
    lands_p25: float
    lands_p50: float
    lands_p75: float
    mana_p25: float
    mana_p50: float
    mana_p75: float
    avg_mana_unspent: float
    avg_hand_lands: float
    avg_hand_ramp: float
    avg_hand_draw: float
    avg_hand_interaction: float
    avg_hand_tutors: float
    avg_hand_other: float


class OpeningHandStats(BaseModel):
    """Distribution of opening-hand land counts before any mulligan decision."""

    pct_screwed_mull: float
    pct_balanced: float
    pct_flood_mull: float
    pct_kept_7: float
    pct_kept_6: float
    pct_kept_5: float
    pct_kept_le4: float


class ColorScrewStats(BaseModel):
    """Color-pip screw analysis. Per-trial classification: a trial is
    color-screwed when at any turn ≥ 3 the hand contains a spell whose total
    mana value is affordable from available sources, but whose colored pips
    cannot be paid. Per-color rates report how often each specific color was
    the missing pip across the sim.
    """

    pct_color_screw: float
    shortages_by_color: dict[str, float] = Field(default_factory=dict)


class CommanderStats(BaseModel):
    """Per-commander cast-turn stats. ``avg_cast_turn`` uses ``turns + 1`` as a
    sentinel for trials where the commander was never cast.
    """

    name: str
    avg_cast_turn: float
    pct_ever_cast: float


class CardSimStat(BaseModel):
    """Per-card simulation outcomes. One entry per distinct card name in the
    deck. ``avg_first_cast_turn`` uses ``turns + 1`` as a sentinel for trials
    where the card was never cast.
    """

    name: str
    quantity_in_deck: int
    pct_drawn_by_end: float
    avg_first_cast_turn: float
    pct_ever_cast: float
    pct_stuck_in_hand_at_end: float


class StuckCard(BaseModel):
    """Top dead-in-hand offender with pre-classified blocker reason. The LLM
    consumes these as actionable swap candidates.
    """

    name: str
    cost: str | None
    pct_stuck: float
    blocker: Literal["mana", "colors", "never_drawn"]


class UnpaidCost(BaseModel):
    """An exact mana-cost string the deck repeatedly failed to pay."""

    cost: str
    pct_failed: float
    missing_colors: list[str]


class SampleTrial(BaseModel):
    """A single representative trial for narrative grounding. Three are
    selected per sim — best / median / worst by total spells cast.
    """

    bucket: Literal["best", "median", "worst"]
    mulligans: int
    commander_cast_turn: int | None
    land_turns: list[int]
    spells_cast_turns: list[tuple[int, str]]
    stuck_at_end: list[str]


class MulliganReasonStats(BaseModel):
    """Distribution of *why* mulligans were taken. Sums to 1.0 across the four
    reasons when ``total > 0``.
    """

    total: int
    low_lands: float
    high_lands: float
    no_commander_color: float
    no_early_play: float


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
    color_screw: ColorScrewStats
    commander: CommanderStats | None = None
    partner: CommanderStats | None = None
    per_card: list[CardSimStat] = Field(default_factory=list)
    top_stuck_cards: list[StuckCard] = Field(default_factory=list)
    unpaid_cost_summary: list[UnpaidCost] = Field(default_factory=list)
    sample_trials: list[SampleTrial] = Field(default_factory=list)
    cast_rate_by_cmc: dict[str, float] = Field(default_factory=dict)
    mulligan_reasons: MulliganReasonStats
    per_turn: list[TurnStat]
