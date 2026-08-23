"""Compact deterministic tools used by the conversational MTG Assistant."""

import re
from collections import Counter
from collections.abc import Mapping
from typing import Literal
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field

from mtg_helper.models.ai import CardSearchHit, CardSuggestion, ManaBaseReport, ManaFixResponse
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.services import bracket_service, mana_base_service
from mtg_helper.services.commander_coach import pipeline
from mtg_helper.services.deck_fit_service import WeakCardEvidence, weak_card_evidence
from mtg_helper.services.theme_service import score_themes

_MAX_THEME_MATCHES = 5
_MAX_CANDIDATES = 12
_BASIC_LAND_TYPES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}


class ThemeMatch(BaseModel):
    """One bounded theme-catalog match."""

    tag: str
    label: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source: Literal["group", "moxfield", "archidekt"]
    confidence: float = Field(ge=0.0, le=1.0)


class ThemeCardCandidate(BaseModel):
    """One legal card ranked by stored theme statistics."""

    card: CardSearchHit
    theme_score: float
    evidence_source: Literal["hub_tag_stats", "local_tags"] = "hub_tag_stats"
    game_changer: bool = False
    commander_matches: list[str] = Field(default_factory=list)
    role_matches: list[str] = Field(default_factory=list)


class DeckAnalysis(BaseModel):
    """Compact deterministic deck-health evidence."""

    mana_summary: str
    curve_summary: str
    role_summary: str
    synergy_summary: str
    priority_roles: list[str] = Field(default_factory=list)
    weak_packages: list[str] = Field(default_factory=list)
    weak_cards: list[WeakCardEvidence] = Field(default_factory=list)


class ManaBaseSwap(BaseModel):
    """One grounded land-for-land improvement."""

    remove_card: str
    add: CardSearchHit
    reason: str


class AssistantManaBaseAnalysis(BaseModel):
    """Bounded mana diagnosis and deterministic land swaps."""

    report: ManaBaseReport
    recommended_land_range: tuple[int, int]
    tapped_land_count: int = Field(ge=0)
    utility_land_count: int = Field(ge=0)
    swaps: list[ManaBaseSwap] = Field(default_factory=list, max_length=6)
    unresolved: list[str] = Field(default_factory=list, max_length=5)


class LegalityIssue(BaseModel):
    """One deterministic Commander legality failure."""

    code: str
    message: str
    cards: list[str] = Field(default_factory=list)


class LegalityReport(BaseModel):
    """Commander legality result for a deck and optional candidates."""

    legal: bool
    issues: list[LegalityIssue] = Field(default_factory=list)


class BracketReport(BaseModel):
    """Current deterministic bracket evaluation with per-rule evidence."""

    declared_bracket: int
    acceptable: bool
    ruleset: str = "project-commander-brackets-v1"
    warnings: list[str] = Field(default_factory=list)
    game_changers: list[str] = Field(default_factory=list)
    game_changer_limit: int | None = None
    game_changer_overage: int = 0
    mass_land_destruction: list[str] = Field(default_factory=list)
    fast_mana: list[str] = Field(default_factory=list)
    infinite_combo_pairs: list[list[str]] = Field(default_factory=list)


async def search_themes(
    pool: asyncpg.Pool,
    query: str,
    *,
    limit: int = _MAX_THEME_MATCHES,
) -> list[ThemeMatch]:
    """Search group and source metadata without placing the full catalog in a prompt."""
    normalized = _normalize(query)
    if not normalized:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(_THEME_CATALOG_SQL)
    ranked: list[tuple[float, asyncpg.Record]] = []
    for row in rows:
        score = _theme_match_score(normalized, row)
        if score > 0:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (item[0], item[1]["source"] == "group"), reverse=True)
    return [
        ThemeMatch(
            tag=row["tag"],
            label=row["label"],
            description=row["description"],
            aliases=list(row["aliases"] or []),
            source=row["source"],
            confidence=min(1.0, score),
        )
        for score, row in ranked[: min(limit, _MAX_THEME_MATCHES)]
    ]


async def find_theme_cards(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    theme_tags: list[str],
    *,
    max_price_eur_cents: int | None = None,
    roles: list[str] | None = None,
    limit: int = 8,
) -> list[ThemeCardCandidate]:
    """Return legal, novel cards ranked by selected hub/tag statistics."""
    scores = await score_themes(pool, theme_tags, pipeline.deck_colors(deck))
    if not scores:
        return await _fallback_theme_cards(
            pool,
            deck,
            theme_tags,
            max_price_eur_cents=max_price_eur_cents,
            roles=roles,
            limit=limit,
        )
    card_ids = sorted(scores, key=lambda card_id: scores[card_id], reverse=True)[:80]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _THEME_CARD_SQL,
            card_ids,
            _existing_names(deck),
            max_price_eur_cents,
        )
    candidates = [_candidate_from_row(row, scores, deck) for row in rows]
    if roles:
        wanted = set(roles)
        candidates = [item for item in candidates if wanted & set(item.role_matches)]
    candidates.sort(key=lambda item: (item.theme_score, len(item.commander_matches)), reverse=True)
    return candidates[: min(limit, _MAX_CANDIDATES)]


async def _fallback_theme_cards(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    theme_tags: list[str],
    *,
    max_price_eur_cents: int | None,
    roles: list[str] | None,
    limit: int,
) -> list[ThemeCardCandidate]:
    """Use local tags when source statistics are unavailable."""
    local_tags = sorted({tag.split(":", maxsplit=1)[-1] for tag in theme_tags})
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _LOCAL_TAG_CARD_SQL,
            local_tags,
            pipeline.deck_colors(deck),
            _existing_names(deck),
            max_price_eur_cents,
        )
    candidates = [
        _candidate_from_row(row, {}, deck).model_copy(update={"evidence_source": "local_tags"})
        for row in rows
    ]
    if roles:
        wanted = set(roles)
        candidates = [item for item in candidates if wanted & set(item.role_matches)]
    return candidates[: min(limit, _MAX_CANDIDATES)]


def analyze_deck(deck: DeckDetailResponse) -> DeckAnalysis:
    """Return deterministic deck-health evidence already used by the old pipeline."""
    mana = pipeline.analyze_mana(deck)
    curve = pipeline.analyze_curve(deck)
    roles = pipeline.analyze_role_budget(deck)
    synergy = pipeline.analyze_synergy(deck)
    return DeckAnalysis(
        mana_summary=mana.summary,
        curve_summary=curve.summary,
        role_summary=roles.summary,
        synergy_summary=synergy.summary,
        priority_roles=roles.priority_roles,
        weak_packages=synergy.weak_packages,
        weak_cards=weak_card_evidence(deck, limit=8),
    )


async def analyze_mana_base(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
) -> AssistantManaBaseAnalysis:
    """Return a deterministic mana diagnosis with grounded land swaps."""
    fix = await mana_base_service.suggest_mana_fix(pool, deck, account_id=None)
    return _compose_mana_base_analysis(deck, fix)


def _compose_mana_base_analysis(
    deck: DeckDetailResponse,
    fix: ManaFixResponse,
) -> AssistantManaBaseAnalysis:
    """Pair mana-fix candidates with safe in-deck land removals."""
    deficient = {status.color for status in fix.report.colors if status.deficit > 0}
    removable = [
        card
        for card in deck.cards
        if "Land" in (card.type_line or "")
        and card.quantity > 0
        and not (set(card.color_identity or []) & deficient)
    ]
    removable.sort(key=_land_removal_rank, reverse=True)
    swaps = [
        ManaBaseSwap(
            remove_card=land.name,
            add=_suggestion_hit(candidate),
            reason=_mana_swap_reason(land.name, candidate.name, deficient),
        )
        for land, candidate in zip(removable[:6], fix.suggestions[:6], strict=False)
    ]
    unresolved = list(fix.unresolved)
    if fix.suggestions and not swaps:
        unresolved.append("No land can be removed without reducing a deficient color source.")
    lands = [card for card in deck.cards if "Land" in (card.type_line or "")]
    recommended = fix.report.recommended_lands
    return AssistantManaBaseAnalysis(
        report=fix.report,
        recommended_land_range=(max(0, recommended - 1), recommended + 1),
        tapped_land_count=sum(
            card.quantity
            for card in lands
            if "enters the battlefield tapped" in (card.oracle_text or "").lower()
        ),
        utility_land_count=sum(card.quantity for card in lands if not card.color_identity),
        swaps=swaps,
        unresolved=unresolved[:5],
    )


def _land_removal_rank(card: DeckCardItem) -> tuple[bool, bool]:
    oracle_text = (card.oracle_text or "").lower()
    colors = card.color_identity or []
    return ("enters the battlefield tapped" in oracle_text, not colors)


def _suggestion_hit(candidate: CardSuggestion) -> CardSearchHit:
    return CardSearchHit(
        scryfall_id=candidate.scryfall_id,
        name=candidate.name,
        mana_cost=candidate.mana_cost,
        cmc=candidate.cmc,
        type_line=candidate.type_line,
        oracle_text=candidate.oracle_text,
        color_identity=list(candidate.color_identity),
        price_eur_cents=candidate.price_eur_cents,
    )


def _mana_swap_reason(remove: str, add: str, deficient: set[str]) -> str:
    colors = "/".join(sorted(deficient)) or "needed"
    return f"Replace {remove} with {add} to add a {colors} source without changing land count."


async def check_legality(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    candidate_ids: list[UUID] | None = None,
) -> LegalityReport:
    """Check structural, color-identity, and database-backed Commander legality."""
    issues = _structural_issues(deck)
    ids = [card.card_id for card in deck.cards]
    ids.extend(card_id for card_id in (candidate_ids or []) if card_id not in ids)
    ids.extend(
        card_id
        for card_id in (deck.commander_id, deck.partner_id)
        if card_id is not None and card_id not in ids
    )
    if ids:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, name, type_line, oracle_text, color_identity,
                          legalities->>'commander' AS legality
                   FROM cards WHERE id = ANY($1::uuid[])""",
                ids,
            )
        issues.extend(_database_legality_issues(rows, pipeline.deck_colors(deck)))
        issues.extend(_commander_eligibility_issues(rows, deck))
    return LegalityReport(legal=not issues, issues=issues)


def check_bracket(deck: DeckDetailResponse, target_bracket: int | None = None) -> BracketReport:
    """Expose current project bracket checks as evidence, never model judgment.

    Args:
        deck: The deck to evaluate.
        target_bracket: Optional target bracket to evaluate against (used for
            conversion questions). Defaults to the deck's declared bracket.
    """
    evaluation = bracket_service.evaluate_bracket(deck, combos=None, target_bracket=target_bracket)
    return BracketReport(
        declared_bracket=evaluation.declared_bracket,
        acceptable=evaluation.acceptable,
        warnings=[violation.message for violation in evaluation.violations],
        game_changers=evaluation.game_changers,
        game_changer_limit=evaluation.game_changer_limit,
        game_changer_overage=evaluation.game_changer_overage,
        mass_land_destruction=evaluation.mass_land_destruction,
        fast_mana=evaluation.fast_mana,
        infinite_combo_pairs=evaluation.infinite_combo_pairs,
    )


def _theme_match_score(query: str, row: Mapping[str, object]) -> float:
    tag = _normalize(str(row["tag"]).split(":", maxsplit=1)[-1])
    label = _normalize(str(row["label"]))
    raw_aliases = row["aliases"]
    aliases = (
        [_normalize(str(alias)) for alias in raw_aliases]
        if isinstance(raw_aliases, list | tuple)
        else []
    )
    description = _normalize(str(row["description"] or ""))
    if query in {tag, label, *aliases}:
        return 1.0
    if query in tag or query in label or any(query in alias for alias in aliases):
        return 0.9
    query_words = set(query.split())
    searchable = set(" ".join([tag, label, *aliases, description]).split())
    overlap = len(query_words & searchable) / max(1, len(query_words))
    return overlap * 0.8 if overlap >= 0.34 else 0.0


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _existing_names(deck: DeckDetailResponse) -> list[str]:
    return [card.name for card in deck.cards]


def _candidate_from_row(
    row: asyncpg.Record,
    scores: dict[UUID, float],
    deck: DeckDetailResponse,
) -> ThemeCardCandidate:
    hit = CardSearchHit(
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=float(row["cmc"]) if row["cmc"] is not None else None,
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        color_identity=list(row["color_identity"] or []),
        tags=list(row["tags"] or []),
        price_eur_cents=row["price_eur_cents"],
    )
    blob = _card_blob(hit)
    commander_words = _commander_words(deck)
    return ThemeCardCandidate(
        card=hit,
        theme_score=round(scores.get(row["id"], 0.0), 3),
        game_changer=bool(row["game_changer"]),
        commander_matches=sorted(commander_words & set(blob.split()))[:6],
        role_matches=_roles(blob),
    )


def _commander_words(deck: DeckDetailResponse) -> set[str]:
    commander = deck.commander_card
    if commander is None:
        return set()
    words = set(_normalize(" ".join([commander.name, commander.oracle_text or ""])).split())
    return {word for word in words if len(word) >= 5}


def _card_blob(card: CardSearchHit) -> str:
    return _normalize(
        " ".join([card.name, card.type_line or "", card.oracle_text or "", *card.tags])
    )


def _roles(blob: str) -> list[str]:
    terms = {
        "draw": ("draw", "card advantage"),
        "interaction": ("destroy", "exile", "counter target"),
        "ramp": ("add mana", "search your library for a land"),
        "protection": ("hexproof", "indestructible", "protection"),
        "payoff": ("whenever", "double", "additional", "each opponent"),
    }
    return [role for role, needles in terms.items() if any(term in blob for term in needles)]


def _structural_issues(deck: DeckDetailResponse) -> list[LegalityIssue]:
    issues: list[LegalityIssue] = []
    total = sum(card.quantity for card in deck.cards) + 1 + int(deck.partner_id is not None)
    if total != 100:
        issues.append(
            LegalityIssue(
                code="deck_size",
                message=f"Commander decks require 100 cards; found {total}.",
            )
        )
    counts = Counter({card.name: card.quantity for card in deck.cards})
    basic_lands = {
        card.name
        for card in deck.cards
        if "Basic Land" in (card.type_line or "") or card.name in _BASIC_LAND_TYPES
    }
    flexible_names = {
        card.name
        for card in deck.cards
        if "deck can have any number of cards named" in (card.oracle_text or "").lower()
        or "deck can have up to" in (card.oracle_text or "").lower()
    }
    duplicates = [
        name
        for name, count in counts.items()
        if count > 1 and name not in basic_lands | flexible_names
    ]
    if duplicates:
        issues.append(
            LegalityIssue(
                code="singleton",
                message="Commander is singleton outside basic lands.",
                cards=sorted(duplicates),
            )
        )
    return issues


def _commander_eligibility_issues(
    rows: list[asyncpg.Record], deck: DeckDetailResponse
) -> list[LegalityIssue]:
    by_id = {row["id"]: row for row in rows}
    commander = by_id.get(deck.commander_id)
    partner = by_id.get(deck.partner_id) if deck.partner_id else None
    invalid: list[str] = []
    if commander is not None and not _can_command(commander, None):
        invalid.append(commander["name"])
    if partner is not None and not _can_command(partner, commander):
        invalid.append(partner["name"])
    if not invalid:
        return []
    return [
        LegalityIssue(
            code="commander_eligibility",
            message="Command-zone cards must be eligible commanders or backgrounds.",
            cards=sorted(invalid),
        )
    ]


def _can_command(card: asyncpg.Record, primary: asyncpg.Record | None) -> bool:
    type_line = card["type_line"] or ""
    oracle_text = (card["oracle_text"] or "").lower()
    if "Legendary" in type_line and "Creature" in type_line:
        return True
    if "can be your commander" in oracle_text:
        return True
    primary_text = (primary["oracle_text"] or "").lower() if primary is not None else ""
    return "Background" in type_line and "choose a background" in primary_text


def _database_legality_issues(
    rows: list[asyncpg.Record],
    deck_colors: list[str],
) -> list[LegalityIssue]:
    issues: list[LegalityIssue] = []
    banned = sorted(row["name"] for row in rows if row["legality"] != "legal")
    if banned:
        issues.append(
            LegalityIssue(
                code="commander_legality",
                message="Cards must be legal in Commander.",
                cards=banned,
            )
        )
    color_violations = sorted(
        row["name"] for row in rows if not set(row["color_identity"] or []) <= set(deck_colors)
    )
    if color_violations:
        issues.append(
            LegalityIssue(
                code="color_identity",
                message="Cards must fit the commander's color identity.",
                cards=color_violations,
            )
        )
    return issues


_THEME_CATALOG_SQL = """
SELECT g.slug AS tag, g.label, g.description, g.aliases, 'group' AS source
FROM theme_groups g
WHERE g.enabled AND g.deleted_at IS NULL
  AND EXISTS (SELECT 1 FROM theme_group_members member WHERE member.group_id = g.id)
UNION ALL
SELECT 'moxfield:' || h.tag, h.name, h.description, ARRAY[]::text[], 'moxfield'
FROM moxfield_hubs h
LEFT JOIN theme_group_members m ON m.moxfield_hub_id = h.id
WHERE h.active AND h.enabled AND m.id IS NULL
UNION ALL
SELECT 'archidekt:' || t.tag, t.name, t.description, ARRAY[]::text[], 'archidekt'
FROM archidekt_tags t
LEFT JOIN theme_group_members m ON m.archidekt_tag_id = t.id
WHERE t.active AND t.enabled AND m.id IS NULL
"""


_THEME_CARD_SQL = """
SELECT id, scryfall_id, name, mana_cost, cmc, type_line, oracle_text, color_identity,
       tags, game_changer,
       ROUND((prices->>'eur')::numeric * 100)::integer AS price_eur_cents
FROM cards
WHERE id = ANY($1::uuid[])
  AND name <> ALL($2::text[])
  AND legalities->>'commander' = 'legal'
  AND ($3::integer IS NULL OR
       ((prices->>'eur') IS NOT NULL AND
        ROUND((prices->>'eur')::numeric * 100)::integer <= $3))
  AND type_line NOT ILIKE '%Basic Land%'
"""


_LOCAL_TAG_CARD_SQL = """
SELECT id, scryfall_id, name, mana_cost, cmc, type_line, oracle_text, color_identity,
       tags, game_changer,
       ROUND((prices->>'eur')::numeric * 100)::integer AS price_eur_cents
FROM cards
WHERE (tags && $1::text[] OR hub_tags && $1::text[] OR mtgjson_tags && $1::text[])
  AND color_identity <@ $2::text[]
  AND name <> ALL($3::text[])
  AND legalities->>'commander' = 'legal'
  AND ($4::integer IS NULL OR
       ((prices->>'eur') IS NOT NULL AND
        ROUND((prices->>'eur')::numeric * 100)::integer <= $4))
  AND type_line NOT ILIKE '%Basic Land%'
ORDER BY COALESCE(edhrec_rank, 999999) ASC NULLS LAST
LIMIT 40
"""
