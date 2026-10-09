"""Explicit contracts for the default-off commander-only Discover pilot."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from mtg_helper.services.recommendations.discovery import StrictModel
from mtg_helper.services.recommendations.pipeline import LiteralQuery
from mtg_helper.services.recommendations.refinement import KeyedAssessment, RuleQuery


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
    known_cost_microusd: int = 0
    held_microusd: int = 0


class DiscoveryStatus(BaseModel):
    ready: bool = False
    reason: str | None = None
    source_hash: str | None = None
    rules_hash: str | None = None
    catalog_updated_at: datetime | None = None
    goal_seed: str = ""
    run: RunView | None = None
    run_cap_microusd: int = 100_000
    daily_cap_microusd: int = 1_000_000
    reserved_microusd: int = 67_750
    maximum_calls: int = 3


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
