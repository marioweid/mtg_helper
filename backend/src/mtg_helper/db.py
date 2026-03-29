"""asyncpg connection pool management."""

import asyncpg


async def create_pool(dsn: str) -> asyncpg.Pool:
    """Create and return an asyncpg connection pool.

    Args:
        dsn: PostgreSQL connection string.

    Returns:
        An initialized asyncpg Pool.
    """
    return await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10)


async def close_pool(pool: asyncpg.Pool) -> None:
    """Gracefully close the asyncpg connection pool.

    Args:
        pool: The pool to close.
    """
    await pool.close()
