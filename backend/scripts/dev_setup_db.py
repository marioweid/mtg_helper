"""Local development database bootstrap: schema and Scryfall card facts.

Run from backend/ with the local DATABASE_URL in backend/.env. Uses the same
services as the production admin pipeline but without HTTP auth.
"""

import argparse
import asyncio
import logging

import asyncpg

from mtg_helper.db import apply_schema
from mtg_helper.services import scryfall


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
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
