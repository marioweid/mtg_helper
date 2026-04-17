"""Per-user ranking weight service."""

from uuid import UUID

import asyncpg

from mtg_helper.models.ranking_weights import (
    RankingWeights,
    RankingWeightsResponse,
    RankingWeightsUpdate,
)

# Tunable signals normalize to this sum; fixed signals (curve/color/profile) are additive.
_TUNABLE_SUM_CAP = 1.0


class AccountNotFoundError(ValueError):
    """Raised when the referenced account does not exist."""


async def get_weights(pool: asyncpg.Pool, account_id: UUID) -> RankingWeightsResponse:
    """Return ranking weights for an account, seeding defaults on first access.

    Args:
        pool: asyncpg connection pool.
        account_id: The account's UUID.

    Returns:
        RankingWeightsResponse with current or default weights.

    Raises:
        AccountNotFoundError: If the account does not exist.
    """
    async with pool.acquire() as conn:
        account_exists = await conn.fetchval("SELECT id FROM accounts WHERE id = $1", account_id)
        if not account_exists:
            raise AccountNotFoundError(f"Account {account_id} not found")

        row = await conn.fetchrow(
            "SELECT * FROM account_ranking_weights WHERE account_id = $1", account_id
        )
        if row is None:
            defaults = RankingWeights()
            row = await conn.fetchrow(
                """
                INSERT INTO account_ranking_weights
                    (account_id, semantic, synergy, popularity, personal)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (account_id) DO UPDATE SET account_id = EXCLUDED.account_id
                RETURNING *
                """,
                account_id,
                defaults.semantic,
                defaults.synergy,
                defaults.popularity,
                defaults.personal,
            )
    return _row_to_response(row)


async def update_weights(
    pool: asyncpg.Pool, account_id: UUID, data: RankingWeightsUpdate
) -> RankingWeightsResponse:
    """Update ranking weights, normalizing if the tunable sum exceeds cap.

    Args:
        pool: asyncpg connection pool.
        account_id: The account's UUID.
        data: New weight values.

    Returns:
        Updated RankingWeightsResponse.

    Raises:
        AccountNotFoundError: If the account does not exist.
    """
    async with pool.acquire() as conn:
        account_exists = await conn.fetchval("SELECT id FROM accounts WHERE id = $1", account_id)
        if not account_exists:
            raise AccountNotFoundError(f"Account {account_id} not found")

        total = data.semantic + data.synergy + data.popularity + data.personal
        if total > _TUNABLE_SUM_CAP:
            scale = _TUNABLE_SUM_CAP / total
            semantic = data.semantic * scale
            synergy = data.synergy * scale
            popularity = data.popularity * scale
            personal = data.personal * scale
        else:
            semantic = data.semantic
            synergy = data.synergy
            popularity = data.popularity
            personal = data.personal

        row = await conn.fetchrow(
            """
            INSERT INTO account_ranking_weights
                (account_id, semantic, synergy, popularity, personal, updated_at)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (account_id) DO UPDATE SET
                semantic   = EXCLUDED.semantic,
                synergy    = EXCLUDED.synergy,
                popularity = EXCLUDED.popularity,
                personal   = EXCLUDED.personal,
                updated_at = now()
            RETURNING *
            """,
            account_id,
            semantic,
            synergy,
            popularity,
            personal,
        )
    return _row_to_response(row)


def _row_to_response(row: asyncpg.Record) -> RankingWeightsResponse:
    return RankingWeightsResponse(
        account_id=row["account_id"],
        semantic=row["semantic"],
        synergy=row["synergy"],
        popularity=row["popularity"],
        personal=row["personal"],
        updated_at=row["updated_at"],
    )
