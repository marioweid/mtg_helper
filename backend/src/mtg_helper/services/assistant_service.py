"""Run a complete assistant turn, including memory commands and session tracing."""

from uuid import UUID

import asyncpg
from opentelemetry.trace import Tracer

from mtg_helper.models.ai import CommanderCoachRequest, CommanderCoachResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.observability import assistant_turn
from mtg_helper.services import coach_memory_service, commander_coach
from mtg_helper.services.commander_coach import ProgressCb


class AssistantService:
    """Application-scoped dependencies for an authorized assistant turn."""

    def __init__(self, pool: asyncpg.Pool, tracer: Tracer) -> None:
        self.pool = pool
        self.tracer = tracer

    async def run(
        self,
        deck: DeckDetailResponse,
        body: CommanderCoachRequest,
        account_id: UUID,
        *,
        progress: ProgressCb | None = None,
    ) -> CommanderCoachResponse:
        """Run one authorized turn with a root span spanning its complete lifetime.

        Args:
            deck: Deck already authorized by the API for this account.
            body: Current question, bounded history, and client conversation UUID.
            account_id: Authenticated account, not a client-supplied identity.
            progress: Optional SSE progress publisher.

        Returns:
            The assistant's visible reply and structured recommendations or memory.
        """
        with assistant_turn(
            self.tracer,
            account_id=account_id,
            deck_id=deck.id,
            conversation_id=body.conversation_id,
            message=body.message,
        ) as turn:
            result = await self._run(deck, body, account_id, progress=progress)
            turn.set_reply(result.reply)
            return result

    async def _run(
        self,
        deck: DeckDetailResponse,
        body: CommanderCoachRequest,
        account_id: UUID,
        *,
        progress: ProgressCb | None,
    ) -> CommanderCoachResponse:
        await _emit(progress, "memory_check", "Checking Assistant memory")
        memory = await coach_memory_service.get_memory(self.pool, deck.id, account_id)
        body = body.model_copy(update={"coach_memory_notes": memory.notes.strip() or None})
        await _emit(progress, "memory_loaded", "Loaded deck memory into Assistant context")
        await _emit(progress, "assistant_routing", "MTG Assistant is reading the request")
        routed = await coach_memory_service.handle_memory_message(
            self.pool, deck.id, account_id, body
        )
        if routed is not None:
            await _emit(progress, "assistant_routed", "Handled by deterministic memory tools")
            await _report_routed(progress, routed)
            return routed
        await _emit(progress, "assistant_routed", "MTG Assistant is selecting deck tools")
        return await commander_coach.run_coach(
            self.pool, deck, body, progress=progress, account_id=account_id
        )


async def _emit(progress: ProgressCb | None, event: str, message: str) -> None:
    if progress is not None:
        await progress(event, message)


async def _report_routed(progress: ProgressCb | None, result: CommanderCoachResponse) -> None:
    if result.mode == "memory" and result.memory_updated:
        await _emit(progress, "memory_writing", "Writing updated Assistant memory")
        await _emit(progress, "memory_written", "Assistant memory updated")
    elif result.mode == "memory":
        await _emit(progress, "memory_read", "Reading Assistant memory")
    else:
        await _emit(progress, "chat_reply", "MTG Assistant answered without deck tools")
