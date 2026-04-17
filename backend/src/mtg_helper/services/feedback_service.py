"""Deck feedback service (thumbs up/down on card suggestions)."""

from uuid import UUID

import asyncpg

from mtg_helper.models.feedback import FeedbackCreate, FeedbackResponse


class DeckNotFoundError(ValueError):
    """Raised when the referenced deck does not exist."""


class CardNotFoundError(ValueError):
    """Raised when the referenced card does not exist in the local DB."""


class FeedbackNotFoundError(ValueError):
    """Raised when the referenced feedback record does not exist."""


def _row_to_feedback(row: asyncpg.Record, card_name: str) -> FeedbackResponse:
    return FeedbackResponse(
        id=row["id"],
        deck_id=row["deck_id"],
        card_id=row["card_id"],
        card_name=card_name,
        feedback=row["feedback"],
        reject_count=row["reject_count"],
        reason=row["reason"],
        created_at=row["created_at"],
    )


async def add_feedback(pool: asyncpg.Pool, deck_id: UUID, data: FeedbackCreate) -> FeedbackResponse:
    """Submit thumbs-up or thumbs-down feedback for a card in a deck.

    Replaces any existing feedback for the same deck+card combination.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        data: Feedback payload including card scryfall ID and vote.

    Returns:
        The created FeedbackResponse.

    Raises:
        DeckNotFoundError: If the deck does not exist.
        CardNotFoundError: If the card is not in the local DB.
    """
    async with pool.acquire() as conn:
        deck_exists = await conn.fetchval("SELECT id FROM decks WHERE id = $1", deck_id)
        if not deck_exists:
            raise DeckNotFoundError(f"Deck {deck_id} not found")

        card_row = await conn.fetchrow(
            "SELECT id, name FROM cards WHERE scryfall_id = $1", data.card_scryfall_id
        )
        if card_row is None:
            raise CardNotFoundError(f"Card with Scryfall ID {data.card_scryfall_id} not found")

        card_id = card_row["id"]
        card_name = card_row["name"]

        if data.feedback == "reject":
            # Compound rejects: increment count instead of replacing
            row = await conn.fetchrow(
                """
                INSERT INTO deck_feedback (deck_id, card_id, feedback, reject_count, reason)
                VALUES ($1, $2, 'reject', 1, $3)
                ON CONFLICT (deck_id, card_id) DO UPDATE SET
                    feedback     = 'reject',
                    reject_count = CASE
                        WHEN deck_feedback.feedback = 'reject'
                        THEN deck_feedback.reject_count + 1
                        ELSE 1
                    END,
                    reason = EXCLUDED.reason
                RETURNING *
                """,
                deck_id,
                card_id,
                data.reason,
            )
        else:
            row = await conn.fetchrow(
                """
                INSERT INTO deck_feedback (deck_id, card_id, feedback, reject_count, reason)
                VALUES ($1, $2, $3, 0, $4)
                ON CONFLICT (deck_id, card_id) DO UPDATE SET
                    feedback     = EXCLUDED.feedback,
                    reject_count = 0,
                    reason       = EXCLUDED.reason
                RETURNING *
                """,
                deck_id,
                card_id,
                data.feedback,
                data.reason,
            )

    return _row_to_feedback(row, card_name)


async def list_feedback(pool: asyncpg.Pool, deck_id: UUID) -> list[FeedbackResponse]:
    """List all feedback for a deck, newest first.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.

    Returns:
        List of FeedbackResponse records.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT df.*, c.name AS card_name
            FROM deck_feedback df
            JOIN cards c ON df.card_id = c.id
            WHERE df.deck_id = $1
            ORDER BY df.created_at DESC
            """,
            deck_id,
        )
    return [_row_to_feedback(r, r["card_name"]) for r in rows]


async def delete_feedback(pool: asyncpg.Pool, deck_id: UUID, feedback_id: UUID) -> bool:
    """Delete a feedback record.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID (used to scope the deletion).
        feedback_id: The feedback record UUID.

    Returns:
        True if deleted, False if not found.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM deck_feedback WHERE id = $1 AND deck_id = $2",
            feedback_id,
            deck_id,
        )
    return result == "DELETE 1"
