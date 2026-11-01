"""Typed contracts for saved Deck Tutor guides."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

TutorMode = Literal["commander", "cedh"]
TutorRunStatus = Literal["running", "succeeded", "failed", "interrupted", "superseded"]


class TutorSetupUpdate(BaseModel):
    """Persist the explicitly selected teaching perspective."""

    mode: TutorMode


class TutorGenerateRequest(BaseModel):
    """One explicit, idempotent request to generate a Deck-Lernleitfaden."""

    request_key: UUID


class TutorCardFact(BaseModel):
    """Exact captured card fact available to a guide teacher."""

    oracle_id: UUID | None
    name: str
    quantity: int = Field(ge=1)
    type_line: str | None
    oracle_text: str | None
    faces: list["TutorCardFace"] = Field(default_factory=list)


class TutorCardFace(BaseModel):
    """One exact source face, kept separate from flattened card rules text."""

    name: str
    type_line: str | None = None
    oracle_text: str | None = None


class TutorRuleFact(BaseModel):
    """One exact, pinned Comprehensive Rules excerpt available to a guide."""

    identifier: str
    text: str


class TutorComboFact(BaseModel):
    """A source-reported current line with its required pieces and outlet."""

    identifier: str
    pieces: list[str]
    produces: list[str]
    description: str | None = None
    requirements: list["TutorLineRequirement"] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    resource_status: Literal["supported", "unverified"] = "unverified"
    outlet: str | None = None
    outlet_status: Literal["supported", "unverified"] = "unverified"


class TutorLineRequirement(BaseModel):
    """A source-reported line piece and its captured deck location."""

    name: str
    zone: Literal["command_zone", "mainboard"]


class TutorEvidence(BaseModel):
    """Frozen exact facts and explicit source gaps for one guide run."""

    commanders: list[TutorCardFact]
    cards: list[TutorCardFact]
    rules: list[TutorRuleFact] = Field(default_factory=list)
    combos: list[TutorComboFact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sources: dict[str, str | None] = Field(default_factory=dict)


class TutorOpeningHand(BaseModel):
    """One verified seven-card example drawn from the saved mainboard."""

    decision: Literal["keep", "mulligan", "context-dependent"]
    cards: list[str] = Field(min_length=7, max_length=7)
    explanation: str = Field(min_length=1, max_length=1200)


class TutorGuideDraft(BaseModel):
    """The teacher's bounded, readable guide output."""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=24000)
    opening_hands: list[TutorOpeningHand] = Field(default_factory=list, max_length=3)


class TutorRunResponse(BaseModel):
    """Persisted status and last guide artifact for the Tutor workspace."""

    id: UUID
    status: TutorRunStatus
    mode: TutorMode
    current: bool
    guide: TutorGuideDraft | None = None
    evidence: TutorEvidence | None = None
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class TutorStateResponse(BaseModel):
    """Owner-scoped Tutor setup and the latest saved guide without side effects."""

    mode: TutorMode | None = None
    latest_run: TutorRunResponse | None = None
    last_successful_run: TutorRunResponse | None = None
