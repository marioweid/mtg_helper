"""Compatibility namespace for MTG Assistant and deterministic deck analysis."""

from collections.abc import Awaitable, Callable
from uuid import UUID

import asyncpg

from mtg_helper.models.ai import CommanderCoachRequest, CommanderCoachResponse
from mtg_helper.models.decks import DeckDetailResponse

ProgressCb = Callable[[str, str], Awaitable[None]]
MemoryLearnCb = Callable[[str], Awaitable[None]]


async def run_coach(
    pool: asyncpg.Pool,
    deck: DeckDetailResponse,
    request: CommanderCoachRequest,
    progress: ProgressCb | None = None,
    memory_learn: MemoryLearnCb | None = None,
    *,
    account_id: UUID | None = None,
) -> CommanderCoachResponse:
    """Lazily call the compatibility orchestrator without creating import cycles."""
    from mtg_helper.services.commander_coach.orchestrator import run_coach as run

    return await run(pool, deck, request, progress, memory_learn, account_id=account_id)


__all__ = ["run_coach"]
