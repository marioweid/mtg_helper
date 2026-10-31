"""Explicit contracts for the default-off commander-only Discover pilot."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from mtg_helper.services.recommendations.discovery import StrictModel
from mtg_helper.services.recommendations.pipeline import LiteralQuery
from mtg_helper.services.recommendations.refinement import KeyedAssessment, RuleQuery
from mtg_helper.services.recommendations.strategy import StrategyChoice
from mtg_helper.services.recommendations.term_queries import StrategyQuery, validate_queries


class StrategyDraftRequest(StrictModel):
    request_key: UUID
    reuse_latest: bool = False


class GenerateRequest(StrictModel):
    request_key: UUID
    goal: str = Field(min_length=1, max_length=1000)
    constraint: LiteralQuery | None = None
    excluded_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("goal")
    @classmethod
    def nonblank_goal(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a nonblank commander-only goal")
        return value.strip()


class PreviewRuleQuery(RuleQuery):
    cursor: str | None = Field(max_length=1000)


class QueryPreview(StrictModel):
    query: LiteralQuery | None = None
    rule_query: PreviewRuleQuery | None = None
    name: str = Field(default="", max_length=150)
    snapshot_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    rules_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    cursor: str | None = Field(default=None, max_length=1000)
    limit: int = Field(default=20, ge=1, le=50)


class CandidateView(BaseModel):
    oracle_id: UUID
    facts: dict[str, Any]
    image_uri: str | None = None
    state: Literal["unassessed", "assessed", "failed"] = "unassessed"
    assessment: KeyedAssessment | None = None
    evidence_errors: list[str] = Field(default_factory=list)
    recommended: bool = False
    excluded: bool = False


class RunView(BaseModel):
    id: UUID
    status: Literal["running", "completed", "failed", "interrupted", "unknown"]
    phase: str
    goal: str
    created_at: datetime
    source_hash: str
    rules_hash: str
    profile: str
    error: str | None = None
    stale: bool = False
    candidates: list[CandidateView] = Field(default_factory=list)
    strategies: list[StrategyChoice] = Field(default_factory=list)
    known_cost_microusd: int = 0
    held_microusd: int = 0


class QueryPage(BaseModel):
    rules_hash: str
    snapshot_hash: str
    total: int
    next_cursor: str | None = None
    cards: list[CandidateView] = Field(default_factory=list)
    rule_results: dict[str, Any] | None = None


class PilotFeedback(StrictModel):
    oracle_id: UUID
    verdict: Literal["useful", "incorrect", "uncertain"]
    note: str = Field(default="", max_length=1000)


class DiscoverStrategySave(StrictModel):
    """Editable saved intent with alternative grouped source searches, not a card taxonomy."""

    prose: str = Field(min_length=1, max_length=2000)
    queries: list[StrategyQuery] = Field(default_factory=list, max_length=6)
    revision: UUID | None = None

    @field_validator("prose")
    @classmethod
    def nonblank_prose(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a nonblank strategy")
        return value.strip()

    @field_validator("queries")
    @classmethod
    def bounded_queries(cls, values: list[StrategyQuery]) -> list[StrategyQuery]:
        validate_queries(values, limit=40)
        return values


class DiscoverStrategy(BaseModel):
    prose: str
    queries: list[StrategyQuery] = Field(default_factory=list)
    revision: UUID
    updated_at: datetime
    needs_review: bool = False


class DiscoverSourceStatus(BaseModel):
    status: Literal["ready", "stale", "unavailable", "mismatched"]
    card_updated_at: datetime | None = None
    tag_updated_at: datetime | None = None
    warning: str | None = None


class StrategyMatchEvidence(BaseModel):
    query_purpose: str
    criterion_type: Literal["oracle_tag", "printed_keyword"]
    criterion_id: UUID | None = None
    criterion_label: str
    matched_tag_id: UUID | None = None
    matched_tag_label: str | None = None
    relation: Literal["direct", "descendant", "keyword"]


class StrategyMatch(BaseModel):
    oracle_id: UUID
    name: str
    image_uri: str | None = None
    mana_cost: str | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    keywords: list[str] = Field(default_factory=list)
    match_count: int
    global_popularity_rank: int | None
    evidence: list[StrategyMatchEvidence]


class DiscoverMatches(BaseModel):
    status: Literal["ready", "stale", "setup_needed", "unavailable", "mismatched"]
    source: DiscoverSourceStatus
    strategy: DiscoverStrategy | None = None
    cards: list[StrategyMatch] = Field(default_factory=list)
    next_cursor: str | None = None
    total: int = 0


class DiscoverTerms(BaseModel):
    oracle_tags: list[dict[str, Any]] = Field(default_factory=list)
    printed_keywords: list[str] = Field(default_factory=list)


class TermSuggestionRequest(StrictModel):
    """An idempotent, explicit request for editable catalog terms."""

    request_key: UUID
    prose: str = Field(min_length=1, max_length=2000)
    strategy_revision: UUID | None = None
    reuse_latest: bool = False

    @field_validator("prose")
    @classmethod
    def nonblank_suggestion_prose(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a nonblank strategy before requesting source terms")
        return value.strip()


class TermSuggestionRun(BaseModel):
    id: UUID
    status: Literal["running", "completed", "failed", "interrupted", "unknown"]
    error: str | None = None
    queries: list[StrategyQuery] = Field(default_factory=list)
    strategy_revision: UUID | None = None
    source_hash: str | None = None


class DiscoverSetup(BaseModel):
    """Recover applicable assistance without starting or repeating model requests."""

    draft: RunView | None = None
    suggestion: TermSuggestionRun | None = None
    prose: str | None = None
