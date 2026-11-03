"""Typed contracts for saved Deck Tutor guides."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

TutorMode = Literal["commander", "cedh"]
TutorRunStatus = Literal["running", "succeeded", "failed", "interrupted", "superseded"]
# Align detailed saved prose with Tutor's 16,000-token response budget without silent truncation.
MAX_TUTOR_GUIDE_CONTENT_CHARS = 64_000


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
    mana_cost: str | None = None
    cmc: float | None = None
    color_identity: list[str] = Field(default_factory=list)
    legalities: dict[str, str] = Field(default_factory=dict)
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


class TutorOpeningHandOutput(BaseModel):
    """One model-produced hand before its required output field supplies the decision."""

    cards: list[str] = Field(min_length=7, max_length=7)
    explanation: str = Field(min_length=1, max_length=1200)


class TutorGuideStructuredOutput(BaseModel):
    """Model-only shape that requires every worked-hand decision exactly once."""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=MAX_TUTOR_GUIDE_CONTENT_CHARS)
    keep: TutorOpeningHandOutput
    mulligan: TutorOpeningHandOutput
    context_dependent: TutorOpeningHandOutput

    def to_draft(self) -> "TutorGuideDraft":
        """Convert named model fields to the persisted, rendered worked-hand list."""
        return TutorGuideDraft(
            title=self.title,
            content=self.content,
            opening_hands=[
                TutorOpeningHand(decision="keep", **self.keep.model_dump()),
                TutorOpeningHand(decision="mulligan", **self.mulligan.model_dump()),
                TutorOpeningHand(
                    decision="context-dependent", **self.context_dependent.model_dump()
                ),
            ],
        )


class TutorGuideDraft(BaseModel):
    """The teacher's bounded, readable guide output."""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=MAX_TUTOR_GUIDE_CONTENT_CHARS)
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
