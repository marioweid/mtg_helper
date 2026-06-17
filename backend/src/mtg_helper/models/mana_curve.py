"""Models for current and recommended Commander mana curves."""

from typing import Literal

from pydantic import BaseModel, Field

CurveSource = Literal["moxfield", "fallback"]
CurveConfidence = Literal["high", "fallback"]


class ManaCurveRecommendation(BaseModel):
    """Recommended non-land, non-commander mana curve."""

    source: CurveSource
    deck_count: int = 0
    confidence: CurveConfidence
    buckets: dict[str, int] = Field(default_factory=dict)


class DeckManaCurve(BaseModel):
    """Current deck curve plus recommended targets and deltas."""

    current: dict[str, int] = Field(default_factory=dict)
    recommended: ManaCurveRecommendation
    delta: dict[str, int] = Field(default_factory=dict)
    progress_delta: dict[str, int] = Field(default_factory=dict)
