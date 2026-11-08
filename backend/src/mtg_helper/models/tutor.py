"""Typed contracts for saved Deck Tutor guides."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

TutorMode = Literal["commander", "cedh"]
TutorRunStatus = Literal["running", "succeeded", "failed", "interrupted", "superseded"]
TutorTurnStatus = Literal["running", "succeeded", "failed", "interrupted", "superseded"]
TutorHandoffStatus = Literal["none", "pending", "running", "ready", "failed"]


class TutorSetupUpdate(BaseModel):
    """Persist the explicitly selected teaching perspective."""

    mode: TutorMode


class TutorGenerateRequest(BaseModel):
    """One explicit, idempotent request to generate a Deck-Lernleitfaden."""

    request_key: UUID


class TutorQuestionRequest(BaseModel):
    """One explicit question; the server alone supplies conversation history."""

    request_key: UUID
    question: str = Field(min_length=1, max_length=8_000)
    card_name: str | None = Field(default=None, max_length=300)


class TutorAnswerDraft(BaseModel):
    """The specialized teacher's answer to one current-list question."""

    content: str = Field(min_length=1)


class TutorHandoffDraft(BaseModel):
    """A bounded, untrusted Lernübergabe for a later teaching context."""

    content: str = Field(min_length=1, max_length=6_000)


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


class TutorReferenceDifference(BaseModel):
    """One canonical card quantity in the frozen reference and current Lerndeck."""

    name: str
    oracle_id: UUID | None
    reference_quantity: int = Field(ge=0)
    actual_quantity: int = Field(ge=0)


class TutorReferenceDifferences(BaseModel):
    """Actual-list changes relative to a Referenzdeck, never proposed membership."""

    missing: list[TutorReferenceDifference] = Field(default_factory=list)
    added: list[TutorReferenceDifference] = Field(default_factory=list)


class TutorReference(BaseModel):
    """An immutable, self-contained Referenzdeck captured by its owner."""

    version: UUID
    source: Literal["current_deck", "owned_deck", "pasted_text"]
    source_deck_id: UUID | None = None
    source_name: str | None = None
    source_url: str | None = None
    captured_at: datetime
    commanders: list[TutorCardFact]
    cards: list[TutorCardFact]


class TutorReferenceRequest(BaseModel):
    """One source selection used only to prepare a reference preview."""

    source: Literal["current", "owned", "pasted"]
    source_deck_id: UUID | None = None
    text: str | None = Field(default=None, max_length=65_536)
    source_url: str | None = Field(default=None, max_length=2_048)


class TutorReferenceConfirm(BaseModel):
    """Confirm the exact server-captured preview, rather than client-supplied facts."""

    preview_id: UUID


class TutorReferencePreviewResponse(BaseModel):
    """A private candidate awaiting explicit confirmation or cancellation."""

    preview_id: UUID
    reference: TutorReference
    differences: TutorReferenceDifferences


class TutorEvidence(BaseModel):
    """Frozen exact facts and explicit source gaps for one guide run."""

    commanders: list[TutorCardFact]
    cards: list[TutorCardFact]
    rules: list[TutorRuleFact] = Field(default_factory=list)
    combos: list[TutorComboFact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sources: dict[str, str | None] = Field(default_factory=dict)
    reference: TutorReference | None = None
    reference_differences: TutorReferenceDifferences | None = None
    optional_suggestions: list[TutorCardFact] = Field(default_factory=list)


class TutorOpeningHand(BaseModel):
    """One verified seven-card example drawn from the saved mainboard."""

    decision: Literal["keep", "mulligan", "context-dependent"]
    cards: list[str] = Field(min_length=7, max_length=7)
    explanation: str = Field(min_length=1)


class TutorOpeningHandOutput(BaseModel):
    """One model-produced hand before its required output field supplies the decision."""

    cards: list[str] = Field(min_length=7, max_length=7)
    explanation: str = Field(min_length=1)


class TutorGuideStructuredOutput(BaseModel):
    """Model-only shape that requires every worked-hand decision exactly once."""

    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
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
    """The teacher's readable guide output."""

    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
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
    reference: TutorReference | None = None
    reference_differences: TutorReferenceDifferences | None = None
    current_cards: list[TutorCardFact] = Field(default_factory=list)


class TutorTurnContext(BaseModel):
    """One successful saved turn admitted to bounded model context."""

    question: str
    answer: str


class TutorTurnResponse(BaseModel):
    """A full original user question and its durable answer status."""

    id: UUID
    question: str
    answer: str | None = None
    card_name: str | None = None
    status: TutorTurnStatus
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class TutorChapterResponse(BaseModel):
    """One chronological Gesprächskapitel with its frozen teaching context."""

    id: UUID
    sequence: int
    mode: TutorMode
    teaching_hash: str
    composition_hash: str
    manifest: dict[str, object]
    current: bool
    handoff: str | None = None
    handoff_status: TutorHandoffStatus
    handoff_error: str | None = None
    turns: list[TutorTurnResponse] = Field(default_factory=list)
    created_at: datetime


class TutorConversationResponse(BaseModel):
    """The complete owner-scoped transcript, including read-only archives."""

    chapters: list[TutorChapterResponse] = Field(default_factory=list)
