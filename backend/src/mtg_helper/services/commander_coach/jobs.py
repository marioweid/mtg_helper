"""In-memory Commander Coach job registry for SSE progress streaming."""

import asyncio
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from mtg_helper.models.ai import CommanderCoachResponse


@dataclass
class CoachEvent:
    """One progress event emitted by a Coach job."""

    event: str
    message: str


@dataclass
class CoachJob:
    """Mutable state for a running Coach request."""

    job_id: UUID
    account_id: UUID
    deck_id: UUID
    queue: asyncio.Queue[CoachEvent] = field(default_factory=asyncio.Queue)
    status: str = "running"
    result: CommanderCoachResponse | None = None
    error: str | None = None


CoachRegistry = dict[UUID, CoachJob]


def create(registry: CoachRegistry, account_id: UUID, deck_id: UUID) -> CoachJob:
    """Create and register a new Coach job."""
    job = CoachJob(job_id=uuid4(), account_id=account_id, deck_id=deck_id)
    registry[job.job_id] = job
    return job


async def emit(job: CoachJob, event: str, message: str) -> None:
    """Publish one progress event to the job stream."""
    await job.queue.put(CoachEvent(event=event, message=message))


async def finish_ok(job: CoachJob, result: CommanderCoachResponse) -> None:
    """Mark a job successful and wake stream listeners."""
    job.status = "ok"
    job.result = result
    await emit(job, "done", "Coach response ready")


async def finish_error(job: CoachJob, message: str) -> None:
    """Mark a job failed and wake stream listeners."""
    job.status = "error"
    job.error = message
    await emit(job, "error", message)
