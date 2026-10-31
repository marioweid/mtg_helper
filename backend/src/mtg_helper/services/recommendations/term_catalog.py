"""Bounded source-menu expansion using commander facts, never private deck contents."""

import json
from uuid import UUID

import asyncpg

from mtg_helper.models.recommendations import DiscoverTerms
from mtg_helper.services.recommendations.source import Card
from mtg_helper.services.recommendations.strategy_discover import source_terms

TAG_LIMIT = 160
KEYWORD_LIMIT = 120


async def suggestion_catalog(
    conn: asyncpg.Connection, commanders: list[Card], prose: str
) -> DiscoverTerms:
    """Retain strategy retrieval and add source-local commander relationships and descriptions."""
    baseline = await source_terms(conn, prose=prose)
    commander_text = " ".join([prose, *(card.get("oracle_text") or "" for card in commanders)])
    related = await source_terms(conn, prose=commander_text)
    direct = await conn.fetch(
        "SELECT DISTINCT t.id,t.slug,t.metadata FROM scryfall_tags t "
        "JOIN scryfall_tag_memberships m ON m.tag_id=t.id "
        "WHERE m.oracle_id=ANY($1::uuid[]) ORDER BY t.slug,t.id",
        [UUID(card["oracle_id"]) for card in commanders],
    )
    neighbors: set[str] = set()
    for row in direct:
        metadata = json.loads(row["metadata"])
        neighbors.update(metadata.get("parent_ids", []) + metadata.get("child_ids", []))
    candidates = [str(tag["id"]) for tag in baseline.oracle_tags]
    candidates.extend(str(row["id"]) for row in direct)
    candidates.extend(sorted(neighbors))
    candidates.extend(str(tag["id"]) for tag in related.oracle_tags)
    selected = list(dict.fromkeys(candidates))[:TAG_LIMIT]
    rows = await conn.fetch(
        "SELECT id,slug,metadata FROM scryfall_tags WHERE id=ANY($1::uuid[])",
        [UUID(identity) for identity in selected],
    )
    by_id = {str(row["id"]): row for row in rows}
    tags = []
    for identity in selected:
        row = by_id[identity]
        metadata = json.loads(row["metadata"])
        description = metadata.get("description") or ""
        tags.append(
            {
                "id": identity,
                "slug": row["slug"],
                "label": metadata.get("label") or row["slug"],
                "description": description[:600],
                "description_truncated": len(description) > 600,
                "parent_ids": [p for p in metadata.get("parent_ids", []) if p in by_id],
            }
        )
    words = [*baseline.printed_keywords]
    words.extend(word for card in commanders for word in card.get("keywords", []))
    words.extend(related.printed_keywords)
    return DiscoverTerms(
        oracle_tags=tags, printed_keywords=list(dict.fromkeys(words))[:KEYWORD_LIMIT]
    )
