"""Hybrid retrieval service: semantic + tag + FTS search with weighted scoring."""

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

import asyncpg
import openai
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    HasIdCondition,
    MatchAny,
    MatchValue,
    ScoredPoint,
)

from mtg_helper.config import settings
from mtg_helper.services import profile_service
from mtg_helper.services.embedding_service import embed_single

_log = logging.getLogger(__name__)

_ALL_COLORS = {"W", "U", "B", "R", "G"}

# Target CMC distribution for a typical commander deck (excluding lands/commander).
# Keys are CMC buckets; 6 means "6 or more". Values are target fractions.
_TARGET_CMC: dict[int, float] = {0: 0.05, 1: 0.08, 2: 0.22, 3: 0.25, 4: 0.18, 5: 0.12, 6: 0.10}


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
    edhrec_rank: int | None
    power: str | None
    toughness: str | None
    rarity: str | None
    score: float
    signals: list[str] = field(default_factory=list)


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
    "removal": ["removal"],
    "kill": ["removal"],
    "destroy": ["removal"],
    "exile": ["removal"],
    "interaction": ["removal", "counterspell", "board_wipe", "protection"],
    "interactive": ["removal", "counterspell", "board_wipe"],
    "board wipe": ["board_wipe"],
    "wrath": ["board_wipe"],
    "sweeper": ["board_wipe"],
    "counterspell": ["counterspell"],
    "counter": ["counterspell"],
    "counters": ["counterspell", "plus_one_counters"],
    "tutor": ["tutor"],
    "search": ["tutor"],
    "token": ["token"],
    "tokens": ["token"],
    "+1/+1": ["plus_one_counters"],
    "plus one": ["plus_one_counters"],
    "counters strategy": ["plus_one_counters"],
    "lifegain": ["lifegain"],
    "life": ["lifegain"],
    "gain life": ["lifegain"],
    "graveyard": ["graveyard"],
    "reanimator": ["graveyard"],
    "recursion": ["graveyard"],
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
    "protection": ["protection"],
    "hexproof": ["protection"],
    "indestructible": ["protection"],
    "extra turn": ["extra_turn"],
    "land destruction": ["land_destruction"],
    "tribal": ["tribal"],
}

# Maps stage names to (query_text, query_tags)
_STAGE_QUERIES: dict[str, tuple[str, list[str]]] = {
    "ramp": ("mana ramp acceleration mana rocks mana dorks", ["ramp", "fast_mana"]),
    "interaction": (
        "removal counterspell board wipe protection",
        ["removal", "counterspell", "board_wipe", "protection"],
    ),
    "draw": ("card draw card advantage cantrips", ["draw"]),
    "utility": (
        "utility recursion graveyard toolbox",
        ["tutor", "graveyard", "blink", "protection"],
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


def stage_retrieval_query(stage: str, deck_description: str | None) -> tuple[str, list[str]]:
    """Map a build stage to a (query_text, query_tags) pair for retrieval.

    Appends the deck description to every stage's query text so that
    thematically relevant cards get a semantic boost even in generic
    stages like ramp or draw.

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
    query_tags = list(base[1])
    for tag in parse_query_tags(deck_description):
        if tag not in query_tags:
            query_tags.append(tag)
    return query_text, query_tags


def _excluded_colors(commander_color_identity: list[str]) -> list[str]:
    """Return colors not in the commander's identity."""
    return list(_ALL_COLORS - set(commander_color_identity))


def _is_land_card(type_line: str | None) -> bool:
    """Return True if the card's type line indicates it is a land."""
    return "Land" in (type_line or "")


async def _search_qdrant(
    qdrant_client: AsyncQdrantClient,
    query_vector: list[float],
    commander_color_identity: list[str],
    exclude_ids: list[UUID],
    limit: int = 50,
) -> list[tuple[UUID, float]]:
    """Semantic search via Qdrant cosine similarity.

    Args:
        qdrant_client: Async Qdrant client.
        query_vector: Embedding of the query text.
        commander_color_identity: Commander's color identity letters.
        exclude_ids: Card UUIDs already in the deck (excluded from results).
        limit: Maximum results to return.

    Returns:
        List of (card_uuid, cosine_similarity) pairs, best match first.
    """
    must_conditions: list = [FieldCondition(key="commander_legal", match=MatchValue(value=True))]

    excluded_colors = _excluded_colors(commander_color_identity)
    must_not_conditions: list = []
    if excluded_colors:
        must_not_conditions.append(
            FieldCondition(key="color_identity", match=MatchAny(any=excluded_colors))
        )
    if exclude_ids:
        must_not_conditions.append(HasIdCondition(has_id=[str(uid) for uid in exclude_ids]))

    query_filter = Filter(
        must=must_conditions,
        must_not=must_not_conditions if must_not_conditions else None,
    )

    results: list[ScoredPoint] = await qdrant_client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=limit,
    )
    return [(UUID(str(p.id)), p.score) for p in results]


async def _search_tags(
    pool: asyncpg.Pool,
    query_tags: list[str],
    commander_color_identity: list[str],
    exclude_ids: list[UUID],
    exclude_lands: bool = False,
    limit: int = 50,
) -> list[tuple[UUID, int]]:
    """Tag-overlap search via Postgres GIN array index.

    Args:
        pool: asyncpg connection pool.
        query_tags: Tags to match against cards.tags.
        commander_color_identity: Commander's color identity (subset filter).
        exclude_ids: Card UUIDs to exclude.
        exclude_lands: If True, exclude land cards from results.
        limit: Maximum results to return.

    Returns:
        List of (card_uuid, tag_overlap_count) pairs, highest overlap first.
    """
    if not query_tags:
        return []
    land_filter = "AND type_line NOT LIKE '%Land%'" if exclude_lands else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id,
                   array_length(
                       ARRAY(
                           SELECT unnest(tags)
                           INTERSECT
                           SELECT unnest($1::text[])
                       ), 1
                   ) AS overlap
            FROM cards
            WHERE tags && $1::text[]
              AND color_identity <@ $2::text[]
              AND legalities->>'commander' = 'legal'
              AND id != ALL($3::uuid[])
              {land_filter}
            ORDER BY
                array_length(
                    ARRAY(
                        SELECT unnest(tags)
                        INTERSECT
                        SELECT unnest($1::text[])
                    ), 1
                ) DESC NULLS LAST,
                edhrec_rank ASC NULLS LAST
            LIMIT $4
            """,
            query_tags,
            commander_color_identity,
            exclude_ids,
            limit,
        )
    return [(r["id"], r["overlap"] or 0) for r in rows]


async def _search_fts(
    pool: asyncpg.Pool,
    query_text: str,
    commander_color_identity: list[str],
    exclude_ids: list[UUID],
    exclude_lands: bool = False,
    limit: int = 30,
) -> list[UUID]:
    """Full-text search via Postgres tsvector index.

    Args:
        pool: asyncpg connection pool.
        query_text: Natural language query.
        commander_color_identity: Commander's color identity (subset filter).
        exclude_ids: Card UUIDs to exclude.
        exclude_lands: If True, exclude land cards from results.
        limit: Maximum results to return.

    Returns:
        Ranked list of card UUIDs (best FTS rank first).
    """
    land_filter = "AND type_line NOT LIKE '%Land%'" if exclude_lands else ""
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
              {land_filter}
            ORDER BY
                ts_rank(
                    to_tsvector('english', COALESCE(oracle_text, '')),
                    plainto_tsquery('english', $1)
                ) DESC
            LIMIT $4
            """,
            query_text,
            commander_color_identity,
            exclude_ids,
            limit,
        )
    return [r["id"] for r in rows]


def _build_signal_map(
    semantic_results: list[tuple[UUID, float]],
    tag_results: list[tuple[UUID, int]],
    fts_ids: list[UUID],
) -> tuple[
    dict[UUID, float],
    dict[UUID, int],
    set[UUID],
    dict[UUID, list[str]],
]:
    """Build per-signal score maps and signal membership from individual search results.

    Args:
        semantic_results: (uuid, cosine_score) pairs from Qdrant.
        tag_results: (uuid, overlap_count) pairs from Postgres tag search.
        fts_ids: UUIDs from Postgres FTS search.

    Returns:
        Tuple of (qdrant_scores, tag_overlaps, fts_set, signal_map).
    """
    qdrant_scores: dict[UUID, float] = {uid: score for uid, score in semantic_results}
    tag_overlaps: dict[UUID, int] = {uid: overlap for uid, overlap in tag_results}
    fts_set: set[UUID] = set(fts_ids)
    signal_map: dict[UUID, list[str]] = {}

    for uid in qdrant_scores:
        signal_map.setdefault(uid, []).append("semantic")
    for uid in tag_overlaps:
        if uid not in signal_map or "tag" not in signal_map[uid]:
            signal_map.setdefault(uid, []).append("tag")
    for uid in fts_set:
        entry = signal_map.setdefault(uid, [])
        if "fts" not in entry:
            entry.append("fts")

    return qdrant_scores, tag_overlaps, fts_set, signal_map


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


def _compute_weighted_scores(
    all_ids: list[UUID],
    qdrant_scores: dict[UUID, float],
    tag_overlaps: dict[UUID, int],
    fts_set: set[UUID],
    cards_by_id: dict[UUID, "asyncpg.Record"],
    deck_cmc_counts: dict[int, int] | None,
    feedback_weights: dict[UUID, float] | None,
    user_profile: "profile_service.UserProfile | None" = None,
) -> dict[UUID, float]:
    """Compute weighted scores for all candidate cards.

    Formula:
        score = 0.4 * vector_similarity
              + 0.3 * synergy_score
              + 0.05 * popularity
              + 0.1 * curve_fit
              + 0.1 * personal_card_rating
              + 0.05 * user_profile_score

    Args:
        all_ids: All candidate card UUIDs.
        qdrant_scores: Cosine similarity per card from Qdrant [0, 1].
        tag_overlaps: Tag overlap count per card from Postgres.
        fts_set: Set of card UUIDs found via full-text search.
        cards_by_id: Raw DB rows indexed by card UUID.
        deck_cmc_counts: Current deck CMC distribution.
        feedback_weights: Per-card feedback weight multipliers.
        user_profile: Optional cross-deck user preference profile.

    Returns:
        Dict mapping card UUID to final weighted score.
    """
    max_overlap = max(tag_overlaps.values(), default=1) or 1
    edhrec_ranks = [
        cards_by_id[uid]["edhrec_rank"]
        for uid in all_ids
        if uid in cards_by_id and cards_by_id[uid]["edhrec_rank"] is not None
    ]
    max_rank = max(edhrec_ranks, default=1) or 1

    scores: dict[UUID, float] = {}
    for uid in all_ids:
        row = cards_by_id.get(uid)
        if row is None:
            continue

        # 0.4 — vector similarity (cosine, already [0,1])
        vec_sim = qdrant_scores.get(uid, 0.0)

        # 0.3 — synergy: tag overlap, with FTS membership as a bonus
        raw_overlap = tag_overlaps.get(uid, 0)
        fts_bonus = 0.15 if uid in fts_set else 0.0
        synergy = min(1.0, (raw_overlap / max_overlap) + fts_bonus)

        # 0.05 — popularity (lower edhrec_rank → more popular → higher score)
        rank = row["edhrec_rank"]
        popularity = (1.0 - rank / max_rank) if rank is not None else 0.0

        # 0.1 — curve fit
        curve = _curve_fit_score(row["cmc"], deck_cmc_counts)

        # 0.1 — personal rating from feedback
        personal = _personal_rating(uid, feedback_weights)

        # 0.05 — cross-deck user profile signal
        if user_profile is not None:
            profile_score = profile_service.score_card(user_profile, uid, list(row["tags"]))
        else:
            profile_score = 0.5

        scores[uid] = (
            0.4 * vec_sim
            + 0.3 * synergy
            + 0.05 * popularity
            + 0.1 * curve
            + 0.1 * personal
            + 0.05 * profile_score
        )

    return scores


async def retrieve_candidates(
    pool: asyncpg.Pool,
    ai_client: openai.AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
    query_text: str,
    query_tags: list[str],
    commander_color_identity: list[str],
    deck_card_ids: list[UUID],
    limit: int = 40,
    *,
    stage: str | None = None,
    deck_cmc_counts: dict[int, int] | None = None,
    feedback_weights: dict[UUID, float] | None = None,
    user_profile: "profile_service.UserProfile | None" = None,
) -> list[RetrievedCard]:
    """Run hybrid retrieval and return top candidate cards with weighted scoring.

    Combines semantic (Qdrant), tag (Postgres GIN), and full-text (Postgres FTS)
    search, applies a weighted scoring formula, then fetches full card data.

    Args:
        pool: asyncpg connection pool.
        ai_client: OpenAI async client for query embedding.
        qdrant_client: Qdrant async client for semantic search.
        query_text: Text describing desired cards.
        query_tags: Pre-parsed tags for GIN search.
        commander_color_identity: Commander's color identity letters.
        deck_card_ids: Cards already in the deck (excluded from results).
        limit: Number of top candidates to return.
        stage: Current build stage; land cards are excluded when stage != "lands".
        deck_cmc_counts: Deck's current CMC distribution for curve fit scoring.
        feedback_weights: Optional per-card score multipliers (range [0.05, 2.0]).
        user_profile: Optional cross-deck user preference profile.

    Returns:
        List of RetrievedCard ordered by final weighted score descending.
    """
    exclude_lands = stage is not None and stage != "lands"
    query_vector = await embed_single(ai_client, query_text)

    semantic_results, tag_results, fts_ids = await asyncio.gather(
        _search_qdrant(qdrant_client, query_vector, commander_color_identity, deck_card_ids),
        _search_tags(
            pool,
            query_tags,
            commander_color_identity,
            deck_card_ids,
            exclude_lands=exclude_lands,
        ),
        _search_fts(
            pool,
            query_text,
            commander_color_identity,
            deck_card_ids,
            exclude_lands=exclude_lands,
        ),
    )

    qdrant_scores, tag_overlaps, fts_set, signal_map = _build_signal_map(
        semantic_results, tag_results, fts_ids
    )
    all_ids = list({*qdrant_scores, *tag_overlaps, *fts_set})
    if not all_ids:
        return []

    rows = await _fetch_candidates(pool, all_ids, exclude_lands=exclude_lands)
    cards_by_id = {r["id"]: r for r in rows}

    scores = _compute_weighted_scores(
        all_ids,
        qdrant_scores,
        tag_overlaps,
        fts_set,
        cards_by_id,
        deck_cmc_counts,
        feedback_weights,
        user_profile,
    )
    top_ids = sorted(scores, key=lambda uid: scores[uid], reverse=True)[:limit]
    if not top_ids:
        return []

    result: list[RetrievedCard] = []
    for uid in top_ids:
        row = cards_by_id.get(uid)
        if row is None:
            continue
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
                edhrec_rank=row["edhrec_rank"],
                power=row["power"],
                toughness=row["toughness"],
                rarity=row["rarity"],
                score=scores[uid],
                signals=signal_map.get(uid, []),
            )
        )
    return result


async def _fetch_candidates(
    pool: asyncpg.Pool,
    ids: list[UUID],
    *,
    exclude_lands: bool = False,
) -> list["asyncpg.Record"]:
    """Fetch full card data from Postgres for the given card IDs.

    Args:
        pool: asyncpg connection pool.
        ids: Card UUIDs to fetch.
        exclude_lands: If True, filter out land cards from results.

    Returns:
        List of raw asyncpg records.
    """
    land_filter = "AND type_line NOT LIKE '%Land%'" if exclude_lands else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id, scryfall_id, name, mana_cost, cmc, type_line, oracle_text,
                   color_identity, image_uri, tags, edhrec_rank, power, toughness, rarity
            FROM cards
            WHERE id = ANY($1::uuid[])
              {land_filter}
            """,
            ids,
        )
    return list(rows)
