"""Runtime feature flags with optional per-account overrides.

Resolution order for :func:`is_enabled`: a per-account override row wins,
then a global override row (``account_id IS NULL``), then the env default
passed by the caller. Admins set/clear overrides via the admin router; the
env default ships flags off so an expensive feature stays dark until enabled.
"""

from typing import Any, Literal
from uuid import UUID

import asyncpg

FLAG_OPTIMIZER = "optimizer"
FeatureFlag = Literal["optimizer"]


async def is_enabled(
    pool: asyncpg.Pool, flag: FeatureFlag, account_id: UUID | None, default: bool
) -> bool:
    """Resolve a flag for an account.

    Args:
        pool: asyncpg connection pool.
        flag: Flag key, e.g. :data:`FLAG_OPTIMIZER`.
        account_id: The calling account, or ``None`` to resolve only the
            global/default value.
        default: Env-level fallback when no override row exists.

    Returns:
        The resolved boolean: account override, else global override, else
        ``default``.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT account_id, enabled FROM feature_flags "
            "WHERE flag = $1 AND (account_id = $2 OR account_id IS NULL)",
            flag,
            account_id,
        )
    by_scope = {row["account_id"]: row["enabled"] for row in rows}
    if account_id is not None and account_id in by_scope:
        return by_scope[account_id]
    if None in by_scope:
        return by_scope[None]
    return default


async def set_flag(
    pool: asyncpg.Pool, flag: FeatureFlag, enabled: bool, account_id: UUID | None = None
) -> None:
    """Upsert a global (``account_id`` omitted) or per-account flag override."""
    async with pool.acquire() as conn:
        if account_id is None:
            await conn.execute(
                "INSERT INTO feature_flags (flag, account_id, enabled) VALUES ($1, NULL, $2) "
                "ON CONFLICT (flag) WHERE account_id IS NULL "
                "DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now()",
                flag,
                enabled,
            )
        else:
            await conn.execute(
                "INSERT INTO feature_flags (flag, account_id, enabled) VALUES ($1, $2, $3) "
                "ON CONFLICT (flag, account_id) WHERE account_id IS NOT NULL "
                "DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now()",
                flag,
                account_id,
                enabled,
            )


async def clear_flag(pool: asyncpg.Pool, flag: FeatureFlag, account_id: UUID | None = None) -> None:
    """Delete a global or per-account override, reverting to the next scope."""
    async with pool.acquire() as conn:
        if account_id is None:
            await conn.execute(
                "DELETE FROM feature_flags WHERE flag = $1 AND account_id IS NULL", flag
            )
        else:
            await conn.execute(
                "DELETE FROM feature_flags WHERE flag = $1 AND account_id = $2", flag, account_id
            )


async def list_flags(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return all override rows for admin inspection, global rows first."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT flag, account_id, enabled, updated_at FROM feature_flags "
            "ORDER BY flag, account_id NULLS FIRST"
        )
    return [dict(row) for row in rows]
