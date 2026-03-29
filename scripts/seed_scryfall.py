"""CLI script to seed the cards table from Scryfall bulk data.

Usage:
    cd backend && uv run python ../scripts/seed_scryfall.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend/src"))

import asyncpg

from mtg_helper.services.scryfall import run_sync


async def main() -> None:
    """Download Scryfall bulk data and upsert all Commander-relevant cards."""
    db_url = os.environ.get(
        "DATABASE_URL", "postgresql://mtg:mtg_dev@localhost:5432/mtg_helper"
    )
    print(f"Connecting to {db_url}...")
    pool = await asyncpg.create_pool(dsn=db_url)

    print("Starting Scryfall sync (this may take a minute)...")
    result = await run_sync(pool)
    await pool.close()

    print(f"Done. {result['cards_processed']} cards processed in {result['duration_seconds']}s")


if __name__ == "__main__":
    asyncio.run(main())
