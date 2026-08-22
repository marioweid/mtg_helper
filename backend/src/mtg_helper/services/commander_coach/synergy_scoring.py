"""Deterministic synergy scoring for Commander Coach upgrade discovery.

The scorer is intentionally independent from external decklists. It uses
only card text, deck identity, role budgets, and package density so suggestions
are theme-correct without copying external lists.
"""

from dataclasses import dataclass
from typing import Literal

import asyncpg
from pydantic import BaseModel, Field

from mtg_helper.models.ai import (
    CardSearchHit,
    CardSearchInput,
    CoachRoleBudgetReport,
    CoachSynergyReport,
    DeckIdentityReport,
)
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.card_search_tool import search_cards
from mtg_helper.services.commander_coach import pipeline

PackageStatus = Literal["strong", "playable", "weak"]


class ScoredUpgrade(BaseModel):
    """One local-card candidate with deterministic synergy evidence."""

    card: CardSearchHit
    score: float
    status: PackageStatus
    packages: list[str] = Field(default_factory=list)
    role_matches: list[str] = Field(default_factory=list)
    commander_matches: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PackageSpec:
    """Text-query and scoring terms for a theme package."""

    name: str
    queries: tuple[str, ...]
    terms: tuple[str, ...]
    role: str


async def discover_scored_upgrades(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    roles: CoachRoleBudgetReport | None,
    synergy: CoachSynergyReport | None,
    *,
    limit: int = 20,
) -> list[ScoredUpgrade]:
    """Discover and rank local upgrade candidates by package overlap."""
    specs = _ordered_specs(_package_specs(identity, deck), synergy, roles)
    raw = await _fetch_broad_candidates(pool, deck, specs)
    scored = [score_card(card, deck, identity, roles, specs) for card in raw]
    keep = [item for item in scored if item.status != "weak"]
    keep.sort(key=lambda item: _rank_key(item), reverse=True)
    return keep[:limit]


def score_card(
    card: CardSearchHit,
    deck: DeckDetailResponse,
    identity: DeckIdentityReport,
    roles: CoachRoleBudgetReport | None,
    specs: list[PackageSpec] | None = None,
) -> ScoredUpgrade:
    """Score one candidate against deck identity and role budget."""
    specs = specs or _package_specs(identity, deck)
    text = _card_blob(card)
    packages = _matched_packages(text, specs)
    role_matches = sorted({spec.role for spec in specs if spec.name in packages})
    commander_matches = _commander_matches(text, deck)
    penalties = _penalties(card, roles) + _package_penalties(packages, identity, deck)
    score = _score(packages, role_matches, commander_matches, penalties)
    return ScoredUpgrade(
        card=card,
        score=score,
        status=_status(score),
        packages=packages,
        role_matches=role_matches,
        commander_matches=commander_matches,
        penalties=penalties,
    )


def reason_for_score(item: ScoredUpgrade) -> str:
    """Build a concise user-facing reason from deterministic evidence."""
    bits: list[str] = []
    if item.packages:
        bits.append("connects to " + ", ".join(item.packages[:3]))
    if item.role_matches:
        bits.append("fills " + ", ".join(item.role_matches[:2]))
    if item.commander_matches:
        bits.append("overlaps commander text: " + ", ".join(item.commander_matches[:3]))
    if not bits:
        bits.append("matches the deck identity better than generic goodstuff")
    return f"Synergy score {item.score:.1f}: " + "; ".join(bits) + "."


async def _fetch_broad_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    specs: list[PackageSpec],
) -> list[CardSearchHit]:
    """Fetch all legal local cards that mention at least one package term."""
    terms = sorted({term for spec in specs for term in spec.terms if len(term) >= 4})
    if not terms:
        return await _fetch_candidates(pool, deck, specs)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _candidate_sql(len(terms)),
            pipeline.deck_colors(deck),
            _existing_names(deck),
            *[f"%{term}%" for term in terms],
        )
    return [_hit_from_row(row) for row in rows if not _is_land_row(row)]


async def _fetch_candidates(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    specs: list[PackageSpec],
) -> list[CardSearchHit]:
    seen: set[str] = set()
    out: list[CardSearchHit] = []
    exclude = _existing_names(deck)
    for spec in specs:
        for query in spec.queries:
            hits = await search_cards(
                pool,
                deck_color_identity=pipeline.deck_colors(deck),
                inp=CardSearchInput(text_query=query, limit=20, max_cmc=7),
                exclude_names=exclude,
            )
            for hit in hits:
                if hit.name not in seen and not _is_land(hit):
                    seen.add(hit.name)
                    out.append(hit)
    return out


def _candidate_sql(term_count: int) -> str:
    clauses = []
    for index in range(term_count):
        placeholder = f"${index + 3}"
        clauses.append(
            f"(name ILIKE {placeholder} OR type_line ILIKE {placeholder} "
            f"OR oracle_text ILIKE {placeholder})"
        )
    return (
        "SELECT scryfall_id, name, mana_cost, cmc, type_line, oracle_text, "
        "color_identity, tags, ROUND((prices->>'eur')::numeric * 100)::integer "
        "AS price_eur_cents FROM cards WHERE is_canonical "
        "AND color_identity <@ $1::text[] "
        "AND name <> ALL($2::text[]) AND legalities->>'commander' = 'legal' "
        "AND type_line NOT ILIKE '%Land%' AND (" + " OR ".join(clauses) + ") "
        "ORDER BY COALESCE(edhrec_rank, 999999) ASC NULLS LAST LIMIT 1200"
    )


def _hit_from_row(row: asyncpg.Record) -> CardSearchHit:
    return CardSearchHit(
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


def _is_land_row(row: asyncpg.Record) -> bool:
    return "land" in (row["type_line"] or "").lower()


def _rank_key(item: ScoredUpgrade) -> tuple[float, int, float]:
    cmc = item.card.cmc or 0.0
    return (item.score, len(item.packages), -cmc)


def _package_specs(identity: DeckIdentityReport, deck: DeckDetailResponse) -> list[PackageSpec]:
    blob = _identity_blob(identity, deck)
    if "food" in blob or "squirrel" in blob:
        return _camellia_specs()
    if "hydra" in blob or "x spell" in blob or "x_spells" in blob:
        return _zaxara_specs()
    return [PackageSpec("theme", (identity.archetype,), tuple(blob.split()), "theme")]


def _camellia_specs() -> list[PackageSpec]:
    return [
        PackageSpec(
            "food_generation",
            ("Food token", "create Food", "Food artifact"),
            ("food",),
            "engine",
        ),
        PackageSpec(
            "squirrel_generation",
            ("Squirrel token", "Squirrel creature"),
            ("squirrel",),
            "engine",
        ),
        PackageSpec(
            "sacrifice", ("sacrifice creature", "sacrifice artifact"), ("sacrifice",), "engine"
        ),
        PackageSpec("death_payoff", ("creature dies lose life",), ("dies", "loses life"), "payoff"),
        PackageSpec(
            "token_payoff", ("tokens creatures you control",), ("token", "tokens"), "payoff"
        ),
        PackageSpec(
            "token_doubler",
            ("double tokens", "twice tokens", "additional token"),
            ("twice", "additional token", "tokens instead"),
            "payoff",
        ),
        PackageSpec(
            "graveyard_value", ("return creature graveyard",), ("graveyard", "return"), "draw"
        ),
    ]


def _zaxara_specs() -> list[PackageSpec]:
    return [
        PackageSpec("x_spells", ("{X}", "X spell"), ("{x}", "x spell", "mana value x"), "payoff"),
        PackageSpec("hydras", ("Hydra",), ("hydra",), "payoff"),
        PackageSpec("counter_scaling", ("+1/+1 counter",), ("+1/+1 counter", "counters"), "payoff"),
        PackageSpec("card_advantage", ("draw card creature",), ("draw",), "draw"),
        PackageSpec("interaction", ("destroy exile removal",), ("destroy", "exile"), "interaction"),
    ]


def _ordered_specs(
    specs: list[PackageSpec],
    synergy: CoachSynergyReport | None,
    roles: CoachRoleBudgetReport | None,
) -> list[PackageSpec]:
    weak = set(synergy.weak_packages if synergy else [])
    priority = set(roles.priority_roles if roles else [])
    return sorted(specs, key=lambda spec: (spec.name in weak, spec.role in priority), reverse=True)


def _matched_packages(text: str, specs: list[PackageSpec]) -> list[str]:
    return [spec.name for spec in specs if _matches_terms(text, spec.terms)]


def _commander_matches(text: str, deck: DeckDetailResponse) -> list[str]:
    commander = deck.commander_card
    if commander is None:
        return []
    words = {word for word in _card_blob(commander).split() if len(word) >= 5}
    useful = {"food", "squirrel", "sacrifice", "token", "hydra", "counter", "mana", "draw"}
    return sorted(word for word in words & useful if word in text)


def _penalties(card: CardSearchHit, roles: CoachRoleBudgetReport | None) -> list[str]:
    penalties: list[str] = []
    if _is_land(card):
        penalties.append("land")
    if _is_ramp(card) and roles and "ramp" in roles.blocked_roles:
        penalties.append("ramp_not_needed")
    if card.cmc is not None and card.cmc >= 6:
        penalties.append("expensive")
    if len(_card_blob(card)) < 80:
        penalties.append("low_text_density")
    return penalties


def _package_penalties(
    packages: list[str],
    identity: DeckIdentityReport,
    deck: DeckDetailResponse,
) -> list[str]:
    if not _is_camellia_like(identity, deck):
        return []
    core = {"food_generation", "squirrel_generation", "token_payoff", "token_doubler"}
    generic = {"sacrifice", "graveyard_value", "death_payoff"}
    if not core & set(packages) and generic & set(packages):
        return ["generic_aristocrats_without_food_squirrel"]
    if packages == ["graveyard_value"] or packages == ["sacrifice"]:
        return ["single_generic_package"]
    return []


def _score(
    packages: list[str],
    roles: list[str],
    commander_matches: list[str],
    penalties: list[str],
) -> float:
    score = sum(_package_weight(package) for package in packages)
    score += len(roles) * 0.55 + len(commander_matches) * 1.1
    score -= sum(_penalty_weight(penalty) for penalty in penalties)
    if len(packages) >= 2:
        score += 1.4
    if len(packages) >= 3:
        score += 1.1
    return round(max(0.0, score), 2)


def _package_weight(package: str) -> float:
    weights = {
        "food_generation": 5.2,
        "squirrel_generation": 5.2,
        "token_doubler": 4.6,
        "token_payoff": 3.8,
        "death_payoff": 2.4,
        "sacrifice": 2.2,
        "graveyard_value": 1.8,
        "x_spells": 5.0,
        "hydras": 4.8,
        "counter_scaling": 3.6,
        "card_advantage": 2.6,
        "interaction": 2.4,
    }
    return weights.get(package, 2.0)


def _penalty_weight(penalty: str) -> float:
    weights = {
        "generic_aristocrats_without_food_squirrel": 4.2,
        "single_generic_package": 2.8,
        "ramp_not_needed": 2.0,
        "expensive": 0.8,
        "low_text_density": 1.0,
        "land": 10.0,
    }
    return weights.get(penalty, 1.3)


def _status(score: float) -> PackageStatus:
    if score >= 7.0:
        return "strong"
    if score >= 4.4:
        return "playable"
    return "weak"


def _matches_terms(text: str, terms: tuple[str, ...]) -> bool:
    return any(term.lower() in text for term in terms)


def _is_camellia_like(identity: DeckIdentityReport, deck: DeckDetailResponse) -> bool:
    blob = _identity_blob(identity, deck)
    return "food" in blob or "squirrel" in blob


def _identity_blob(identity: DeckIdentityReport, deck: DeckDetailResponse) -> str:
    return " ".join(
        [identity.archetype, identity.main_plan, " ".join(deck.archetype_tags or [])]
    ).lower()


def _card_blob(card: object) -> str:
    parts = [
        getattr(card, "name", "") or "",
        getattr(card, "type_line", "") or "",
        getattr(card, "oracle_text", "") or "",
        " ".join(getattr(card, "tags", []) or []),
    ]
    return " ".join(parts).lower()


def _is_land(card: CardSearchHit) -> bool:
    return "land" in (card.type_line or "").lower()


def _is_ramp(card: CardSearchHit) -> bool:
    text = _card_blob(card)
    return "add one mana" in text or "search your library for a land" in text or "ramp" in text


def _existing_names(deck: DeckDetailResponse) -> list[str]:
    names = [card.name for card in deck.cards]
    if deck.commander_card is not None:
        names.append(deck.commander_card.name)
    if deck.partner_card is not None:
        names.append(deck.partner_card.name)
    return names
