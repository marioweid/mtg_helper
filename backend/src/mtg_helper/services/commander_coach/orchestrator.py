"""Compatibility entrypoint for the single MTG Assistant."""

from collections.abc import Awaitable, Callable
from uuid import UUID

import asyncpg

from mtg_helper.models.ai import CommanderCoachRequest, CommanderCoachResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.services.mtg_assistant import run_assistant

ProgressCb = Callable[[str, str], Awaitable[None]]


async def run_coach(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    request: CommanderCoachRequest,
    progress: ProgressCb | None = None,
    memory_learn: Callable[[str], Awaitable[None]] | None = None,
    *,
    account_id: UUID | None = None,
) -> CommanderCoachResponse:
    """Run the MTG Assistant while preserving the existing API function name."""
    del memory_learn
    return await run_assistant(pool, deck, request, progress, account_id=account_id)
