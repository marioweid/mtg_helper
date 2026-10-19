"""Check the configured application database without bootstrap or write queries."""

import asyncio
import json

import asyncpg

from mtg_helper.config import settings


async def main() -> None:
    """Print database identity and aggregate counts inside a read-only transaction."""
    connection = await asyncpg.connect(settings.database_url, timeout=10)
    try:
        async with connection.transaction(readonly=True):
            row = await connection.fetchrow(
                """
                SELECT current_database() AS database, current_user AS role,
                    (SELECT count(*) FROM accounts) AS accounts,
                    (SELECT count(*) FROM decks) AS decks,
                    (SELECT count(*) FROM collections) AS collections
                """
            )
            assert row is not None
            print(json.dumps(dict(row)))
    finally:
        await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (OSError, asyncpg.PostgresError, TimeoutError) as error:
        raise SystemExit(
            f"Database check failed ({type(error).__name__}); check LAN access and credentials."
        ) from None
