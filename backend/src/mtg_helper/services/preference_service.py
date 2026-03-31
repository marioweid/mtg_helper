"""Account preference service (pet cards, avoid lists, archetypes)."""

from uuid import UUID

import asyncpg

from mtg_helper.models.preferences import PreferenceCreate, PreferenceResponse


class AccountNotFoundError(ValueError):
    """Raised when the referenced account does not exist."""


class CardNotFoundError(ValueError):
    """Raised when the referenced card does not exist in the local DB."""


def _row_to_preference(row: asyncpg.Record, card_name: str | None) -> PreferenceResponse:
    return PreferenceResponse(
        id=row["id"],
        account_id=row["account_id"],
        preference_type=row["preference_type"],
        card_id=row["card_id"],
        card_name=card_name,
        description=row["description"],
        created_at=row["created_at"],
    )


async def create_preference(
    pool: asyncpg.Pool, account_id: UUID, data: PreferenceCreate
) -> PreferenceResponse:
    """Create a new preference for an account.

    Args:
        pool: asyncpg connection pool.
        account_id: The account's UUID.
        data: Preference payload.

    Returns:
        The created PreferenceResponse.

    Raises:
        AccountNotFoundError: If the account does not exist.
        CardNotFoundError: If a card_scryfall_id is provided but not found.
    """
    async with pool.acquire() as conn:
        account_exists = await conn.fetchval("SELECT id FROM accounts WHERE id = $1", account_id)
        if not account_exists:
            raise AccountNotFoundError(f"Account {account_id} not found")

        card_id: UUID | None = None
        card_name: str | None = None
        if data.card_scryfall_id is not None:
            card_row = await conn.fetchrow(
                "SELECT id, name FROM cards WHERE scryfall_id = $1", data.card_scryfall_id
            )
            if card_row is None:
                raise CardNotFoundError(f"Card with Scryfall ID {data.card_scryfall_id} not found")
            card_id = card_row["id"]
            card_name = card_row["name"]

        row = await conn.fetchrow(
            """
            INSERT INTO preferences (account_id, preference_type, card_id, description)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            account_id,
            data.preference_type,
            card_id,
            data.description,
        )

    return _row_to_preference(row, card_name)


async def list_preferences(pool: asyncpg.Pool, account_id: UUID) -> list[PreferenceResponse]:
    """List all preferences for an account, newest first.

    Args:
        pool: asyncpg connection pool.
        account_id: The account's UUID.

    Returns:
        List of PreferenceResponse records.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.*, c.name AS card_name
            FROM preferences p
            LEFT JOIN cards c ON p.card_id = c.id
            WHERE p.account_id = $1
            ORDER BY p.created_at DESC
            """,
            account_id,
        )
    return [_row_to_preference(r, r["card_name"]) for r in rows]


async def delete_preference(pool: asyncpg.Pool, account_id: UUID, preference_id: UUID) -> bool:
    """Delete a preference record.

    Args:
        pool: asyncpg connection pool.
        account_id: The account's UUID (scopes the deletion).
        preference_id: The preference record UUID.

    Returns:
        True if deleted, False if not found.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM preferences WHERE id = $1 AND account_id = $2",
            preference_id,
            account_id,
        )
    return result == "DELETE 1"


async def get_preferences_for_prompt(pool: asyncpg.Pool, account_id: UUID) -> dict[str, list[str]]:
    """Load account preferences grouped by type for AI prompt injection.

    Args:
        pool: asyncpg connection pool.
        account_id: The account's UUID.

    Returns:
        Dict with keys ``pet_cards``, ``avoid_cards``, ``avoid_archetypes``,
        ``general`` each mapping to a list of strings.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.preference_type, p.description, c.name AS card_name
            FROM preferences p
            LEFT JOIN cards c ON p.card_id = c.id
            WHERE p.account_id = $1
            """,
            account_id,
        )

    result: dict[str, list[str]] = {
        "pet_cards": [],
        "avoid_cards": [],
        "avoid_archetypes": [],
        "general": [],
    }
    for row in rows:
        ptype = row["preference_type"]
        if ptype == "pet_card" and row["card_name"]:
            result["pet_cards"].append(row["card_name"])
        elif ptype == "avoid_card" and row["card_name"]:
            result["avoid_cards"].append(row["card_name"])
        elif ptype == "avoid_archetype" and row["description"]:
            result["avoid_archetypes"].append(row["description"])
        elif ptype == "general" and row["description"]:
            result["general"].append(row["description"])

    return result
