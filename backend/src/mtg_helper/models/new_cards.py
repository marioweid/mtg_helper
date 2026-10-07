"""Public experimental discovery responses and source-grounded card facts."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NewCardFace(BaseModel):
    name: str
    mana_cost: str | None = None
    type_line: str | None = None
    oracle_text: str = ""
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    defense: str | None = None


class CardFacts(NewCardFace):
    oracle_id: UUID
    color_identity: list[str] = Field(default_factory=list)
    commander_legality: str = "not_legal"
    layout: str = "normal"
    faces: list[NewCardFace] = Field(default_factory=list)
    game_changer: bool = False


class NewCardEvidence(BaseModel):
    name: str
    quote: str


class NewCardPick(NewCardFace):
    oracle_id: UUID
    card_id: UUID
    scryfall_id: UUID
    faces: list[NewCardFace] = Field(default_factory=list)
    image_uri: str | None
    scryfall_uri: str
    released_at: date
    expires_at: date
    price_eur_cents: int | None
    label: Literal["strong", "worth_testing"]
    reason: str
    caveat: str
    required_changes: list[str]
    evidence: list[NewCardEvidence]


class NewCardsResponse(BaseModel):
    status: Literal["unavailable", "idle", "running", "error"] = "idle"
    catalog_updated_at: datetime | None = None
    analyzed_at: datetime | None = None
    stale: bool = False
    eligible_count: int = 0
    assessed_count: int = 0
    remaining_count: int = 0
    dismissed_count: int = 0
    error: str | None = None
    picks: list[NewCardPick] = Field(default_factory=list)
