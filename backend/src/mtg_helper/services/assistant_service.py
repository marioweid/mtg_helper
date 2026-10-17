"""Run a complete authorized and traced assistant turn."""

from uuid import UUID

import asyncpg
from opentelemetry.trace import Tracer

from mtg_helper.models.ai import CommanderCoachRequest, CommanderCoachResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.observability import assistant_turn
from mtg_helper.services.mtg_assistant import ProgressCb, run_assistant


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
            The assistant's visible reply and structured recommendations.
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
        await _emit(progress, "assistant_routing", "MTG Assistant is reading the request")
        await _emit(progress, "assistant_routed", "MTG Assistant is selecting deck tools")
        return await run_assistant(self.pool, deck, body, progress=progress, account_id=account_id)


async def _emit(progress: ProgressCb | None, event: str, message: str) -> None:
    if progress is not None:
        await progress(event, message)
