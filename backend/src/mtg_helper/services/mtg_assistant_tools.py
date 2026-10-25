"""Compact deterministic tools used by the conversational MTG Assistant."""

from collections import Counter
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field

from mtg_helper.models.ai import CardSearchHit, CardSuggestion, ManaBaseReport, ManaFixResponse
from mtg_helper.models.decks import DeckCardItem, DeckDetailResponse
from mtg_helper.services import bracket_service, mana_base_service
from mtg_helper.services.commander_coach import pipeline
from mtg_helper.services.deck_fit_service import WeakCardEvidence, weak_card_evidence

_MAX_GAME_CHANGER_NAMES = 10
_BASIC_LAND_TYPES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}


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


class GameChangerStatus(BaseModel):
    """One named card's deterministic Game Changer status."""

    name: str
    is_game_changer: bool


class GameChangerCheck(BaseModel):
    """Deterministic Game Changer lookup for arbitrary card names."""

    results: list[GameChangerStatus] = Field(default_factory=list)
    unknown_names: list[str] = Field(default_factory=list)
    ruleset: str = "project-commander-brackets-v1"


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


async def check_game_changers(pool: asyncpg.Pool, names: list[str]) -> GameChangerCheck:
    """Return deterministic Game Changer status for up to ten named cards.

    Matches canonical card names case-insensitively, including the front face
    of modal double-faced cards (e.g. ``Tergrid`` finds
    ``Tergrid, God of Fright // Tergrid's Lantern``). Names with no match are
    reported in ``unknown_names`` rather than guessed.

    Args:
        pool: Database pool for the card lookup.
        names: Card names to check; at most ``_MAX_GAME_CHANGER_NAMES``.
    """
    if len(names) > _MAX_GAME_CHANGER_NAMES:
        raise ValueError(f"check_game_changers accepts at most {_MAX_GAME_CHANGER_NAMES} names")
    requested = [name.strip() for name in names if name and name.strip()]
    if not requested:
        return GameChangerCheck()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT name, game_changer
            FROM cards
            WHERE is_canonical
              AND (
                  lower(name) = ANY($1::text[])
                  OR lower(split_part(name, ' // ', 1)) = ANY($1::text[])
              )
            """,
            [name.casefold() for name in requested],
        )
    by_name: dict[str, asyncpg.Record] = {
        row["name"].casefold().split(" // ", maxsplit=1)[0]: row for row in rows
    }
    results: list[GameChangerStatus] = []
    unknown: list[str] = []
    for name in requested:
        row = by_name.get(name.casefold())
        if row is None:
            unknown.append(name)
        else:
            results.append(
                GameChangerStatus(
                    name=row["name"],
                    is_game_changer=bool(row["game_changer"]),
                )
            )
    return GameChangerCheck(results=results, unknown_names=unknown)


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
