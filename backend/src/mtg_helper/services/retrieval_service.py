"""Structured retrieval service: tags + FTS + trusted inclusion scoring."""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

import asyncpg

from mtg_helper.models.ranking_weights import RankingWeights
from mtg_helper.services import (
    moxfield_hub_service,
    moxfield_recs_service,
    profile_service,
)

_log = logging.getLogger(__name__)

# Target CMC distribution for a typical commander deck (excluding lands/commander).
# Keys are CMC buckets; 6 means "6 or more". Values are target fractions.
_TARGET_CMC: dict[int, float] = {0: 0.05, 1: 0.08, 2: 0.22, 3: 0.25, 4: 0.18, 5: 0.12, 6: 0.10}


@dataclass
class TypeFilter:
    """Parsed type/subtype/keyword/trait preferences from a user query.

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
    traits: list[str] = field(default_factory=list)
    token_types: list[str] = field(default_factory=list)
    strict: bool = False
    match_all_categories: bool = False


@dataclass(frozen=True)
class RepresentationQuery:
    """Structured deterministic terms used for representation scoring."""

    tags: list[str] = field(default_factory=list)
    mtgjson_tags: list[str] = field(default_factory=list)
    card_types: list[str] = field(default_factory=list)
    subtypes: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    token_types: list[str] = field(default_factory=list)


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
    name: str
    mana_cost: str | None
    cmc: Decimal | None
    type_line: str | None
    oracle_text: str | None
    color_identity: list[str]
    image_uri: str | None
    tags: list[str]
    token_types: list[str]
    edhrec_rank: int | None
    power: str | None
    toughness: str | None
    rarity: str | None
    price_eur_cents: int | None
    score: float
    game_changer: bool = False
    signals: list[str] = field(default_factory=list)
    hub_weight: float = 0.0
    moxfield_weight: float = 0.0


# Maps natural-language terms to tag names
_TAG_SYNONYMS: dict[str, list[str]] = {
    "ramp": ["ramp"],
    "mana": ["ramp"],
    "acceleration": ["ramp"],
    "rocking": ["ramp"],
    "draw": ["draw"],
    "card draw": ["draw"],
    "card advantage": ["draw"],
    "cantrip": ["draw"],
    "removal": ["interaction"],
    "kill": ["interaction"],
    "destroy": ["interaction"],
    "exile": ["interaction"],
    "interaction": ["interaction"],
    "interactive": ["interaction"],
    "board wipe": ["interaction"],
    "wrath": ["interaction"],
    "sweeper": ["interaction"],
    "counterspell": ["interaction"],
    "counter": ["interaction"],
    "counters": ["interaction", "plus_one_counters"],
    "tutor": ["tutor"],
    "search": ["tutor"],
    "token": ["tokens"],
    "tokens": ["tokens"],
    "+1/+1": ["plus_one_plus_one_counters"],
    "plus one": ["plus_one_plus_one_counters"],
    "counters strategy": ["plus_one_plus_one_counters"],
    "lifegain": ["lifegain"],
    "life": ["lifegain"],
    "gain life": ["lifegain"],
    "graveyard": ["graveyard"],
    "reanimator": ["graveyard"],
    "recursion": ["graveyard"],
    "graveyard hate": ["interaction"],
    "exile graveyard": ["interaction"],
    "graveyard removal": ["interaction"],
    "sacrifice": ["sacrifice"],
    "sac": ["sacrifice"],
    "aristocrats": ["aristocrats"],
    "death": ["aristocrats"],
    "equipment": ["equipment"],
    "voltron": ["voltron", "equipment"],
    "aura": ["voltron"],
    "stax": ["stax"],
    "tax": ["stax"],
    "group hug": ["group_hug"],
    "hug": ["group_hug"],
    "fast mana": ["fast_mana"],
    "blink": ["blink"],
    "flicker": ["blink"],
    "mill": ["mill"],
    "protection": ["interaction"],
    "hexproof": ["interaction"],
    "indestructible": ["interaction"],
    "extra turn": ["extra_turn"],
    "land destruction": ["land_destruction"],
    "tribal": ["tribal"],
    "cost reduction": ["cost_reduction"],
    "discount": ["cost_reduction"],
    "cheaper": ["cost_reduction"],
    "anthem": ["anthem"],
    "global buff": ["anthem"],
    "lord effect": ["anthem"],
    "proliferate": ["proliferate"],
    "scry": ["card_selection"],
    "surveil": ["card_selection"],
    "card selection": ["card_selection"],
    "filtering": ["card_selection"],
    "treasure": ["treasure"],
    "food token": ["food"],
    "clue token": ["clues"],
    "blood token": ["tokens"],
    "powerstone": ["tokens"],
    "treasure token": ["treasure"],
    # New archetype synonyms (tag_service v2)
    "reanimate": ["reanimator"],
    "reanimation": ["reanimator"],
    "cascade": ["cascade"],
    "storm": ["storm"],
    "landfall": ["landfall"],
    "lands matter": ["landfall"],
    "spellslinger": ["spellslinger"],
    "spells matter": ["spellslinger"],
    "wheels": ["wheels"],
    "wheel": ["wheels"],
    "treasure matters": ["treasure"],
    "treasures matter": ["treasure"],
    "food matters": ["food"],
    "clue matters": ["clues"],
    "infect": ["infect"],
    "toxic": ["infect"],
    "poison": ["infect"],
}

# Token types that can be detected from a query (maps query word → canonical name)
_TOKEN_TYPE_NAMES: dict[str, str] = {
    "treasure": "treasure",
    "food": "food",
    "clue": "clue",
    "blood": "blood",
    "powerstone": "powerstone",
    "map": "map",
    "incubator": "incubator",
    # Creature token types
    "zombie": "zombie",
    "soldier": "soldier",
    "spirit": "spirit",
    "saproling": "saproling",
    "goblin": "goblin",
    "elf": "elf",
    "squirrel": "squirrel",
    "angel": "angel",
    "demon": "demon",
    "dragon": "dragon",
    "elemental": "elemental",
    "beast": "beast",
    "bird": "bird",
    "cat": "cat",
    "human": "human",
    "knight": "knight",
    "warrior": "warrior",
    "thopter": "thopter",
    "servo": "servo",
    "insect": "insect",
    "rat": "rat",
    "snake": "snake",
    "wolf": "wolf",
    "vampire": "vampire",
    "faerie": "faerie",
    "merfolk": "merfolk",
    "plant": "plant",
    "horror": "horror",
}

# Stages that a card auto-cross-counts into based on tags / type. Theme is
# deck-specific (no tag mapping) and is excluded from auto-membership.
_STAGE_TAG_MEMBERSHIP: dict[str, frozenset[str]] = {
    "ramp": frozenset({"ramp", "fast_mana", "cost_reduction"}),
    "draw": frozenset({"draw", "card_draw", "card_selection"}),
    "interaction": frozenset({"interaction"}),
}


def card_qualifying_stages(tags: list[str], type_line: str | None) -> list[str]:
    """Return the build stages this card naturally fits into.

    A card may qualify for multiple stages — e.g. a card tagged both `ramp`
    and `draw` qualifies for both. Lands always qualify for the `lands`
    stage by type and never for the non-land stages (basics auto-tag as
    ``ramp`` from "Add {G}" oracle text — that boost only makes sense for
    nonland cards). `theme` is excluded.

    Args:
        tags: Tag list from `cards.tags`.
        type_line: Card type line (used to detect lands).

    Returns:
        Deduplicated list of stage names.
    """
    is_land = bool(type_line and "Land" in type_line)
    if is_land:
        return ["lands"]
    tag_set = set(tags)
    return [s for s, req in _STAGE_TAG_MEMBERSHIP.items() if tag_set & req]


# Maps stage names to (query_text, query_tags)
_STAGE_QUERIES: dict[str, tuple[str, list[str]]] = {
    "ramp": ("mana ramp acceleration mana rocks mana dorks", ["ramp", "fast_mana"]),
    "draw": ("card draw card advantage cantrips", ["draw"]),
    "interaction": (
        "removal counterspell board wipe protection graveyard hate",
        ["interaction"],
    ),
    "lands": ("lands mana base mana fixing", ["ramp"]),
}


def parse_query_tags(query: str) -> list[str]:
    """Extract tag names from a natural-language query string.

    Args:
        query: Free-form user query or prompt text.

    Returns:
        Deduplicated list of matching tag names.
    """
    q_lower = query.lower()
    found: list[str] = []
    # Try multi-word keys first (longest match), then single words
    keys: list[str] = list(_TAG_SYNONYMS.keys())
    keys.sort(key=len, reverse=True)
    for key in keys:
        if key in q_lower:
            found.extend(_TAG_SYNONYMS[key])
    seen: set[str] = set()
    result: list[str] = []
    for tag in found:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


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

# Maps user query terms/phrases to trait names (longer keys checked first)
_TRAIT_SYNONYMS: dict[str, str] = {
    "enters the battlefield": "etb",
    "enter the battlefield": "etb",
    "activated ability": "activated",
    "activated abilities": "activated",
    "tap ability": "activated",
    "etb": "etb",
    "enters": "etb",
    "activated": "activated",
    "evasion": "evasion",
    "evasive": "evasion",
    "unblockable": "evasion",
}


def _classify_query_word(
    stripped: str,
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
    for queries that don't mention card types, keywords, or traits.

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
    traits: list[str] = []
    token_types: list[str] = []
    seen_types: set[str] = set()
    seen_subs: set[str] = set()
    seen_kw: set[str] = set()
    seen_traits: set[str] = set()
    seen_tokens: set[str] = set()

    for phrase in _KEYWORD_PHRASES:
        if phrase in q_lower and phrase not in seen_kw:
            seen_kw.add(phrase)
            keywords.append(phrase.title())

    for key in sorted(_TRAIT_SYNONYMS, key=len, reverse=True):
        trait = _TRAIT_SYNONYMS[key]
        if key in q_lower and trait not in seen_traits:
            seen_traits.add(trait)
            traits.append(trait)

    for word in q_lower.split():
        stripped = word.strip(".,!?;:'\"")
        _classify_query_word(
            stripped,
            seen_types,
            seen_subs,
            seen_kw,
            card_types,
            subtypes,
            keywords,
        )
        if stripped in _TOKEN_TYPE_NAMES and stripped not in seen_tokens:
            seen_tokens.add(stripped)
            token_types.append(_TOKEN_TYPE_NAMES[stripped])

    if not card_types and not subtypes and not keywords and not traits and not token_types:
        return None

    total_terms = len(card_types) + len(subtypes) + len(keywords) + len(traits) + len(token_types)
    return TypeFilter(
        card_types=card_types,
        subtypes=subtypes,
        keywords=keywords,
        traits=traits,
        token_types=token_types,
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


def _is_land_card(type_line: str | None) -> bool:
    """Return True if the card's type line indicates it is a land."""
    return "Land" in (type_line or "")


async def _search_tags(
    pool: asyncpg.Pool,
    query_tags: list[str],
    commander_color_identity: list[str],
    exclude_ids: list[UUID],
    exclude_lands: bool = False,
    limit: int = 50,
    owned_card_ids: frozenset[UUID] | None = None,
    price_filter: PriceFilter | None = None,
) -> list[tuple[UUID, int]]:
    """Tag-overlap search via Postgres GIN array index.

    Args:
        pool: asyncpg connection pool.
        query_tags: Tags to match against cards.tags.
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
    land_filter = "AND type_line NOT LIKE '%Land%'" if exclude_lands else ""
    params: list = [query_tags, commander_color_identity, exclude_ids, limit]
    collection_filter = ""
    if owned_card_ids is not None:
        params.append(list(owned_card_ids))
        collection_filter = f"AND id = ANY(${len(params)}::uuid[])"
    price_clause = _build_price_clause(price_filter, params)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id,
                   array_length(
                       ARRAY(
                           SELECT unnest(hub_tags || mtgjson_tags)
                           INTERSECT
                           SELECT unnest($1::text[])
                       ), 1
                   ) AS overlap
            FROM cards
            WHERE (
                hub_tags || mtgjson_tags
            ) && $1::text[]
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
                array_length(
                    ARRAY(
                        SELECT unnest(
                            hub_tags || mtgjson_tags
                        )
                        INTERSECT
                        SELECT unnest($1::text[])
                    ), 1
                ) DESC NULLS LAST,
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


def _personal_rating(card_id: UUID, feedback_weights: dict[UUID, float] | None) -> float:
    """Map a feedback weight to a [0, 1] personal rating score.

    Args:
        card_id: Card UUID.
        feedback_weights: Per-card weight multipliers (range [0.05, 2.0]).

    Returns:
        Personal rating in [0.0, 1.0]; 0.5 if no feedback.
    """
    if feedback_weights is None:
        return 0.5
    weight = feedback_weights.get(card_id)
    if weight is None:
        return 0.5
    # Linear map: 0.05 → 0.0, 2.0 → 1.0
    return (weight - 0.05) / 1.95


def _type_match_score(row: "asyncpg.Record", type_filter: TypeFilter) -> float:
    """Score a card based on how many requested types/subtypes/keywords/traits it matches.

    Returns a [0.0, 1.0] value proportional to the fraction of requested filter
    terms the card satisfies. A card with no matches scores 0.0.

    Args:
        row: DB row with card_types, subtypes, keywords, traits fields.
        type_filter: Parsed type/keyword/trait preferences from the user query.

    Returns:
        Match fraction in [0.0, 1.0].
    """
    requested_count = (
        len(type_filter.card_types)
        + len(type_filter.subtypes)
        + len(type_filter.keywords)
        + len(type_filter.traits)
        + len(type_filter.token_types)
    )
    if not requested_count:
        return 0.0

    card_types = set(row["card_types"])
    subtypes = set(row["subtypes"])
    card_keywords = {k.lower() for k in row["keywords"]}
    card_traits = set(row["traits"])
    card_token_types = set(row["token_types"])

    per_category = (
        (type_filter.card_types, card_types & set(type_filter.card_types)),
        (type_filter.subtypes, subtypes & set(type_filter.subtypes)),
        (type_filter.keywords, card_keywords & {k.lower() for k in type_filter.keywords}),
        (type_filter.traits, card_traits & set(type_filter.traits)),
        (type_filter.token_types, card_token_types & set(type_filter.token_types)),
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
        mtgjson_tags=list(query_tags),
        card_types=list(type_filter.card_types) if type_filter else [],
        subtypes=list(type_filter.subtypes) if type_filter else [],
        keywords=list(type_filter.keywords) if type_filter else [],
        traits=list(type_filter.traits) if type_filter else [],
        token_types=list(type_filter.token_types) if type_filter else [],
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
    mtgjson_matches = set(row["mtgjson_tags"]) & set(query.mtgjson_tags)
    type_matches = set(row["card_types"]) & set(query.card_types)
    subtype_matches = set(row["subtypes"]) & set(query.subtypes)
    keyword_matches = {k.lower() for k in row["keywords"]} & {k.lower() for k in query.keywords}
    trait_matches = set(row["traits"]) & set(query.traits)
    token_matches = set(row["token_types"]) & set(query.token_types)
    matched = (
        len(tag_matches)
        + len(mtgjson_matches)
        + len(type_matches)
        + len(subtype_matches)
        + len(keyword_matches)
        + len(trait_matches)
        + len(token_matches)
    )
    return matched / requested


def _representation_term_count(query: RepresentationQuery) -> int:
    return (
        len(query.tags)
        + len(query.mtgjson_tags)
        + len(query.card_types)
        + len(query.subtypes)
        + len(query.keywords)
        + len(query.traits)
        + len(query.token_types)
    )


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


# Default signal weights (no type filter)
_W_SYNERGY: float = 0.22
_W_POPULARITY: float = 0.20
_W_PERSONAL: float = 0.15
# Fixed weights (never user-tunable)
_W_CURVE: float = 0.10
_W_COLOR: float = 0.05
_W_PROFILE: float = 0.03
_W_REPRESENTATION: float = 0.08

_MULTI_TAG_SYNERGY_EXEMPT = frozenset({"theme", "bangers"})
_MULTI_TAG_SYNERGY_THRESHOLD = 3
_MULTI_TAG_SYNERGY_DAMPEN = 0.7


def _compute_weighted_scores(
    all_ids: list[UUID],
    tag_overlaps: dict[UUID, int],
    fts_set: set[UUID],
    cards_by_id: dict[UUID, "asyncpg.Record"],
    commander_color_identity: list[str],
    deck_cmc_counts: dict[int, int] | None,
    feedback_weights: dict[UUID, float] | None,
    user_profile: "profile_service.UserProfile | None" = None,
    type_filter: TypeFilter | None = None,
    stage: str | None = None,
    ranking_weights: RankingWeights | None = None,
    hub_inclusion: dict[UUID, float] | None = None,
    moxfield_inclusion: dict[UUID, float] | None = None,
    prefer_keywords: bool = False,
    representation_query: RepresentationQuery | None = None,
) -> dict[UUID, float]:
    """Compute weighted scores for all candidate cards.

    Default weights (no type_filter):
        score = w_synergy   * synergy_score
              + w_popularity* popularity
              + w_personal  * personal_card_rating
              + 0.10        * curve_fit
              + 0.05        * color_affinity
              + 0.03        * user_profile_score

    The legacy keyword-match weight is folded into synergy so saved ranking
    settings remain compatible after removing vector search. With type_filter, 0.15 is
    reallocated from synergy to a type_score signal.

    Weights come from ``ranking_weights`` when provided; otherwise module defaults apply.
    Multi-modal cards (3+ tag matches) outside theme/bangers stages have synergy dampened 0.7x.

    Args:
        all_ids: All candidate card UUIDs.
        tag_overlaps: Tag overlap count per card from Postgres.
        fts_set: Set of card UUIDs found via full-text search.
        cards_by_id: Raw DB rows indexed by card UUID.
        commander_color_identity: Commander's color identity letters.
        deck_cmc_counts: Current deck CMC distribution.
        feedback_weights: Per-card feedback weight multipliers.
        user_profile: Optional cross-deck user preference profile.
        type_filter: Optional parsed type/subtype preferences; activates type boost.
        stage: Current build stage (used to determine synergy damping).
        ranking_weights: Optional per-user weight overrides.
        representation_query: Deterministic feature terms to score against card representation.

    Returns:
        Dict mapping card UUID to final weighted score.
    """
    w = ranking_weights if ranking_weights is not None else RankingWeights()
    synergy_base_weight = w.synergy + w.semantic
    if prefer_keywords:
        synergy_base_weight += 0.05

    max_overlap = max(tag_overlaps.values(), default=1) or 1
    edhrec_ranks = [
        cards_by_id[uid]["edhrec_rank"]
        for uid in all_ids
        if uid in cards_by_id and cards_by_id[uid]["edhrec_rank"] is not None
    ]
    max_rank = max(edhrec_ranks, default=1) or 1
    cmdr_colors = set(commander_color_identity)

    scores: dict[UUID, float] = {}
    for uid in all_ids:
        row = cards_by_id.get(uid)
        if row is None:
            continue

        raw_overlap = tag_overlaps.get(uid, 0)
        fts_bonus = 0.15 if uid in fts_set else 0.0
        synergy = min(1.0, (raw_overlap / max_overlap) + fts_bonus)
        if raw_overlap >= _MULTI_TAG_SYNERGY_THRESHOLD and stage not in _MULTI_TAG_SYNERGY_EXEMPT:
            synergy *= _MULTI_TAG_SYNERGY_DAMPEN

        rank = row["edhrec_rank"]
        popularity = (
            max(0.0, 1.0 - math.log1p(rank) / math.log1p(max_rank)) if rank is not None else 0.0
        )

        curve = _curve_fit_score(row["cmc"], deck_cmc_counts)
        personal = _personal_rating(uid, feedback_weights)
        color = _color_affinity_score(list(row["color_identity"]), cmdr_colors)

        if user_profile is not None:
            profile_score = profile_service.score_card(user_profile, uid, list(row["tags"]))
        else:
            profile_score = 0.5

        inclusion = hub_inclusion.get(uid, 0.0) if hub_inclusion else 0.0
        mox_inclusion = moxfield_inclusion.get(uid, 0.0) if moxfield_inclusion else 0.0
        representation = (
            _representation_match_score(row, representation_query)
            if representation_query is not None
            else 0.0
        )
        rep_weight = _W_REPRESENTATION if representation_query is not None else 0.0

        if type_filter is not None:
            type_score = _type_match_score(row, type_filter)
            if type_filter.strict and type_score == 0.0:
                scores[uid] = 0.0
                continue
            # With type filter: reallocate 0.15 from synergy to type_score.
            tf_synergy = max(0.0, synergy_base_weight - 0.15 - rep_weight)
            scores[uid] = (
                tf_synergy * synergy
                + 0.15 * type_score
                + rep_weight * representation
                + _W_COLOR * color
                + w.popularity * popularity
                + _W_CURVE * curve
                + w.personal * personal
                + _W_PROFILE * profile_score
                + w.deck_inclusion * inclusion
                + w.moxfield_inclusion * mox_inclusion
            )
        else:
            synergy_weight = max(0.0, synergy_base_weight - rep_weight)
            scores[uid] = (
                synergy_weight * synergy
                + rep_weight * representation
                + _W_COLOR * color
                + w.popularity * popularity
                + _W_CURVE * curve
                + w.personal * personal
                + _W_PROFILE * profile_score
                + w.deck_inclusion * inclusion
                + w.moxfield_inclusion * mox_inclusion
            )

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


def _merge_inclusion_scores(
    primary: dict[UUID, float], secondary: dict[UUID, float]
) -> dict[UUID, float]:
    """Merge trusted inclusion maps by keeping each card's strongest score."""
    merged = dict(primary)
    for uid, score in secondary.items():
        if score > merged.get(uid, 0.0):
            merged[uid] = score
    return merged


def _annotate_hub_signals(
    signal_map: dict[UUID, list[str]],
    hub_inclusion: dict[UUID, float],
    cards_by_id: dict[UUID, "asyncpg.Record"],
) -> None:
    """Add 'hub' to signal_map for cards present in selected Moxfield hubs."""
    for uid, weight in hub_inclusion.items():
        if weight <= 0.0 or uid not in cards_by_id:
            continue
        entry = signal_map.setdefault(uid, [])
        if "hub" not in entry:
            entry.append("hub")


async def _fetch_inclusion_signals(
    pool: asyncpg.Pool,
    commander_id: UUID | None,
    commander_color_identity: list[str],
    bracket: int | None,
    query_tags: list[str],
) -> tuple[dict[UUID, float], dict[UUID, float]]:
    """Fetch Moxfield hub and top-commander-pick scores; swallow source failures."""
    _ = bracket
    hub_inclusion: dict[UUID, float] = {}
    moxfield_inclusion: dict[UUID, float] = {}
    try:
        hub_inclusion = await moxfield_hub_service.score_hubs(
            pool, query_tags, commander_color_identity
        )
    except Exception:
        _log.exception("Moxfield hub inclusion lookup failed; continuing without boost")
    if commander_id is not None:
        try:
            mox_payload = await moxfield_recs_service.get_or_refresh(pool, commander_id)
            moxfield_inclusion = await moxfield_recs_service.score_inclusion(
                pool, mox_payload, commander_color_identity
            )
        except Exception:
            _log.exception("Moxfield inclusion lookup failed; continuing without boost")
    return hub_inclusion, moxfield_inclusion


def _annotate_moxfield_signals(
    signal_map: dict[UUID, list[str]],
    moxfield_inclusion: dict[UUID, float],
    cards_by_id: dict[UUID, "asyncpg.Record"],
) -> None:
    """Add 'top_commander_pick' for cards present in top-liked commander decks."""
    for uid, weight in moxfield_inclusion.items():
        if weight <= 0.0 or uid not in cards_by_id:
            continue
        entry = signal_map.setdefault(uid, [])
        if "top_commander_pick" not in entry:
            entry.append("top_commander_pick")


# Hard cap on the inner candidate pool. Each Load More click bumps the requested
# limit (frontend sends target=80 with the growing exclude list); inner searches
# scale with that limit. 1000 leaves plenty of headroom before stages exhaust.
_MAX_INNER_POOL: int = 1000


def _filter_inclusion_by_stage(
    inclusion: dict[UUID, float],
    cards_by_id: dict[UUID, "asyncpg.Record"],
    stage: str | None,
) -> dict[UUID, float]:
    """Drop trusted Moxfield cards that don't fit the active stage.

    Stages with explicit tag membership (ramp/interaction/draw/utility) keep
    only cards whose tags overlap. The ``lands`` stage keeps only lands. The
    catch-all stages (``theme``, ``bangers``, ``None``) pass through unchanged
    because a high-trust hub or commander-deck card is fair game there.

    Without this filter, the trusted quota injects globally popular staples
    (Sol Ring, Arcane Signet) into every stage's top results, including the
    interaction and draw stages where they have no thematic fit.
    """
    if stage is None or stage in {"theme", "bangers"}:
        return inclusion
    if stage == "lands":
        return {
            uid: w
            for uid, w in inclusion.items()
            if uid in cards_by_id and "Land" in (cards_by_id[uid]["type_line"] or "")
        }
    required = _STAGE_TAG_MEMBERSHIP.get(stage, frozenset())
    if not required:
        return inclusion
    filtered: dict[UUID, float] = {}
    for uid, w in inclusion.items():
        row = cards_by_id.get(uid)
        if row is None:
            continue
        tags = set(row["tags"] or [])
        if tags & required:
            filtered[uid] = w
    return filtered


def _filter_theme_rows(
    rows: list["asyncpg.Record"],
    *,
    required_hub_tag: str | None = None,
    excluded_hub_tags: frozenset[str] | None = None,
    allowed_theme_ids: frozenset[UUID] | None = None,
    excluded_theme_ids: frozenset[UUID] | None = None,
) -> list["asyncpg.Record"]:
    """Keep theme rows in the selected Moxfield hub bucket.

    A concrete theme tab requires exact hub membership. The Etc tab uses
    the inverse: cards that do not belong to any selected deck archetype tag.
    """
    if required_hub_tag is None and not excluded_hub_tags:
        return rows

    filtered: list["asyncpg.Record"] = []
    for row in rows:
        uid = row["id"]
        if (
            required_hub_tag is not None
            and not _row_matches_local_theme_bucket(row, required_hub_tag)
            and uid not in (allowed_theme_ids or frozenset())
        ):
            continue
        if excluded_hub_tags and any(
            _row_matches_local_theme_bucket(row, tag) for tag in excluded_hub_tags
        ):
            continue
        if excluded_theme_ids and uid in excluded_theme_ids:
            continue
        filtered.append(row)
    return filtered


def _row_matches_local_theme_bucket(row: "asyncpg.Record", tag: str) -> bool:
    """Return True when local structured fields prove theme membership."""
    normalized_tag = _normalize_theme_tag(tag)
    row_tags = set(row["hub_tags"] or row["tags"] or [])
    if normalized_tag in row_tags:
        return True
    return False


def _normalize_theme_tag(tag: str) -> str:
    """Normalize one selected theme tag for local bucket comparisons."""
    return tag.strip().lower().replace("-", "_")


def _theme_pinned_uncategorizable(
    trusted: list[tuple[UUID, float]],
    cards_by_id: dict[UUID, "asyncpg.Record"],
    limit: int,
) -> list[UUID]:
    """Return trusted cards with no qualifying stage, capped at ``limit``.

    Used by the theme stage to guarantee top-deck staples that don't match any
    mechanical stage (e.g. enchantress cost-reducers) keep a slot.
    """
    pinned: list[UUID] = []
    for uid, _ in trusted:
        row = cards_by_id.get(uid)
        if row is None:
            continue
        if not card_qualifying_stages(list(row["tags"] or []), row["type_line"]):
            pinned.append(uid)
        if len(pinned) >= limit:
            break
    return pinned


def _apply_trusted_quota(
    scores: dict[UUID, float],
    hub_inclusion: dict[UUID, float],
    moxfield_inclusion: dict[UUID, float],
    cards_by_id: dict[UUID, "asyncpg.Record"],
    limit: int,
    stage: str | None = None,
    quota: float = 1.0,
) -> list[UUID]:
    """Reserve a fraction of the page for trusted cards, fill the rest with composite.

    Ordering of the returned list:

    1. ``theme``-stage uncategorizable pins (cards with no qualifying mechanical
       stage but high trust — see :func:`_theme_pinned_uncategorizable`).
    2. Trusted cards (hub + top commander pick inclusion >= 0 with a positive composite
       score), sorted by trusted score desc then composite score desc. Capped
       at ``floor(limit * quota)`` slots so the composite channel always has
       room to surface keyword/text winners when ``quota < 1.0``. A card
       present in all 10 top Moxfield decks (trust = 1.0) therefore ranks
       above one in 5 decks (trust = 0.5).
    3. Composite-ranked fill (keyword + FTS scoring) for any
       remaining slots up to ``limit``.

    The result is then truncated to ``limit`` so over-allocation from large
    trusted pools is bounded; pagination at the caller (``retrieve_candidates``)
    walks deeper trusted slices as ``limit = offset + page_size`` grows.

    Args:
        scores: Final composite scores per card UUID.
        hub_inclusion: Moxfield hub inclusion scores per card UUID.
        moxfield_inclusion: Top commander pick scores per card UUID.
        cards_by_id: Raw DB rows indexed by card UUID.
        limit: Maximum number of UIDs to return (page_end in pagination terms).
        stage: Active build stage; controls the theme uncategorizable-pin pass.
        quota: Fraction of ``limit`` reserved for trusted cards. ``1.0`` keeps
            the historical "all trusted first" behavior; ``0.5`` yields the
            50/50 mix that lets keyword/text winners share the page.

    Returns:
        Ordered list of UUIDs: pinned + trusted (capped by quota) + composite
        fill, truncated to ``limit``.
    """
    if limit <= 0:
        return []

    composite_ranked = sorted(scores, key=lambda uid: scores[uid], reverse=True)

    trusted: list[tuple[UUID, float]] = []
    for uid in {*hub_inclusion, *moxfield_inclusion}:
        if uid not in cards_by_id or scores.get(uid, 0.0) <= 0.0:
            continue
        trusted_score = max(hub_inclusion.get(uid, 0.0), moxfield_inclusion.get(uid, 0.0))
        if trusted_score <= 0.0:
            continue
        trusted.append((uid, trusted_score))

    trusted.sort(key=lambda item: (item[1], scores.get(item[0], 0.0)), reverse=True)

    pinned = _theme_pinned_uncategorizable(trusted, cards_by_id, limit) if stage == "theme" else []
    pinned_set = set(pinned)

    # Pinned cards count against the trusted budget so the page total stays bounded.
    trusted_budget = max(0, int(limit * quota) - len(pinned))
    reserved = [uid for uid, _ in trusted if uid not in pinned_set][:trusted_budget]
    reserved_set = pinned_set | set(reserved)

    remaining = max(0, limit - len(pinned) - len(reserved))
    fill = [uid for uid in composite_ranked if uid not in reserved_set][:remaining]
    return (pinned + reserved + fill)[:limit]


async def retrieve_candidates(
    pool: asyncpg.Pool,
    query_text: str,
    query_tags: list[str],
    commander_color_identity: list[str],
    deck_card_ids: list[UUID],
    limit: int = 40,
    *,
    offset: int = 0,
    stage: str | None = None,
    deck_cmc_counts: dict[int, int] | None = None,
    feedback_weights: dict[UUID, float] | None = None,
    user_profile: "profile_service.UserProfile | None" = None,
    type_filter: TypeFilter | None = None,
    ranking_weights: RankingWeights | None = None,
    collection_filter: CollectionFilter | None = None,
    price_filter: PriceFilter | None = None,
    commander_id: UUID | None = None,
    bracket: int | None = None,
    prefer_keywords: bool = False,
    required_hub_tag: str | None = None,
    excluded_hub_tags: frozenset[str] | None = None,
) -> list[RetrievedCard]:
    """Run structured retrieval and return top candidate cards with weighted scoring.

    Combines tag (Postgres GIN), full-text (Postgres FTS), Moxfield hub inclusion,
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
        feedback_weights: Optional per-card score multipliers (range [0.05, 2.0]).
        user_profile: Optional cross-deck user preference profile.
        type_filter: Optional type/subtype preferences for soft score boosting.
        ranking_weights: Optional per-user signal weight overrides.
        collection_filter: When set, restricts candidates to owned cards.
        price_filter: When set, excludes cards above the EUR cap (nonfoil).
        commander_id: When set, fetches top Moxfield commander-deck picks and
            applies the commander-pick ranking signal.
        bracket: Deck bracket.
        prefer_keywords: When True (deck supplies explicit archetype keywords),
            slightly increases tag/keyword synergy weight.
        required_hub_tag: For a selected theme tab, require exact hub membership
            so unrelated trusted cards cannot leak into the tab.
        excluded_hub_tags: For the Etc theme tab, exclude cards that belong to
            any selected deck archetype hub.

    Returns:
        List of RetrievedCard ordered by final weighted score descending.
    """
    exclude_lands = stage is not None and stage != "lands"
    owned_ids = collection_filter.owned_card_ids if collection_filter else None
    if owned_ids == frozenset():
        return []
    excluded_names = await _excluded_nonbasic_names(pool, deck_card_ids)

    # Build a deep enough ranked list to satisfy ``offset + limit`` (Load More
    # paginates through positions, not via a growing exclude list). The pool
    # is also padded for cards already in the deck since those get filtered.
    page_end = offset + limit
    headroom = page_end + len(deck_card_ids)
    pool_size = min(_MAX_INNER_POOL, max(headroom, 50))
    fts_pool_size = min(_MAX_INNER_POOL, max(headroom, 30))

    tag_results, fts_ids = await asyncio.gather(
        _search_tags(
            pool,
            query_tags,
            commander_color_identity,
            deck_card_ids,
            exclude_lands=exclude_lands,
            limit=pool_size,
            owned_card_ids=owned_ids,
            price_filter=price_filter,
        ),
        _search_fts(
            pool,
            query_text,
            commander_color_identity,
            deck_card_ids,
            exclude_lands=exclude_lands,
            limit=fts_pool_size,
            owned_card_ids=owned_ids,
            price_filter=price_filter,
        ),
    )

    tag_overlaps, fts_set, signal_map = _build_signal_map(tag_results, fts_ids)

    hub_inclusion, moxfield_inclusion = await _fetch_inclusion_signals(
        pool, commander_id, commander_color_identity, bracket, query_tags
    )
    excluded_theme_ids: frozenset[UUID] | None = None
    if excluded_hub_tags:
        try:
            hub_theme_exclusions = set(
                await moxfield_hub_service.score_hubs(
                    pool, list(excluded_hub_tags), commander_color_identity
                )
            )
            excluded_theme_ids = frozenset(hub_theme_exclusions)
        except Exception:
            _log.exception("Moxfield hub exclusion lookup failed; continuing with tag-only Etc")

    # Include Moxfield hub and top-commander-pick matches as candidates so a high-synergy
    # card not surfaced by tag/FTS still has a path into the result set.
    # Must respect ``deck_card_ids`` — the search channels filter against it,
    # but this fallback path bypasses them and would otherwise resurface cards
    # already in the deck.
    deck_exclude = set(deck_card_ids)
    extra_ids = [
        uid
        for uid in {*hub_inclusion, *moxfield_inclusion}
        if uid not in tag_overlaps
        and uid not in fts_set
        and uid not in deck_exclude
        and (owned_ids is None or uid in owned_ids)
    ]
    all_ids = list({*tag_overlaps, *fts_set, *extra_ids})
    if not all_ids:
        return []

    rows = await _fetch_candidates(
        pool, all_ids, exclude_lands=exclude_lands, price_filter=price_filter
    )
    if excluded_names:
        rows = [r for r in rows if _normalize_card_name(r["name"]) not in excluded_names]
    rows = _filter_theme_rows(
        rows,
        required_hub_tag=required_hub_tag,
        excluded_hub_tags=excluded_hub_tags,
        allowed_theme_ids=frozenset(hub_inclusion),
        excluded_theme_ids=excluded_theme_ids,
    )
    cards_by_id = {r["id"]: r for r in rows}

    # Trusted-card boost only fires when the card actually fits the stage —
    # otherwise Sol Ring keeps showing up under "interaction" etc.
    hub_inclusion = _filter_inclusion_by_stage(hub_inclusion, cards_by_id, stage)
    moxfield_inclusion = _filter_inclusion_by_stage(moxfield_inclusion, cards_by_id, stage)
    representation_query = _build_representation_query(query_tags, type_filter)

    scores = _compute_weighted_scores(
        all_ids,
        tag_overlaps,
        fts_set,
        cards_by_id,
        commander_color_identity,
        deck_cmc_counts,
        feedback_weights,
        user_profile,
        type_filter,
        stage=stage,
        ranking_weights=ranking_weights,
        hub_inclusion=hub_inclusion,
        moxfield_inclusion=moxfield_inclusion,
        prefer_keywords=prefer_keywords,
        representation_query=representation_query,
    )

    _annotate_type_signals(signal_map, cards_by_id, type_filter)
    _annotate_representation_signals(signal_map, cards_by_id, representation_query)
    _annotate_hub_signals(signal_map, hub_inclusion, cards_by_id)
    _annotate_moxfield_signals(signal_map, moxfield_inclusion, cards_by_id)
    trusted_quota = ranking_weights.trusted_quota if ranking_weights is not None else 1.0
    full_ranked = _apply_trusted_quota(
        scores,
        hub_inclusion,
        moxfield_inclusion,
        cards_by_id,
        page_end,
        stage=stage,
        quota=trusted_quota,
    )
    top_ids = full_ranked[offset:page_end]
    if not top_ids:
        return []

    result: list[RetrievedCard] = []
    seen_names: set[str] = set()
    for uid in top_ids:
        row = cards_by_id.get(uid)
        if row is None:
            continue
        name = row["name"]
        if name in seen_names:
            continue
        seen_names.add(name)
        result.append(
            RetrievedCard(
                id=row["id"],
                scryfall_id=row["scryfall_id"],
                name=row["name"],
                mana_cost=row["mana_cost"],
                cmc=row["cmc"],
                type_line=row["type_line"],
                oracle_text=row["oracle_text"],
                color_identity=list(row["color_identity"]),
                image_uri=row["image_uri"],
                tags=list(row["tags"]),
                token_types=list(row["token_types"]),
                edhrec_rank=row["edhrec_rank"],
                power=row["power"],
                toughness=row["toughness"],
                rarity=row["rarity"],
                price_eur_cents=row["price_eur_cents"],
                game_changer=bool(row["game_changer"]),
                score=scores[uid],
                signals=signal_map.get(uid, []),
                hub_weight=hub_inclusion.get(uid, 0.0),
                moxfield_weight=moxfield_inclusion.get(uid, 0.0),
            )
        )
    return result


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
            SELECT id, scryfall_id, name, mana_cost, cmc, type_line, oracle_text,
                   color_identity, image_uri,
                   hub_tags AS tags,
                   hub_tags,
                   mtgjson_tags,
                   edhrec_rank, power, toughness, rarity, game_changer,
                   card_types, subtypes, keywords, traits, token_types,
                   CASE
                       WHEN (prices->>'eur') IS NULL THEN NULL
                       ELSE ROUND((prices->>'eur')::numeric * 100)::integer
                   END AS price_eur_cents
            FROM cards
            WHERE id = ANY($1::uuid[])
              AND COALESCE(border_color, '') != 'gold'
              AND COALESCE(security_stamp, '') != 'acorn'
              AND type_line NOT LIKE '%Conspiracy%'
              {land_filter}
              {price_clause}
            """,
            *params,
        )
    return list(rows)
