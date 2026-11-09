"""Tutor setup, explicit generation, freshness, and durable publication."""

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from mtg_helper.models.tutor import (
    TutorConversationResponse,
    TutorMode,
    TutorReferencePreviewResponse,
    TutorReferenceRequest,
    TutorStateResponse,
)
from mtg_helper.services.recommendations.repository import Owner
from mtg_helper.services.tutor import cedh, commander
from mtg_helper.services.tutor.repository import (
    TutorHandoffRetryWork,
    TutorHandoffWork,
    TutorQuestionWork,
    TutorRepository,
    TutorWork,
)
from mtg_helper.services.tutor.teaching import (
    CompactionInput,
    ConversationInput,
    TeachingInput,
    run_compaction_agent,
    validate_opening_hands,
)

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _HandoffOutcome:
    content: str | None = None
    failed: bool = False


class TutorService:
    """Small interface for owner-scoped Tutor state and manual guide generation."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.repository = TutorRepository(pool)

    async def save_mode(self, owner: Owner, deck_id: UUID, mode: TutorMode) -> TutorStateResponse:
        await self.repository.save_mode(owner, deck_id, mode)
        return await self.state(owner, deck_id)

    async def preview_reference(
        self, owner: Owner, deck_id: UUID, request: TutorReferenceRequest
    ) -> TutorReferencePreviewResponse:
        """Prepare one immutable reference candidate without model or deck writes."""
        return await self.repository.preview_reference(owner, deck_id, request)

    async def confirm_reference(
        self, owner: Owner, deck_id: UUID, preview_id: UUID
    ) -> TutorStateResponse:
        """Save a confirmed reference and return the now-historical guide state."""
        await self.repository.confirm_reference(owner, deck_id, preview_id)
        return await self.state(owner, deck_id)

    async def remove_reference(self, owner: Owner, deck_id: UUID) -> TutorStateResponse:
        """Remove the Referenzdeck without touching the Lerndeck or starting a guide."""
        await self.repository.remove_reference(owner, deck_id)
        return await self.state(owner, deck_id)

    async def start(self, owner: Owner, deck_id: UUID, request_key: UUID) -> TutorStateResponse:
        work = await self.repository.create(owner, deck_id, request_key)
        if work is not None:
            asyncio.create_task(self._run(work))
        return await self.state(owner, deck_id)

    async def state(self, owner: Owner, deck_id: UUID) -> TutorStateResponse:
        (
            mode,
            latest,
            successful,
            reference,
            differences,
            current_cards,
        ) = await self.repository.state(owner, deck_id)
        return TutorStateResponse(
            mode=mode,
            latest_run=latest,
            last_successful_run=successful,
            reference=reference,
            reference_differences=differences,
            current_cards=current_cards,
        )

    async def ask(
        self,
        owner: Owner,
        deck_id: UUID,
        request_key: UUID,
        question: str,
        card_name: str | None,
    ) -> TutorConversationResponse:
        """Save and start one idempotent current-list answer request."""
        work = await self.repository.create_question(
            owner, deck_id, request_key, question, card_name
        )
        if work is not None:
            asyncio.create_task(self._answer(work))
        return await self.repository.conversation(owner, deck_id)

    async def conversation(self, owner: Owner, deck_id: UUID) -> TutorConversationResponse:
        """Read the full owner-scoped conversation without starting work."""
        return await self.repository.conversation(owner, deck_id)

    async def retry_handoff(
        self, owner: Owner, deck_id: UUID, chapter_id: UUID, request_key: UUID
    ) -> TutorConversationResponse:
        """Start only an explicit, deduplicated retry for one failed Lernübergabe."""
        work = await self.repository.create_handoff_retry(owner, deck_id, chapter_id, request_key)
        if work is not None:
            asyncio.create_task(self._retry_handoff(work))
        return await self.repository.conversation(owner, deck_id)

    async def clear_conversation(self, owner: Owner, deck_id: UUID) -> TutorConversationResponse:
        """Clear only deck-local Tutor history and return its now-empty state."""
        await self.repository.clear_conversation(owner, deck_id)
        return await self.repository.conversation(owner, deck_id)

    async def _answer(self, work: TutorQuestionWork) -> None:
        handoff = await self._handoff(work)
        question_input = ConversationInput(
            mode=work.mode,
            description=work.manifest["description"]
            if isinstance(work.manifest["description"], str)
            else None,
            bracket=work.manifest["bracket"] if isinstance(work.manifest["bracket"], int) else None,
            evidence=work.question_evidence,
            question=work.question,
            selected_card_name=work.card_name,
            selected_card=work.selected_card,
            selected_card_present=work.selected_card_present,
            handoff=handoff,
            recent_turns=work.recent_turns,
        )
        try:
            answer = await (
                commander.answer(question_input)
                if work.mode == "commander"
                else cedh.answer(question_input)
            )
            await self.repository.publish_question(work, answer.content)
        except Exception:
            _log.exception("Tutor question failed")
            await self.repository.fail_question(work)

    async def _handoff(self, work: TutorWork | TutorQuestionWork) -> str | None:
        """Compact once when required; failure never blocks an answer from current facts."""
        handoff_work = work.handoff_work
        if handoff_work is None:
            return None
        if not handoff_work.compaction_required:
            return handoff_work.handoff
        if not await self.repository.start_handoff(handoff_work):
            return None
        outcome = await self._execute_handoff(work.mode, handoff_work)
        return outcome.content

    async def _execute_handoff(self, mode: TutorMode, handoff: TutorHandoffWork) -> _HandoffOutcome:
        """Execute and publish one claimed compaction without owning its caller's lifecycle."""
        compaction_input = CompactionInput(
            mode=mode,
            previous_handoff=handoff.previous_handoff,
            turns=handoff.compaction_turns,
        )
        try:
            summary = await run_compaction_agent(compaction_input)
        except Exception:
            _log.exception("Tutor handoff failed")
            await self.repository.fail_handoff(handoff)
            return _HandoffOutcome(failed=True)
        published = await self.repository.complete_handoff(handoff, summary.content)
        return _HandoffOutcome(content=summary.content if published else None)

    async def _retry_handoff(self, work: TutorHandoffRetryWork) -> None:
        """Run one paid compaction only after its explicit user request."""
        handoff = work.handoff_work
        try:
            outcome = await self._execute_handoff(work.mode, handoff)
            if outcome.failed:
                error = "Lernübergabe retry failed; retry explicitly."
            else:
                error = (
                    None
                    if outcome.content is not None
                    else "Lernübergabe retry was interrupted; retry explicitly."
                )
        except Exception:
            _log.exception("Explicit Tutor handoff retry failed")
            await self.repository.fail_handoff(handoff)
            error = "Lernübergabe retry failed; retry explicitly."
        await self.repository.finish_handoff_retry(work, error)

    async def _run(self, work: TutorWork) -> None:
        await self._handoff(work)
        teacher_input = TeachingInput(
            mode=work.mode,
            description=work.manifest["description"]
            if isinstance(work.manifest["description"], str)
            else None,
            bracket=work.manifest["bracket"] if isinstance(work.manifest["bracket"], int) else None,
            evidence=work.guide_evidence,
        )
        try:
            guide = await (
                commander.generate(teacher_input)
                if work.mode == "commander"
                else cedh.generate(teacher_input)
            )
            validate_opening_hands(guide, work.guide_evidence)
            await self.repository.publish(work, guide)
        except Exception:
            _log.exception("Tutor guide generation failed")
            await self.repository.fail(work)


def owner(account_id: UUID, email: str) -> Owner:
    """Construct a normalized owner record used by all Tutor persistence operations."""
    return Owner(account_id=account_id, email=email.strip().lower())
