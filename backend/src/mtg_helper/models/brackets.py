"""Pydantic models for bracket validation."""

from typing import Literal

from pydantic import BaseModel

ViolationRule = Literal[
    "game_changer",
    "mass_land_destruction",
    "fast_mana",
    "infinite_combo",
    "extra_turn_chain",
]


class BracketViolation(BaseModel):
    """A single bracket rule violation for a deck."""

    rule: ViolationRule
    severity: Literal["block", "warn"]
    message: str
    cards: list[str]


class BracketValidationResponse(BaseModel):
    """Result of validating a deck against its declared bracket."""

    declared_bracket: int
    legal: bool
    violations: list[BracketViolation]
