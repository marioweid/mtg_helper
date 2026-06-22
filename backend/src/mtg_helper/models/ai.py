"""Pydantic models for AI deck building endpoints."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class BuildRequest(BaseModel):
    """Request body for the staged deck build."""

    stage: str | None = None
    target: int | None = Field(default=None, ge=1, le=99)
    offset: int = Field(default=0, ge=0, le=1000)
    exclude: list[str] | None = Field(default=None, max_length=200)
    collection_ids: list[UUID] | None = None
    max_price_cents: int | None = Field(default=None, gt=0)
    min_price_cents: int | None = Field(default=None, ge=0)
    card_types: list[str] | None = Field(default=None, max_length=10)
    subtypes: list[str] | None = Field(default=None, max_length=10)


class CollectionMembership(BaseModel):
    """A collection that owns the suggested card."""

    id: UUID
    name: str


class CardSuggestion(BaseModel):
    """A single suggested card with reasoning."""

    scryfall_id: UUID
    name: str
    mana_cost: str | None
    type_line: str | None
    image_uri: str | None
    oracle_text: str | None = None
    power: str | None = None
    toughness: str | None = None
    rarity: str | None = None
    cmc: float | None = None
    color_identity: list[str] = Field(default_factory=list)
    category: str
    reasoning: str
    synergies: list[str]
    highlight_reasons: list[str] | None = None
    price_eur_cents: int | None = None
    owned_in: list[CollectionMembership] = Field(default_factory=list)
    qualifying_stages: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class BuildResponse(BaseModel):
    """Response from a staged deck build step."""

    stage: str
    stage_number: int
    total_stages: int
    suggestions: list[CardSuggestion]
    unresolved: list[str]


class SuggestRequest(BaseModel):
    """Request body for free-form card suggestions."""

    prompt: str = Field(min_length=1, max_length=500)
    count: int = Field(default=10, ge=1, le=25)
    collection_ids: list[UUID] | None = None
    max_price_cents: int | None = Field(default=None, gt=0)
    min_price_cents: int | None = Field(default=None, ge=0)
    card_types: list[str] | None = Field(default=None, max_length=10)
    subtypes: list[str] | None = Field(default=None, max_length=10)


class SuggestResponse(BaseModel):
    """Response from a card suggestion request."""

    suggestions: list[CardSuggestion]
    unresolved: list[str]


class DescribeMessage(BaseModel):
    """A single turn in the description agent conversation."""

    role: str
    content: str = Field(max_length=2000)


class DescribeRequest(BaseModel):
    """Request body for the deck description agent."""

    commander_scryfall_id: UUID
    partner_scryfall_id: UUID | None = None
    bracket: int = Field(default=3, ge=1, le=5)
    history: list[DescribeMessage] = Field(default_factory=list, max_length=24)
    message: str = Field(default="", max_length=2000)


class DescribeResponse(BaseModel):
    """Response from the deck description agent."""

    reply: str
    done: bool
    description: str | None = None
    suggested_name: str | None = None
    stage_targets: dict[str, int] | None = None


class KeywordExtractRequest(BaseModel):
    """Request body for the keyword-extracting deck agent.

    Mirrors ``DescribeRequest`` but the agent is asked to converge on a
    structured set of archetype keywords (Moxfield-style: ``voltron``,
    ``aristocrats``, ``squirrel_tribal``) rather than a free-form description.
    """

    commander_scryfall_id: UUID
    partner_scryfall_id: UUID | None = None
    bracket: int = Field(default=3, ge=1, le=5)
    history: list[DescribeMessage] = Field(default_factory=list, max_length=24)
    message: str = Field(default="", max_length=2000)


class RiskyCard(BaseModel):
    """A non-land card whose colored pip requirement exceeds available sources.

    ``sources_required`` is the Karsten heuristic for the card's CMC turn and
    solid pip count in the given color.
    """

    card_id: UUID
    name: str
    mana_cost: str | None
    cmc: int = Field(ge=0)
    color: str = Field(pattern="^[WUBRG]$")
    pips_required: int = Field(ge=1)
    sources_available: int = Field(ge=0)
    sources_required: int = Field(ge=0)


class ColorStatus(BaseModel):
    """Per-color mana-base health for a deck."""

    color: str = Field(pattern="^[WUBRG]$")
    pip_count: float = Field(ge=0.0)
    source_count: int = Field(ge=0)
    target: int = Field(ge=0)
    deficit: int = Field(ge=0)
    turn_demand: int = Field(default=0, ge=0)
    turn_deficit: int = Field(default=0, ge=0)
    risky_cards: list[RiskyCard] = Field(default_factory=list)


class ManaBaseReport(BaseModel):
    """Mana-base analysis for a deck — per-color requirements vs sources."""

    total_lands: int = Field(ge=0)
    total_colored_pips: float = Field(ge=0.0)
    colors: list[ColorStatus] = Field(default_factory=list)
    avg_cmc: float = Field(default=0.0, ge=0.0)
    ramp_count: int = Field(default=0, ge=0)
    recommended_lands: int = Field(default=0, ge=0)
    land_delta: int = Field(default=0)


class ManaFixResponse(BaseModel):
    """Mana-base report plus suggested lands to fix deficient colors."""

    report: ManaBaseReport
    suggestions: list[CardSuggestion] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class CardSearchInput(BaseModel):
    """Arguments the LLM passes to the ``card_search`` tool. The backend
    overlays the deck's color identity onto every query — the LLM cannot
    escape it.
    """

    text_query: str | None = None
    types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    min_cmc: int | None = Field(default=None, ge=0, le=20)
    max_cmc: int | None = Field(default=None, ge=0, le=20)
    max_price_eur_cents: int | None = Field(default=None, ge=0)
    limit: int = Field(default=8, ge=1, le=20)


class CardSearchHit(BaseModel):
    """A single card returned by the ``card_search`` tool. Already validated
    against the deck's color identity.
    """

    scryfall_id: UUID | None = None
    name: str
    mana_cost: str | None = None
    cmc: float | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    color_identity: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    price_eur_cents: int | None = None


class AnalysisFinding(BaseModel):
    """One diagnosis line produced by the analysis agent."""

    category: Literal["mana_base", "consistency", "curve", "commander", "color_fix", "card_quality"]
    severity: Literal["info", "warn", "critical"]
    title: str
    detail: str
    evidence: str


class SwapSuggestion(BaseModel):
    """A concrete swap recommendation — remove cards from the deck and replace
    them with candidates the agent retrieved via ``card_search``.
    """

    remove: list[str] = Field(default_factory=list)
    add: list[CardSearchHit] = Field(default_factory=list)
    reason: str


class SimulationAnalysisResponse(BaseModel):
    """Structured output of the simulation analysis agent."""

    summary: str
    findings: list[AnalysisFinding] = Field(default_factory=list)
    swap_suggestions: list[SwapSuggestion] = Field(default_factory=list)
    tool_call_count: int = 0


class DoctorCut(BaseModel):
    """A card the deck doctor recommends cutting."""

    card_name: str
    reason: str
    confidence: Literal["low", "medium", "high"] = "medium"


class DoctorAdd(BaseModel):
    """A card the deck doctor recommends adding."""

    card: CardSearchHit
    reason: str
    confidence: Literal["low", "medium", "high"] = "medium"


class DoctorSwap(BaseModel):
    """A concrete cut/add package produced by the deck doctor."""

    remove: list[str] = Field(default_factory=list)
    add: list[CardSearchHit] = Field(default_factory=list)
    reason: str


class DeckDoctorResponse(BaseModel):
    """Structured output of the Commander deck doctor agent."""

    summary: str
    game_plan: str
    findings: list[AnalysisFinding] = Field(default_factory=list)
    cuts: list[DoctorCut] = Field(default_factory=list)
    adds: list[DoctorAdd] = Field(default_factory=list)
    swaps: list[DoctorSwap] = Field(default_factory=list)
    tool_call_count: int = 0


class DeckIdentityReport(BaseModel):
    """Identity anchor for the multi-step Commander Coach pipeline."""

    archetype: str
    main_plan: str
    secondary_plan: str | None = None
    power_target: str
    deck_tension: list[str] = Field(default_factory=list)
    must_preserve_themes: list[str] = Field(default_factory=list)


class CoachManaReport(BaseModel):
    """Coach-facing mana-base diagnosis derived from deterministic analysis."""

    summary: str
    total_lands: int = Field(ge=0)
    recommended_lands: int = Field(ge=0)
    land_delta: int
    color_issues: list[str] = Field(default_factory=list)
    risky_cards: list[str] = Field(default_factory=list)
    ramp_count: int = Field(ge=0)


class CoachCurveReport(BaseModel):
    """Coach-facing curve and tempo diagnosis."""

    summary: str
    curve: dict[str, int] = Field(default_factory=dict)
    overloaded_buckets: list[str] = Field(default_factory=list)
    underfilled_buckets: list[str] = Field(default_factory=list)
    tempo_issues: list[str] = Field(default_factory=list)


class CoachCutCandidate(BaseModel):
    """Ranked cut candidate from the cut specialist."""

    card_name: str
    cut_score: float = Field(ge=0.0, le=10.0)
    reason: str
    tags: list[str] = Field(default_factory=list)


class CoachCutReport(BaseModel):
    """Structured output from the cut specialist."""

    summary: str
    candidates: list[CoachCutCandidate] = Field(default_factory=list)


class CoachUpgradeCandidate(BaseModel):
    """Grounded upgrade candidate returned by the upgrade specialist."""

    card: CardSearchHit
    reason: str
    role: str
    replaces: list[str] = Field(default_factory=list)


class CoachUpgradeReport(BaseModel):
    """Structured output from the upgrade specialist."""

    summary: str
    candidates: list[CoachUpgradeCandidate] = Field(default_factory=list)
    tool_call_count: int = 0


class ReplacementOption(BaseModel):
    """One candidate for replacing a specific card."""

    card: CardSearchHit
    reason: str
    role_match: Literal["same_role", "role_upgrade", "theme_upgrade", "role_change"]
    tradeoff: str | None = None


class TargetedReplacementResponse(BaseModel):
    """Focused replacement advice for one card already in the deck."""

    target_card_name: str
    summary: str
    keep_reason: str | None = None
    best_pick: CardSearchHit | None = None
    options: list[ReplacementOption] = Field(default_factory=list)
    tool_call_count: int = 0


CoachMode = Literal["auto", "doctor", "builder", "mana", "meta"]
CoachResolvedMode = Literal[
    "doctor",
    "builder",
    "mana",
    "meta",
    "memory",
    "chat",
    "replacement",
]


class CommanderCoachRequest(BaseModel):
    """Request body for the Commander Coach orchestrator."""

    message: str = Field(default="Doctor this deck", max_length=4000)
    mode: CoachMode = "auto"
    coach_memory_notes: str | None = Field(default=None, max_length=8000)


class CoachMemoryUpdate(BaseModel):
    """User-editable persistent notes for one deck's Coach context."""

    notes: str = Field(default="", max_length=8000)


class CoachMemoryResponse(BaseModel):
    """Persistent Commander Coach memory for a deck/account pair."""

    deck_id: UUID
    account_id: UUID
    notes: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CommanderCoachResponse(BaseModel):
    """Response from the Commander Coach orchestrator."""

    mode: CoachResolvedMode
    reply: str
    doctor: DeckDoctorResponse | None = None
    replacement: TargetedReplacementResponse | None = None
    coach_memory: CoachMemoryResponse | None = None
    memory_updated: bool = False


class CommanderCoachStartResponse(BaseModel):
    """Response after starting a streaming Coach job."""

    job_id: UUID


class KeywordExtractResponse(BaseModel):
    """Response from the keyword-extracting deck agent.

    ``archetype_tags`` is the running set of canonical keywords the agent has
    inferred from the conversation. The frontend mirrors them as live chips so
    the user can refine selection mid-conversation. Unknown tags are silently
    dropped — see :meth:`_filter_known_archetype_tags`.
    """

    reply: str
    done: bool
    archetype_tags: list[str] = Field(default_factory=list)
    suggested_name: str | None = None
    stage_targets: dict[str, int] | None = None

    @field_validator("archetype_tags", mode="after")
    @classmethod
    def _filter_known_archetype_tags(cls, value: list[str]) -> list[str]:
        """Drop tags outside the agent's archetype/tribal vocab; preserve order."""
        from mtg_helper.services.agents.extract_agent import KEYWORD_VOCAB
        from mtg_helper.services.tag_service import _TRIBAL_SUBTYPES

        allowed_archetypes = set(KEYWORD_VOCAB)
        allowed_tribes = {f"{s.lower()}_tribal" for s in _TRIBAL_SUBTYPES}
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            tag = item.strip().lower()
            if tag in seen:
                continue
            if tag in allowed_archetypes or tag in allowed_tribes:
                seen.add(tag)
                out.append(tag)
        return out
