"""In-memory progress registry for long-running deck-optimizer runs.

Mirrors :mod:`mtg_helper.services.admin_jobs` but keyed by a per-run
``job_id`` (UUID) rather than fixed singleton slots, since optimizer runs are
per-deck / per-account and may overlap. Each run updates an
:class:`OptimizerJob` via the callback from :func:`progress_cb`; the frontend
polls ``GET /decks/{id}/playtest/optimize/{job_id}`` to render a progress bar.

State is process-local: a backend restart drops in-flight jobs. Acceptable —
the run is a stateless recommendation the user can simply re-trigger.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from mtg_helper.models.optimizer import OptimizationProposal

JobStatus = Literal["running", "ok", "error"]
ProgressCb = Callable[[str, int, int], None]

_MAX_AGE = timedelta(minutes=15)


@dataclass
class OptimizerJob:
    """Live progress state for a single optimizer run."""

    job_id: UUID
    account_id: UUID
    deck_id: UUID
    status: JobStatus = "running"
    phase: str = ""
    current: int = 0
    total: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    finished_at: datetime | None = None
    error: str | None = None
    result: OptimizationProposal | None = None


def prune(registry: dict[UUID, OptimizerJob], *, max_age: timedelta = _MAX_AGE) -> None:
    """Drop finished jobs older than ``max_age`` to bound the registry."""
    cutoff = datetime.now(tz=UTC) - max_age
    stale = [
        jid
        for jid, job in registry.items()
        if job.finished_at is not None and job.finished_at < cutoff
    ]
    for jid in stale:
        del registry[jid]


def create(registry: dict[UUID, OptimizerJob], account_id: UUID, deck_id: UUID) -> OptimizerJob:
    """Register a new running job and return it. Prunes stale jobs first."""
    prune(registry)
    job = OptimizerJob(job_id=uuid4(), account_id=account_id, deck_id=deck_id)
    registry[job.job_id] = job
    return job


def progress_cb(job: OptimizerJob) -> ProgressCb:
    """Return a callback that updates ``job`` in-place at each progress tick."""

    def _cb(phase: str, current: int, total: int) -> None:
        job.phase = phase
        job.current = current
        job.total = total

    return _cb


def finish_ok(job: OptimizerJob, result: OptimizationProposal) -> None:
    """Mark the job successful and attach its result."""
    job.status = "ok"
    job.result = result
    job.current = job.total
    job.finished_at = datetime.now(tz=UTC)


def finish_error(job: OptimizerJob, error: str) -> None:
    """Mark the job failed with an error message."""
    job.status = "error"
    job.error = error
    job.finished_at = datetime.now(tz=UTC)


def noop_progress(phase: str, current: int, total: int) -> None:
    """Default progress sink when a search is run without a callback."""
    del phase, current, total
