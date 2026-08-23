"""Local dev database bootstrap: schema, Scryfall cards, keywords, hubs, tags.

Run from backend/ with the local DATABASE_URL in backend/.env. Uses the same
services as the production admin pipeline but without HTTP auth.
"""

import argparse
import asyncio
import logging

import asyncpg

from mtg_helper.db import apply_schema
from mtg_helper.services import (
    archidekt_tag_service,
    moxfield_hub_service,
    mtgjson,
    scryfall,
    tag_service,
    theme_service,
)


async def _run(phase: str, coro: object) -> None:
    print(f"[{phase}] started", flush=True)
    result = await coro
    print(f"[{phase}] done: {result}", flush=True)


async def main() -> None:  # noqa: C901 - dev CLI with sequential optional phases
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        nargs="*",
        choices=[
            "schema",
            "analyze",
            "cards",
            "keywords",
            "hubs",
            "hub_stats",
            "archidekt",
            "tags",
            "groups",
        ],
        default=None,
    )
    args = parser.parse_args()
    only = set(args.only) if args.only else None

    logging.basicConfig(level=logging.WARNING)
    from mtg_helper.config import settings

    pool = await asyncpg.create_pool(settings.database_url)
    try:
        if only is None or "schema" in only:
            await _run("schema", apply_schema(pool))
        if only is None or "analyze" in only:
            # Give the planner real stats on the (empty) deck tables before the
            # bulk card load, so joins avoid scanning the large cards table.
            async with pool.acquire() as conn:
                await conn.execute("ANALYZE deck_cards")
                await conn.execute("ANALYZE decks")
                await conn.execute("ANALYZE deck_card_plans")
            print("[analyze] done", flush=True)
        if only is None or "cards" in only:
            await _run("scryfall", scryfall.run_sync(pool))
        if only is None or "keywords" in only:
            await _run("mtgjson-keywords", mtgjson.sync_keywords(pool))
        if only is None or "hubs" in only:
            await _run("moxfield-hub-catalog", moxfield_hub_service.sync_hubs(pool))
        if only is None or "hub_stats" in only:
            await _run("moxfield-hub-stats", moxfield_hub_service.sync_hub_card_stats(pool))
        if only is None or "archidekt" in only:
            await _run("archidekt-tags", archidekt_tag_service.sync_tags(pool))
        if only is None or "groups" in only:
            await _run("theme-groups", theme_service.seed_groups(pool))
        if only is None or "tags" in only:
            await _run("card-tags", tag_service.run_batch_tag(pool))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
