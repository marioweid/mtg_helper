"""Account management service."""

from uuid import UUID

import asyncpg

from mtg_helper.models.accounts import AccountResponse, AccountUpdate


def _row_to_account(row: asyncpg.Record) -> AccountResponse:
    return AccountResponse(
        id=row["id"],
        display_name=row["display_name"],
        email=row["email"] if "email" in row else None,
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


async def upsert_by_google_sub(
    pool: asyncpg.Pool,
    *,
    google_sub: str,
    email: str,
    display_name: str,
) -> AccountResponse:
    """Upsert an account keyed by Google OIDC subject.

    On first login for a given `google_sub`, inserts a new account row.
    On subsequent logins, refreshes `email` (if Google reports a new value)
    and returns the existing row.

    Args:
        pool: asyncpg connection pool.
        google_sub: OIDC `sub` claim from the verified Google ID token.
        email: Email claim from the ID token.
        display_name: Best-effort display name (Google `name` claim or email).

    Returns:
        The matched or newly created account.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO accounts (display_name, google_sub, email)
            VALUES ($1, $2, $3)
            ON CONFLICT (google_sub) DO UPDATE
            SET email = EXCLUDED.email
            RETURNING *
            """,
            display_name,
            google_sub,
            email,
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


async def update_account(
    pool: asyncpg.Pool, account_id: UUID, data: AccountUpdate
) -> AccountResponse | None:
    """Update account metadata. Only provided fields are changed.

    Args:
        pool: asyncpg connection pool.
        account_id: The account's UUID.
        data: Fields to update.

    Returns:
        Updated AccountResponse or None if not found.
    """
    updates = data.model_dump(exclude_none=True)
    if not updates:
        return await get_account(pool, account_id)

    fields = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
    values = list(updates.values())

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE accounts SET {fields} WHERE id = $1 RETURNING *",
            account_id,
            *values,
        )
    return _row_to_account(row) if row else None
