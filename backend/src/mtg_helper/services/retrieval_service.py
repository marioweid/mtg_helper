"""Structured retrieval service over Oracle-tag memberships and card facts."""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

import asyncpg

_log = logging.getLogger(__name__)

# Target CMC distribution for a typical commander deck (excluding lands/commander).
# Keys are CMC buckets; 6 means "6 or more". Values are target fractions.
_TARGET_CMC: dict[int, float] = {0: 0.05, 1: 0.08, 2: 0.22, 3: 0.25, 4: 0.18, 5: 0.12, 6: 0.10}
_MAX_INNER_POOL = 1000


@dataclass
class TypeFilter:
    """Parsed type, subtype, and printed-keyword preferences from a user query.

    When present, cards matching these criteria get a score boost during fusion.
    When ``strict=True``, cards with zero matches are scored 0.0 (hard-filtered out).
    When ``match_all_categories=True``, the score is 0.0 unless the card matches
    at least one term in *every* non-empty category — used by the structured UI
    filter so "Creature + Equipment" returns only creature-equipment hybrids
    instead of any creature OR any equipment.
    """

    card_types: list[str]
    subtypes: list[str]
    keywords: list[str] = field(default_factory=list)
    strict: bool = False
    match_all_categories: bool = False


@dataclass(frozen=True)
class RepresentationQuery:
    """Structured deterministic terms used for representation scoring."""

    tags: list[str] = field(default_factory=list)
    card_types: list[str] = field(default_factory=list)
    subtypes: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CollectionFilter:
    """Restricts retrieval to a set of owned cards.

    When active, only cards in ``owned_card_ids`` are eligible as candidates.
    A near-empty result beats padded-in cards the user doesn't own.
    """

    owned_card_ids: frozenset[UUID]


@dataclass(frozen=True)
class PriceFilter:
    """Restricts retrieval to cards with nonfoil EUR price in a cents range.

    Cards missing a EUR price are excluded (safe default: cannot verify price).
    ``min_cents`` defaults to 0 (no floor); ``max_cents`` is None for no ceiling.
    """

    max_cents: int | None = None
    min_cents: int = 0


def _build_price_clause(price_filter: PriceFilter | None, params: list) -> str:
    """Append price parameters and return the matching SQL fragment.

    Cards with NULL EUR price are always excluded when a filter is active.
    Appends up to two params (min, max) to ``params`` in that order and
    returns a SQL fragment that references them by ``$N`` position.
    """
    if price_filter is None:
        return ""
    clauses = ["AND (prices->>'eur') IS NOT NULL"]
    if price_filter.min_cents > 0:
        params.append(price_filter.min_cents)
        clauses.append(f"AND ((prices->>'eur')::numeric * 100) >= ${len(params)}")
    if price_filter.max_cents is not None:
        params.append(price_filter.max_cents)
        clauses.append(f"AND ((prices->>'eur')::numeric * 100) <= ${len(params)}")
    return " ".join(clauses)


@dataclass
class RetrievedCard:
    """A card retrieved via hybrid search, enriched with full DB data."""

    id: UUID
    scryfall_id: UUID
    oracle_id: UUID | None
    name: str
    mana_cost: str | None
    cmc: Decimal | None
    type_line: str | None
    oracle_text: str | None
    color_identity: list[str]
    image_uri: str | None
    tags: list[str]
    edhrec_rank: int | None
    power: str | None
    toughness: str | None
    rarity: str | None
    price_eur_cents: int | None
    score: float
    game_changer: bool = False
    signals: list[str] = field(default_factory=list)


# Maps stage names to (query_text, query_tags)
_STAGE_QUERIES: dict[str, tuple[str, list[str]]] = {
    "ramp": ("mana acceleration", []),
    "draw": ("draw cards", []),
    "interaction": ("removal counterspell board wipe protection", []),
    "lands": ("lands mana base mana fixing", []),
}


def parse_query_tags(query: str) -> list[str]:
    """Return explicit Oracle-tag UUIDs written in a query, never inferred labels."""
    values: list[str] = []
    for token in query.replace(",", " ").split():
        try:
            value = str(UUID(token))
        except ValueError:
            continue
        if value not in values:
            values.append(value)
    return values


_CARD_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "artifact",
        "creature",
        "enchantment",
        "instant",
        "land",
        "planeswalker",
        "sorcery",
        "battle",
        "kindred",
    }
)

# Plural forms for card type names (lowercase → canonical singular)
_CARD_TYPE_PLURALS: dict[str, str] = {
    "artifacts": "Artifact",
    "creatures": "Creature",
    "enchantments": "Enchantment",
    "instants": "Instant",
    "lands": "Land",
    "planeswalkers": "Planeswalker",
    "sorceries": "Sorcery",
    "battles": "Battle",
}

# Common creature and permanent subtypes worth detecting in queries
_SUBTYPE_NAMES: frozenset[str] = frozenset(
    {
        "elf",
        "elves",
        "human",
        "wizard",
        "goblin",
        "dragon",
        "monk",
        "angel",
        "demon",
        "zombie",
        "vampire",
        "merfolk",
        "warrior",
        "knight",
        "cleric",
        "rogue",
        "shaman",
        "druid",
        "beast",
        "elemental",
        "spirit",
        "squirrel",
        "cat",
        "dog",
        "bird",
        "soldier",
        "pirate",
        "dinosaur",
        "giant",
        "hydra",
        "wurm",
        "sliver",
        "golem",
        "elemental",
        "treefolk",
        "faerie",
        "kithkin",
        "ally",
        "scout",
        "ranger",
        "archer",
        "berserker",
        "artificer",
        "advisor",
        "noble",
        "peasant",
        "citizen",
        "rebel",
        "mercenary",
        "shaman",
        "barbarian",
        "horror",
        "illusion",
        "shapeshifter",
        "snake",
        "wolf",
        "bear",
        "spider",
        "insect",
        "rat",
        "fox",
        "raccoon",
        "rabbit",
        "otter",
        "mouse",
        "bat",
        "fish",
        "equipment",
        "aura",
        "vehicle",
        "food",
        "treasure",
        "clue",
        "saga",
        "class",
        "role",
        "curse",
    }
)

# Map plural/variant forms to canonical subtype
_SUBTYPE_NORMALIZE: dict[str, str] = {
    "elves": "Elf",
    "warriors": "Warrior",
    "goblins": "Goblin",
    "dragons": "Dragon",
    "humans": "Human",
    "wizards": "Wizard",
    "monks": "Monk",
    "angels": "Angel",
    "demons": "Demon",
    "zombies": "Zombie",
    "vampires": "Vampire",
    "knights": "Knight",
    "clerics": "Cleric",
    "rogues": "Rogue",
    "shamans": "Shaman",
    "druids": "Druid",
    "beasts": "Beast",
    "spirits": "Spirit",
    "slivers": "Sliver",
}

# MTG keyword abilities detectable from single query words
_KEYWORD_NAMES: frozenset[str] = frozenset(
    {
        # Evasion / combat
        "flying",
        "trample",
        "haste",
        "deathtouch",
        "lifelink",
        "menace",
        "vigilance",
        "flash",
        "reach",
        "ward",
        "hexproof",
        "indestructible",
        "defender",
        "prowess",
        "ninjutsu",
        "annihilator",
        "myriad",
        "wither",
        "infect",
        "exalted",
        # Card selection / advantage
        "scry",
        "surveil",
        "discover",
        "explore",
        "investigate",
        "connive",
        "foretell",
        # Counters / growth
        "proliferate",
        "adapt",
        "fabricate",
        "mentor",
        "training",
        "amass",
        "mutate",
        # Mana / cost reduction
        "cascade",
        "convoke",
        "delve",
        "cycling",
        "affinity",
        "kicker",
        "emerge",
        # Recursion / graveyard
        "flashback",
        "unearth",
        "encore",
        "escape",
        "overload",
        "embalm",
        "eternalize",
        "disturb",
        "madness",
        "dredge",
        "suspend",
        # Token / go-wide
        "populate",
        # Control / stax
        "extort",
        "miracle",
        "storm",
        "persist",
        "undying",
    }
)

# MTG keyword abilities that require phrase matching
_KEYWORD_PHRASES: frozenset[str] = frozenset(
    {
        "first strike",
        "double strike",
    }
)


def _classify_query_word(
    stripped: str,
    *,
    seen_types: set[str],
    seen_subs: set[str],
    seen_kw: set[str],
    card_types: list[str],
    subtypes: list[str],
    keywords: list[str],
) -> None:
    """Classify a single query word into card types, subtypes, or keywords."""
    if stripped in _CARD_TYPE_NAMES and stripped not in seen_types:
        seen_types.add(stripped)
        card_types.append(stripped.capitalize())
    elif stripped in _CARD_TYPE_PLURALS and stripped not in seen_types:
        seen_types.add(stripped)
        canonical = _CARD_TYPE_PLURALS[stripped]
        if canonical not in card_types:
            card_types.append(canonical)
    elif (
        stripped in _SUBTYPE_NAMES or stripped in _SUBTYPE_NORMALIZE
    ) and stripped not in seen_subs:
        seen_subs.add(stripped)
        subtypes.append(_SUBTYPE_NORMALIZE.get(stripped, stripped.capitalize()))
    elif stripped in _KEYWORD_NAMES and stripped not in seen_kw:
        seen_kw.add(stripped)
        keywords.append(stripped.capitalize())


def parse_query_types(query: str) -> TypeFilter | None:
    """Extract type/subtype/keyword/trait preferences from a natural-language query.

    Returns None when no filter terms are detected, keeping the feature inactive
    for queries that don't mention card types, subtypes, or printed keywords.

    Strict mode is enabled when 2+ filter terms are detected across all
    dimensions — strict queries zero-out zero-match cards.

    Args:
        query: Free-form user query text.

    Returns:
        TypeFilter if any filter terms detected, else None.
    """
    q_lower = query.lower()
    card_types: list[str] = []
    subtypes: list[str] = []
    keywords: list[str] = []
    seen_types: set[str] = set()
    seen_subs: set[str] = set()
    seen_kw: set[str] = set()

    for phrase in _KEYWORD_PHRASES:
        if phrase in q_lower and phrase not in seen_kw:
            seen_kw.add(phrase)
            keywords.append(phrase.title())

    for word in q_lower.split():
        stripped = word.strip(".,!?;:'\"")
        _classify_query_word(
            stripped,
            seen_types=seen_types,
            seen_subs=seen_subs,
            seen_kw=seen_kw,
            card_types=card_types,
            subtypes=subtypes,
            keywords=keywords,
        )
    if not card_types and not subtypes and not keywords:
        return None

    total_terms = len(card_types) + len(subtypes) + len(keywords)
    return TypeFilter(
        card_types=card_types,
        subtypes=subtypes,
        keywords=keywords,
        strict=total_terms >= 2,
    )


def stage_retrieval_query(stage: str, deck_description: str | None) -> tuple[str, list[str]]:
    """Map a build stage to a (query_text, query_tags) pair for retrieval.

    Appends the deck description to every stage's query text so full-text and
    tag parsing can use theme language even in generic stages like ramp or draw.

    Args:
        stage: Build stage name (e.g. "ramp", "draw", "theme").
        deck_description: Deck strategy description.

    Returns:
        Tuple of (query_text, query_tags).
    """
    if stage == "theme":
        desc = deck_description or "synergy theme core strategy"
        return f"{desc} synergy theme", parse_query_tags(desc)

    base = _STAGE_QUERIES.get(stage, (stage, []))
    if not deck_description:
        return base

    query_text = f"{base[0]} {deck_description}"
    return query_text, list(base[1])


def _normalize_card_name(name: str) -> str:
    return " ".join(name.split()).casefold()


async def _excluded_nonbasic_names(pool: asyncpg.Pool, ids: list[UUID]) -> set[str]:
    """Return singleton card names represented by excluded internal card IDs."""
    if not ids:
        return set()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT name
            FROM cards
            WHERE id = ANY($1::uuid[])
              AND COALESCE(type_line, '') NOT LIKE 'Basic Land%'
            """,
            ids,
        )
    return {_normalize_card_name(r["name"]) for r in rows}


async def _search_tags(
    pool: asyncpg.Pool,
    query_tags: list[str],
    commander_color_identity: list[str],
    exclude_ids: list[UUID],
    *,
    exclude_lands: bool = False,
    limit: int = 50,
    owned_card_ids: frozenset[UUID] | None = None,
    price_filter: PriceFilter | None = None,
) -> list[tuple[UUID, int]]:
    """Oracle-tag-overlap search via direct Scryfall memberships.

    Args:
        pool: asyncpg connection pool.
        query_tags: Scryfall Oracle-tag UUIDs to match.
        commander_color_identity: Commander's color identity (subset filter).
        exclude_ids: Card UUIDs to exclude.
        exclude_lands: If True, exclude land cards from results.
        limit: Maximum results to return.
        owned_card_ids: When set, restricts results to these card UUIDs.
        price_filter: When set, excludes cards with no EUR price or EUR > cap.

    Returns:
        List of (card_uuid, tag_overlap_count) pairs, highest overlap first.
    """
    if not query_tags:
        return []
    try:
        source_ids = [UUID(tag) for tag in query_tags]
    except ValueError:
        return []
    land_filter = "AND type_line NOT LIKE '%Land%'" if exclude_lands else ""
    params: list = [source_ids, commander_color_identity, exclude_ids, limit]
    collection_filter = ""
    if owned_card_ids is not None:
        params.append(list(owned_card_ids))
        collection_filter = f"AND id = ANY(${len(params)}::uuid[])"
    price_clause = _build_price_clause(price_filter, params)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id,
                   (SELECT count(*) FROM scryfall_tag_memberships membership
                    WHERE membership.oracle_id = cards.oracle_id
                      AND membership.tag_id = ANY($1::uuid[])) AS overlap
            FROM cards
            WHERE EXISTS (
                SELECT 1 FROM scryfall_tag_memberships membership
                WHERE membership.oracle_id = cards.oracle_id
                  AND membership.tag_id = ANY($1::uuid[])
            )
              AND is_canonical
              AND color_identity <@ $2::text[]
              AND legalities->>'commander' = 'legal'
              AND id != ALL($3::uuid[])
              AND COALESCE(border_color, '') != 'gold'
              AND COALESCE(security_stamp, '') != 'acorn'
              AND type_line NOT LIKE '%Conspiracy%'
              {land_filter}
              {collection_filter}
              {price_clause}
            ORDER BY
                overlap DESC NULLS LAST,
                edhrec_rank ASC NULLS LAST
            LIMIT $4
            """,
            *params,
        )
    return [(r["id"], r["overlap"] or 0) for r in rows]


async def _search_fts(
    pool: asyncpg.Pool,
    query_text: str,
    commander_color_identity: list[str],
    exclude_ids: list[UUID],
    *,
    exclude_lands: bool = False,
    limit: int = 30,
    owned_card_ids: frozenset[UUID] | None = None,
    price_filter: PriceFilter | None = None,
) -> list[UUID]:
    """Full-text search via Postgres tsvector index.

    Args:
        pool: asyncpg connection pool.
        query_text: Natural language query.
        commander_color_identity: Commander's color identity (subset filter).
        exclude_ids: Card UUIDs to exclude.
        exclude_lands: If True, exclude land cards from results.
        limit: Maximum results to return.
        owned_card_ids: When set, restricts results to these card UUIDs.
        price_filter: When set, excludes cards with no EUR price or EUR > cap.

    Returns:
        Ranked list of card UUIDs (best FTS rank first).
    """
    land_filter = "AND type_line NOT LIKE '%Land%'" if exclude_lands else ""
    params: list = [query_text, commander_color_identity, exclude_ids, limit]
    collection_filter = ""
    if owned_card_ids is not None:
        params.append(list(owned_card_ids))
        collection_filter = f"AND id = ANY(${len(params)}::uuid[])"
    price_clause = _build_price_clause(price_filter, params)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id
            FROM cards
            WHERE to_tsvector('english', COALESCE(oracle_text, ''))
                  @@ plainto_tsquery('english', $1)
              AND is_canonical
              AND color_identity <@ $2::text[]
              AND legalities->>'commander' = 'legal'
              AND id != ALL($3::uuid[])
              AND COALESCE(border_color, '') != 'gold'
              AND COALESCE(security_stamp, '') != 'acorn'
              AND type_line NOT LIKE '%Conspiracy%'
              {land_filter}
              {collection_filter}
              {price_clause}
            ORDER BY
                ts_rank(
                    to_tsvector('english', COALESCE(oracle_text, '')),
                    plainto_tsquery('english', $1)
                ) DESC
            LIMIT $4
            """,
            *params,
        )
    return [r["id"] for r in rows]


def _build_signal_map(
    tag_results: list[tuple[UUID, int]],
    fts_ids: list[UUID],
) -> tuple[
    dict[UUID, int],
    set[UUID],
    dict[UUID, list[str]],
]:
    """Build per-signal score maps and signal membership from individual search results.

    Args:
        tag_results: (uuid, overlap_count) pairs from Postgres tag search.
        fts_ids: UUIDs from Postgres FTS search.

    Returns:
        Tuple of (tag_overlaps, fts_set, signal_map).
    """
    tag_overlaps: dict[UUID, int] = {uid: overlap for uid, overlap in tag_results}
    fts_set: set[UUID] = set(fts_ids)
    signal_map: dict[UUID, list[str]] = {}

    for uid in tag_overlaps:
        if uid not in signal_map or "tag" not in signal_map[uid]:
            signal_map.setdefault(uid, []).append("tag")
    for uid in fts_set:
        entry = signal_map.setdefault(uid, [])
        if "fts" not in entry:
            entry.append("fts")

    return tag_overlaps, fts_set, signal_map


def _curve_fit_score(cmc: Decimal | None, deck_cmc_counts: dict[int, int] | None) -> float:
    """Score a card based on how underrepresented its CMC bucket is in the deck.

    Returns 0.5 if no deck distribution is provided (neutral score).
    Returns higher scores for CMC buckets that are below their target fraction.

    Args:
        cmc: Card's converted mana cost.
        deck_cmc_counts: Current deck card counts by CMC bucket.

    Returns:
        Curve fit score in [0.0, 1.0].
    """
    if deck_cmc_counts is None or cmc is None:
        return 0.5
    bucket = min(int(cmc), 6)
    total = sum(deck_cmc_counts.values()) or 1
    actual = deck_cmc_counts.get(bucket, 0) / total
    target = _TARGET_CMC.get(bucket, 0.10)
    if actual < target:
        return min(1.0, 0.5 + (target - actual) / target * 0.5)
    return max(0.0, 0.5 - (actual - target) / target * 0.5)


def _type_match_score(row: "asyncpg.Record", type_filter: TypeFilter) -> float:
    """Score a card by requested types, subtypes, and printed keywords.

    Returns a [0.0, 1.0] value proportional to the fraction of requested filter
    terms the card satisfies. A card with no matches scores 0.0.

    Args:
        row: DB row with card_types, subtypes, and keywords.
        type_filter: Parsed type, subtype, and keyword preferences.

    Returns:
        Match fraction in [0.0, 1.0].
    """
    requested_count = (
        len(type_filter.card_types) + len(type_filter.subtypes) + len(type_filter.keywords)
    )
    if not requested_count:
        return 0.0

    card_types = set(row["card_types"])
    subtypes = set(row["subtypes"])
    card_keywords = {k.lower() for k in row["keywords"]}

    per_category = (
        (type_filter.card_types, card_types & set(type_filter.card_types)),
        (type_filter.subtypes, subtypes & set(type_filter.subtypes)),
        (type_filter.keywords, card_keywords & {k.lower() for k in type_filter.keywords}),
    )
    if type_filter.match_all_categories:
        for requested, matched_set in per_category:
            if requested and not matched_set:
                return 0.0

    matched = sum(len(matched_set) for _, matched_set in per_category)
    return matched / requested_count


def _build_representation_query(
    query_tags: list[str],
    type_filter: TypeFilter | None,
) -> RepresentationQuery | None:
    """Build deterministic representation terms from parsed query context."""
    query = RepresentationQuery(
        tags=list(query_tags),
        card_types=list(type_filter.card_types) if type_filter else [],
        subtypes=list(type_filter.subtypes) if type_filter else [],
        keywords=list(type_filter.keywords) if type_filter else [],
    )
    if _representation_term_count(query) == 0:
        return None
    return query


def _representation_match_score(row: "asyncpg.Record", query: RepresentationQuery) -> float:
    """Score deterministic feature overlap between a card row and query terms."""
    requested = _representation_term_count(query)
    if requested == 0:
        return 0.0

    tag_matches = set(row["tags"]) & set(query.tags)
    type_matches = set(row["card_types"]) & set(query.card_types)
    subtype_matches = set(row["subtypes"]) & set(query.subtypes)
    keyword_matches = {k.lower() for k in row["keywords"]} & {k.lower() for k in query.keywords}
    matched = len(tag_matches) + len(type_matches) + len(subtype_matches) + len(keyword_matches)
    return matched / requested


def _representation_term_count(query: RepresentationQuery) -> int:
    return len(query.tags) + len(query.card_types) + len(query.subtypes) + len(query.keywords)


def _color_affinity_score(
    card_colors: list[str],
    commander_colors: set[str],
) -> float:
    """Score card-commander color identity overlap in [0.0, 1.0].

    Colorless cards in colored decks receive a dynamic penalty that scales
    with commander color count: fewer colors = stricter penalty.

    Args:
        card_colors: Card's color identity letters.
        commander_colors: Commander's color identity as a set.

    Returns:
        1.0 for full overlap, scaled [0.16, 0.40] for colorless cards, proportional otherwise.
    """
    if not commander_colors:
        return 1.0
    if not card_colors:
        # Scale: 1-color→0.16, 2-color→0.22, 3-color→0.28, 4-color→0.34, 5-color→0.40
        return 0.1 + 0.06 * len(commander_colors)
    overlap = sum(1 for c in card_colors if c in commander_colors)
    return overlap / len(card_colors)


# Fixed source-evidence weights (never user-tunable).
_W_SYNERGY: float = 0.47
_W_POPULARITY: float = 0.10
_W_CURVE: float = 0.10
_W_COLOR: float = 0.05
_W_REPRESENTATION: float = 0.08

_MULTI_TAG_SYNERGY_EXEMPT = frozenset({"theme", "bangers"})
_MULTI_TAG_SYNERGY_THRESHOLD = 3
_MULTI_TAG_SYNERGY_DAMPEN = 0.7


@dataclass(frozen=True)
class _ScoreContext:
    tag_overlaps: dict[UUID, int]
    fts_set: set[UUID]
    commander_colors: set[str]
    deck_cmc_counts: dict[int, int] | None
    type_filter: TypeFilter | None
    stage: str | None
    representation_query: RepresentationQuery | None
    max_overlap: int
    max_rank: int
    synergy_base_weight: float


@dataclass(frozen=True)
class _ScoreComponents:
    synergy: float
    popularity: float
    curve: float
    color: float
    representation: float


def _build_score_context(
    all_ids: list[UUID],
    *,
    tag_overlaps: dict[UUID, int],
    fts_set: set[UUID],
    cards_by_id: dict[UUID, "asyncpg.Record"],
    commander_color_identity: list[str],
    deck_cmc_counts: dict[int, int] | None,
    type_filter: TypeFilter | None,
    stage: str | None,
    prefer_keywords: bool,
    representation_query: RepresentationQuery | None,
) -> _ScoreContext:
    synergy_base_weight = _W_SYNERGY
    if prefer_keywords:
        synergy_base_weight += 0.05
    ranks = [
        cards_by_id[uid]["edhrec_rank"]
        for uid in all_ids
        if uid in cards_by_id and cards_by_id[uid]["edhrec_rank"] is not None
    ]
    return _ScoreContext(
        tag_overlaps=tag_overlaps,
        fts_set=fts_set,
        commander_colors=set(commander_color_identity),
        deck_cmc_counts=deck_cmc_counts,
        type_filter=type_filter,
        stage=stage,
        representation_query=representation_query,
        max_overlap=max(tag_overlaps.values(), default=1) or 1,
        max_rank=max(ranks, default=1) or 1,
        synergy_base_weight=synergy_base_weight,
    )


def _score_components(uid: UUID, row: "asyncpg.Record", context: _ScoreContext) -> _ScoreComponents:
    raw_overlap = context.tag_overlaps.get(uid, 0)
    fts_bonus = 0.15 if uid in context.fts_set else 0.0
    synergy = min(1.0, (raw_overlap / context.max_overlap) + fts_bonus)
    if (
        raw_overlap >= _MULTI_TAG_SYNERGY_THRESHOLD
        and context.stage not in _MULTI_TAG_SYNERGY_EXEMPT
    ):
        synergy *= _MULTI_TAG_SYNERGY_DAMPEN
    rank = row["edhrec_rank"]
    popularity = 0.0
    if rank is not None:
        popularity = max(0.0, 1.0 - math.log1p(rank) / math.log1p(context.max_rank))
    representation = 0.0
    if context.representation_query is not None:
        representation = _representation_match_score(row, context.representation_query)
    return _ScoreComponents(
        synergy=synergy,
        popularity=popularity,
        curve=_curve_fit_score(row["cmc"], context.deck_cmc_counts),
        color=_color_affinity_score(list(row["color_identity"]), context.commander_colors),
        representation=representation,
    )


def _combine_score(
    row: "asyncpg.Record", components: _ScoreComponents, context: _ScoreContext
) -> float:
    representation_weight = _W_REPRESENTATION if context.representation_query is not None else 0.0
    type_weight = 0.0
    type_score = 0.0
    if context.type_filter is not None:
        type_score = _type_match_score(row, context.type_filter)
        if context.type_filter.strict and type_score == 0.0:
            return 0.0
        type_weight = 0.15
    synergy_weight = max(0.0, context.synergy_base_weight - type_weight - representation_weight)
    return (
        synergy_weight * components.synergy
        + type_weight * type_score
        + representation_weight * components.representation
        + _W_COLOR * components.color
        + _W_POPULARITY * components.popularity
        + _W_CURVE * components.curve
    )


def _compute_weighted_scores(
    all_ids: list[UUID],
    *,
    tag_overlaps: dict[UUID, int],
    fts_set: set[UUID],
    cards_by_id: dict[UUID, "asyncpg.Record"],
    commander_color_identity: list[str],
    deck_cmc_counts: dict[int, int] | None,
    type_filter: TypeFilter | None = None,
    stage: str | None = None,
    prefer_keywords: bool = False,
    representation_query: RepresentationQuery | None = None,
) -> dict[UUID, float]:
    """Compute weighted scores for all candidate cards.

    Default weights (no type_filter):
        score = w_synergy   * synergy_score
              + w_popularity* popularity
              + 0.10        * curve_fit
              + 0.05        * color_affinity
              + w_source    * source_inclusion

    With a type filter, 0.15 is reallocated from synergy to a type-score signal.
    Multi-modal cards (3+ tag matches) outside theme/bangers stages have synergy dampened 0.7x.

    Args:
        all_ids: All candidate card UUIDs.
        tag_overlaps: Tag overlap count per card from Postgres.
        fts_set: Set of card UUIDs found via full-text search.
        cards_by_id: Raw DB rows indexed by card UUID.
        commander_color_identity: Commander's color identity letters.
        deck_cmc_counts: Current deck CMC distribution.
        type_filter: Optional parsed type/subtype preferences; activates type boost.
        stage: Current build stage (used to determine synergy damping).
        representation_query: Deterministic feature terms to score against card representation.

    Returns:
        Dict mapping card UUID to final weighted score.
    """
    context = _build_score_context(
        all_ids,
        tag_overlaps=tag_overlaps,
        fts_set=fts_set,
        cards_by_id=cards_by_id,
        commander_color_identity=commander_color_identity,
        deck_cmc_counts=deck_cmc_counts,
        type_filter=type_filter,
        stage=stage,
        prefer_keywords=prefer_keywords,
        representation_query=representation_query,
    )
    scores: dict[UUID, float] = {}
    for uid in all_ids:
        row = cards_by_id.get(uid)
        if row is None:
            continue
        scores[uid] = _combine_score(row, _score_components(uid, row, context), context)
    return scores


def _annotate_type_signals(
    signal_map: dict[UUID, list[str]],
    cards_by_id: dict[UUID, "asyncpg.Record"],
    type_filter: TypeFilter | None,
) -> None:
    """Add 'type' to signal_map for cards that match the type filter.

    No-op when type_filter is None.
    """
    if type_filter is None:
        return
    for uid, row in cards_by_id.items():
        if _type_match_score(row, type_filter) > 0:
            entry = signal_map.setdefault(uid, [])
            if "type" not in entry:
                entry.append("type")


def _annotate_representation_signals(
    signal_map: dict[UUID, list[str]],
    cards_by_id: dict[UUID, "asyncpg.Record"],
    representation_query: RepresentationQuery | None,
) -> None:
    """Add 'representation' for cards matching deterministic feature terms."""
    if representation_query is None:
        return
    for uid, row in cards_by_id.items():
        if _representation_match_score(row, representation_query) <= 0.0:
            continue
        entry = signal_map.setdefault(uid, [])
        if "representation" not in entry:
            entry.append("representation")


async def _fetch_excluded_source_card_ids(
    pool: asyncpg.Pool,
    source_tags: frozenset[str] | None,
    commander_color_identity: list[str],
) -> frozenset[UUID] | None:
    """Return canonical cards with a directly selected Oracle-tag membership."""
    if not source_tags:
        return None
    source_ids = [UUID(tag) for tag in source_tags]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cards.id
            FROM cards
            JOIN scryfall_tag_memberships memberships ON memberships.oracle_id = cards.oracle_id
            WHERE cards.is_canonical
              AND cards.color_identity <@ $2::text[]
              AND memberships.tag_id = ANY($1::uuid[])
            """,
            source_ids,
            commander_color_identity,
        )
    return frozenset(row["id"] for row in rows)


def _filter_source_rows(
    rows: list["asyncpg.Record"],
    required_source_tag: str | None,
    excluded_card_ids: frozenset[UUID] | None,
) -> list["asyncpg.Record"]:
    """Apply direct Oracle-tag tab membership without alias expansion."""
    return [
        row
        for row in rows
        if (required_source_tag is None or required_source_tag in set(row["tags"] or []))
        and (excluded_card_ids is None or row["id"] not in excluded_card_ids)
    ]


def _filter_rows_by_stage(
    rows: list["asyncpg.Record"], stage: str | None
) -> list["asyncpg.Record"]:
    """Keep land-stage retrieval factual without assigning card roles."""
    if stage != "lands":
        return rows
    return [row for row in rows if "Land" in (row["type_line"] or "")]


@dataclass(frozen=True)
class _RetrievalRequest:
    query_text: str
    query_tags: list[str]
    commander_color_identity: list[str]
    deck_card_ids: list[UUID]
    limit: int
    offset: int
    stage: str | None
    deck_cmc_counts: dict[int, int] | None
    type_filter: TypeFilter | None
    collection_filter: CollectionFilter | None
    price_filter: PriceFilter | None
    commander_id: UUID | None
    bracket: int | None
    prefer_keywords: bool
    required_source_tag: str | None
    excluded_source_tags: frozenset[str] | None


@dataclass
class _CandidateSearch:
    all_ids: list[UUID]
    tag_overlaps: dict[UUID, int]
    fts_set: set[UUID]
    signal_map: dict[UUID, list[str]]
    excluded_theme_ids: frozenset[UUID] | None


@dataclass(frozen=True)
class _RankingResult:
    top_ids: list[UUID]
    scores: dict[UUID, float]
    signal_map: dict[UUID, list[str]]


def _owned_ids(request: _RetrievalRequest) -> frozenset[UUID] | None:
    if request.collection_filter is None:
        return None
    return request.collection_filter.owned_card_ids


async def _collect_candidate_search(
    pool: asyncpg.Pool, request: _RetrievalRequest
) -> _CandidateSearch:
    exclude_lands = request.stage is not None and request.stage != "lands"
    page_end = request.offset + request.limit
    headroom = page_end + len(request.deck_card_ids)
    pool_size = min(_MAX_INNER_POOL, max(headroom, 50))
    fts_pool_size = min(_MAX_INNER_POOL, max(headroom, 30))
    owned_ids = _owned_ids(request)
    tag_results, fts_ids = await asyncio.gather(
        _search_tags(
            pool,
            request.query_tags,
            request.commander_color_identity,
            request.deck_card_ids,
            exclude_lands=exclude_lands,
            limit=pool_size,
            owned_card_ids=owned_ids,
            price_filter=request.price_filter,
        ),
        _search_fts(
            pool,
            request.query_text,
            request.commander_color_identity,
            request.deck_card_ids,
            exclude_lands=exclude_lands,
            limit=fts_pool_size,
            owned_card_ids=owned_ids,
            price_filter=request.price_filter,
        ),
    )
    tag_overlaps, fts_set, signal_map = _build_signal_map(tag_results, fts_ids)
    excluded_theme_ids = await _fetch_excluded_source_card_ids(
        pool, request.excluded_source_tags, request.commander_color_identity
    )
    return _CandidateSearch(
        all_ids=list({*tag_overlaps, *fts_set}),
        tag_overlaps=tag_overlaps,
        fts_set=fts_set,
        signal_map=signal_map,
        excluded_theme_ids=excluded_theme_ids,
    )


async def _load_candidate_rows(
    pool: asyncpg.Pool,
    request: _RetrievalRequest,
    search: _CandidateSearch,
    excluded_names: set[str],
) -> list["asyncpg.Record"]:
    exclude_lands = request.stage is not None and request.stage != "lands"
    rows = await _fetch_candidates(
        pool,
        search.all_ids,
        exclude_lands=exclude_lands,
        price_filter=request.price_filter,
    )
    if excluded_names:
        rows = [row for row in rows if _normalize_card_name(row["name"]) not in excluded_names]
    rows = _filter_source_rows(rows, request.required_source_tag, search.excluded_theme_ids)
    return _filter_rows_by_stage(rows, request.stage)


def _rank_candidates(
    request: _RetrievalRequest,
    search: _CandidateSearch,
    rows: list["asyncpg.Record"],
) -> _RankingResult:
    cards_by_id = {row["id"]: row for row in rows}
    representation_query = _build_representation_query(request.query_tags, request.type_filter)
    scores = _compute_weighted_scores(
        search.all_ids,
        tag_overlaps=search.tag_overlaps,
        fts_set=search.fts_set,
        cards_by_id=cards_by_id,
        commander_color_identity=request.commander_color_identity,
        deck_cmc_counts=request.deck_cmc_counts,
        type_filter=request.type_filter,
        stage=request.stage,
        prefer_keywords=request.prefer_keywords,
        representation_query=representation_query,
    )
    _annotate_type_signals(search.signal_map, cards_by_id, request.type_filter)
    _annotate_representation_signals(search.signal_map, cards_by_id, representation_query)
    page_end = request.offset + request.limit
    ranked = sorted(scores, key=lambda uid: scores[uid], reverse=True)[:page_end]
    return _RankingResult(
        top_ids=ranked[request.offset : page_end],
        scores=scores,
        signal_map=search.signal_map,
    )


def _build_retrieved_cards(
    rows: list["asyncpg.Record"], ranking: _RankingResult
) -> list[RetrievedCard]:
    cards_by_id = {row["id"]: row for row in rows}
    result: list[RetrievedCard] = []
    seen_names: set[str] = set()
    for uid in ranking.top_ids:
        row = cards_by_id.get(uid)
        if row is None or row["name"] in seen_names:
            continue
        seen_names.add(row["name"])
        result.append(
            RetrievedCard(
                id=row["id"],
                scryfall_id=row["scryfall_id"],
                oracle_id=row["oracle_id"],
                name=row["name"],
                mana_cost=row["mana_cost"],
                cmc=row["cmc"],
                type_line=row["type_line"],
                oracle_text=row["oracle_text"],
                color_identity=list(row["color_identity"]),
                image_uri=row["image_uri"],
                tags=list(row["tags"]),
                edhrec_rank=row["edhrec_rank"],
                power=row["power"],
                toughness=row["toughness"],
                rarity=row["rarity"],
                price_eur_cents=row["price_eur_cents"],
                game_changer=bool(row["game_changer"]),
                score=ranking.scores[uid],
                signals=ranking.signal_map.get(uid, []),
            )
        )
    return result


async def _retrieve_candidates(
    pool: asyncpg.Pool, request: _RetrievalRequest
) -> list[RetrievedCard]:
    if _owned_ids(request) == frozenset():
        return []
    excluded_names = await _excluded_nonbasic_names(pool, request.deck_card_ids)
    search = await _collect_candidate_search(pool, request)
    if not search.all_ids:
        return []
    rows = await _load_candidate_rows(pool, request, search, excluded_names)
    ranking = _rank_candidates(request, search, rows)
    return _build_retrieved_cards(rows, ranking)


async def retrieve_candidates(
    pool: asyncpg.Pool,
    query_text: str,
    query_tags: list[str],
    commander_color_identity: list[str],
    deck_card_ids: list[UUID],
    *,
    limit: int = 40,
    offset: int = 0,
    stage: str | None = None,
    deck_cmc_counts: dict[int, int] | None = None,
    type_filter: TypeFilter | None = None,
    collection_filter: CollectionFilter | None = None,
    price_filter: PriceFilter | None = None,
    commander_id: UUID | None = None,
    bracket: int | None = None,
    prefer_keywords: bool = False,
    required_source_tag: str | None = None,
    excluded_source_tags: frozenset[str] | None = None,
) -> list[RetrievedCard]:
    """Run structured retrieval and return top candidate cards with weighted scoring.

    Combines tag (Postgres GIN), full-text (Postgres FTS), source tag inclusion,
    top commander picks, and deterministic card representation matches.

    Args:
        pool: asyncpg connection pool.
        query_text: Text describing desired cards.
        query_tags: Pre-parsed tags for GIN search.
        commander_color_identity: Commander's color identity letters.
        deck_card_ids: Cards already in the deck (excluded from results).
        limit: Number of top candidates to return.
        stage: Current build stage; land cards are excluded when stage != "lands".
        deck_cmc_counts: Deck's current CMC distribution for curve fit scoring.
        type_filter: Optional type/subtype preferences for soft score boosting.
        collection_filter: When set, restricts candidates to owned cards.
        price_filter: When set, excludes cards above the EUR cap (nonfoil).
        commander_id: Retained request context for callers.
        bracket: Deck bracket.
        prefer_keywords: When True (deck supplies explicit archetype keywords),
            slightly increases tag/keyword synergy weight.
        required_source_tag: For a selected theme tab, require direct Oracle-tag membership.
        excluded_source_tags: For the Etc theme tab, exclude cards that belong to
            any selected deck Oracle tag.

    Returns:
        List of RetrievedCard ordered by final weighted score descending.
    """
    request = _RetrievalRequest(
        query_text=query_text,
        query_tags=query_tags,
        commander_color_identity=commander_color_identity,
        deck_card_ids=deck_card_ids,
        limit=limit,
        offset=offset,
        stage=stage,
        deck_cmc_counts=deck_cmc_counts,
        type_filter=type_filter,
        collection_filter=collection_filter,
        price_filter=price_filter,
        commander_id=commander_id,
        bracket=bracket,
        prefer_keywords=prefer_keywords,
        required_source_tag=required_source_tag,
        excluded_source_tags=excluded_source_tags,
    )
    return await _retrieve_candidates(pool, request)


async def _fetch_candidates(
    pool: asyncpg.Pool,
    ids: list[UUID],
    *,
    exclude_lands: bool = False,
    price_filter: PriceFilter | None = None,
) -> list["asyncpg.Record"]:
    """Fetch full card data from Postgres for the given card IDs.

    Args:
        pool: asyncpg connection pool.
        ids: Card UUIDs to fetch.
        exclude_lands: If True, filter out land cards from results.
        price_filter: When set, drops cards with no EUR price or EUR > cap.

    Returns:
        List of raw asyncpg records.
    """
    land_filter = "AND type_line NOT LIKE '%Land%'" if exclude_lands else ""
    params: list = [ids]
    price_clause = _build_price_clause(price_filter, params)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id, scryfall_id, oracle_id, name, mana_cost, cmc, type_line, oracle_text,
                   color_identity, image_uri,
                    COALESCE((
                        SELECT array_agg(m.tag_id::text ORDER BY m.tag_id)
                        FROM scryfall_tag_memberships m
                        WHERE m.oracle_id = cards.oracle_id
                    ), '{{}}') AS tags,
                   edhrec_rank, power, toughness, rarity, game_changer,
                    card_types, subtypes, keywords,
                   CASE
                       WHEN (prices->>'eur') IS NULL THEN NULL
                       ELSE ROUND((prices->>'eur')::numeric * 100)::integer
                   END AS price_eur_cents
            FROM cards
            WHERE id = ANY($1::uuid[])
              AND is_canonical
              AND COALESCE(border_color, '') != 'gold'
              AND COALESCE(security_stamp, '') != 'acorn'
              AND type_line NOT LIKE '%Conspiracy%'
              {land_filter}
              {price_clause}
            """,
            *params,
        )
    return list(rows)
