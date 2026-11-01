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


class TutorEvidence(BaseModel):
    """Frozen exact facts and explicit source gaps for one guide run."""

    commanders: list[TutorCardFact]
    cards: list[TutorCardFact]
    rules: list[TutorRuleFact] = Field(default_factory=list)
    combos: list[TutorComboFact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sources: dict[str, str | None] = Field(default_factory=dict)


class TutorGuideDraft(BaseModel):
    """The teacher's bounded, readable guide output."""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=24000)


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
