"""Conversation history persistence for per-deck AI chat."""

from __future__ import annotations

from uuid import UUID

import asyncpg


async def get_turns(pool: asyncpg.Pool, deck_id: UUID) -> list[dict[str, str]]:
    """Fetch all conversation turns for a deck, ordered by turn_order.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.

    Returns:
        List of {role, content} dicts suitable for the chat completions API.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, content FROM conversation_turns"
            " WHERE deck_id = $1 ORDER BY turn_order ASC",
            deck_id,
        )
    return [{"role": r["role"], "content": r["content"]} for r in rows if r["content"]]


async def get_recent_turns(pool: asyncpg.Pool, deck_id: UUID, limit: int) -> list[dict[str, str]]:
    """Fetch the most recent N turns for a deck in chronological order.

    Caps the amount of history replayed into the LLM to keep token usage
    bounded.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        limit: Maximum number of turns to return.

    Returns:
        List of {role, content} dicts in ascending turn order.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, content FROM conversation_turns"
            " WHERE deck_id = $1 ORDER BY turn_order DESC LIMIT $2",
            deck_id,
            limit,
        )
    turns = [{"role": r["role"], "content": r["content"]} for r in rows if r["content"]]
    turns.reverse()
    return turns


async def append_turn(pool: asyncpg.Pool, deck_id: UUID, role: str, content: str) -> None:
    """Append a single conversation turn, auto-incrementing turn_order.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.
        role: "user" or "assistant".
        content: Message content.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversation_turns (deck_id, role, content, turn_order)
            VALUES (
                $1, $2, $3,
                (SELECT COALESCE(MAX(turn_order), 0) + 1
                 FROM conversation_turns WHERE deck_id = $1)
            )
            """,
            deck_id,
            role,
            content,
        )


async def get_turn_count(pool: asyncpg.Pool, deck_id: UUID) -> int:
    """Return the number of conversation turns for a deck.

    Args:
        pool: asyncpg connection pool.
        deck_id: The deck's UUID.

    Returns:
        Total number of turns.
    """
    async with pool.acquire() as conn:
        count: int = await conn.fetchval(
            "SELECT COUNT(*) FROM conversation_turns WHERE deck_id = $1", deck_id
        )
    return count
