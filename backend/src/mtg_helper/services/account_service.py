"""Account management service."""

from uuid import UUID

import asyncpg

from mtg_helper.models.accounts import AccountResponse


def _row_to_account(row: asyncpg.Record) -> AccountResponse:
    return AccountResponse(
        id=row["id"],
        display_name=row["display_name"],
        created_at=row["created_at"],
    )


async def create_account(pool: asyncpg.Pool, display_name: str) -> AccountResponse:
    """Create a new account.

    Args:
        pool: asyncpg connection pool.
        display_name: Human-readable name for the account.

    Returns:
        The newly created account.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO accounts (display_name) VALUES ($1) RETURNING *",
            display_name,
        )
    return _row_to_account(row)


async def get_account(pool: asyncpg.Pool, account_id: UUID) -> AccountResponse | None:
    """Fetch an account by ID.

    Args:
        pool: asyncpg connection pool.
        account_id: The account UUID.

    Returns:
        The account, or None if not found.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM accounts WHERE id = $1", account_id)
    return _row_to_account(row) if row else None
