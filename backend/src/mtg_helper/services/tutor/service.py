"""Tutor setup, explicit generation, freshness, and durable publication."""

import asyncio
import logging
from uuid import UUID

import asyncpg

from mtg_helper.models.tutor import (
    TutorMode,
    TutorReferencePreviewResponse,
    TutorReferenceRequest,
    TutorStateResponse,
)
from mtg_helper.services.recommendations.repository import Owner
from mtg_helper.services.tutor import cedh, commander
from mtg_helper.services.tutor.repository import TutorRepository, TutorWork
from mtg_helper.services.tutor.teaching import TeachingInput, validate_opening_hands

_log = logging.getLogger(__name__)


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
        mode, latest, successful, reference, differences = await self.repository.state(
            owner, deck_id
        )
        return TutorStateResponse(
            mode=mode,
            latest_run=latest,
            last_successful_run=successful,
            reference=reference,
            reference_differences=differences,
        )

    async def _run(self, work: TutorWork) -> None:
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
