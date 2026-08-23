"""Tag a focused subset of cards (dev helper): decks' cards, hub members, commanders.

Runs the same rule-based classifier as the full pass, but only for a bounded
set of cards so it completes quickly even on a cold database.
"""

import asyncio
import logging

import asyncpg

from mtg_helper.config import settings
from mtg_helper.services.tag_service import (
    classify_card,
    normalize_local_tags,
)

# Classic aristocrats payoffs sometimes missed by the hub sample; tag them so
# theme search still surfaces them via the local-tag supplement.
_EXTRA_NAMES = [
    "Blood Artist",
    "Marionette Apprentice",
    "Nadier's Nightblade",
    "Zulaport Cutthroat",
    "Pitiless Plunderer",
    "Viscera Seer",
    "Bastion of Remembrance",
    "Carrion Feeder",
    "Falkenrath Noble",
    "Cruel Celebrant",
    "Sifter of Skulls",
    "Pawn of Ulamog",
    "Dictate of Erebos",
    "Grave Pact",
    "Syr Konrad, the Grim",
    "Mayhem Devil",
]


async def _target_ids(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Resolve the focused card set through indexed lookups only (no seq scans)."""
    async with pool.acquire() as conn:
        hub_ids = [
            row["card_id"]
            for row in await conn.fetch("SELECT card_id FROM moxfield_hub_card_stats")
        ]
        deck_ids = [
            row["id"]
            for row in await conn.fetch(
                """
                SELECT commander_id AS id FROM decks
                UNION SELECT partner_id FROM decks WHERE partner_id IS NOT NULL
                UNION SELECT card_id FROM deck_cards
                """
            )
        ]
        name_rows = await conn.fetch(
            "SELECT id FROM cards WHERE is_canonical AND name = ANY($1::text[])",
            _EXTRA_NAMES,
        )
        rows = await conn.fetch(
            """
            SELECT c.id, c.name, c.type_line, c.oracle_text, c.keywords, c.cmc
            FROM cards c
            WHERE c.is_canonical AND c.id = ANY($1::uuid[])
            """,
            list(dict.fromkeys([*hub_ids, *deck_ids, *[row["id"] for row in name_rows]])),
        )
    return rows


async def run_focused_tag(pool: asyncpg.Pool) -> int:
    """Tag the focused card subset and return how many cards were updated."""
    rows = await _target_ids(pool)
    updates: list[tuple[list[str], list[str], list[str], list[str], object]] = []
    for r in rows:
        keywords = list(r["keywords"])
        local_tags = classify_card(
            r["name"],
            r["type_line"],
            r["oracle_text"],
            keywords,
            float(r["cmc"]) if r["cmc"] is not None else None,
        )
        local_tags = normalize_local_tags(local_tags)
        from mtg_helper.services.tag_service import classify_token_types, classify_traits

        updates.append(
            (
                local_tags,
                [],
                classify_traits(r["oracle_text"], keywords),
                classify_token_types(r["oracle_text"]),
                r["id"],
            )
        )

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            UPDATE cards
            SET tags = $1, mtgjson_tags = $2, traits = $3, token_types = $4
            WHERE id = $5
            """,
            updates,
        )
    return len(updates)


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    pool = await asyncpg.create_pool(settings.database_url)
    try:
        count = await run_focused_tag(pool)
        print(f"targeted-tagged {count} cards")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
