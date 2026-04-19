"""asyncpg connection pool management."""

from pathlib import Path

import asyncpg

_SCHEMA_PATH = Path(__file__).parent / "sql" / "schema.sql"


async def create_pool(dsn: str) -> asyncpg.Pool:
    """Create and return an asyncpg connection pool.

    Args:
        dsn: PostgreSQL connection string.

    Returns:
        An initialized asyncpg Pool.
    """
    return await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10)


async def apply_schema(pool: asyncpg.Pool) -> None:
    """Run schema.sql against the pool to ensure schema is up to date.

    schema.sql is written to be fully idempotent (IF NOT EXISTS / DROP IF
    EXISTS / CREATE OR REPLACE), so running it on every startup applies any
    pending migrations without affecting existing data.

    Args:
        pool: asyncpg connection pool.
    """
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def close_pool(pool: asyncpg.Pool) -> None:
    """Gracefully close the asyncpg connection pool.

    Args:
        pool: The pool to close.
    """
    await pool.close()
