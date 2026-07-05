"""In-memory progress registry for admin maintenance jobs.

Each long-running admin endpoint (sync, tag, embed, refresh-all) updates a
shared :class:`JobState` via the callback returned by
:func:`make_progress_cb`. The Admin UI polls ``GET /admin/status`` every
couple of seconds and renders a progress bar from ``current`` / ``total``.

State is process-local; a backend restart resets every job back to ``idle``.
That is acceptable here: the sync is idempotent (UPSERT) and the operator
can re-trigger it from the Admin page.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

JobKey = Literal["sync", "mtgjson", "tag", "embed", "refresh-all"]
JobStatus = Literal["idle", "running", "ok", "error"]

ProgressCb = Callable[[str, int, int], None]


@dataclass
class JobState:
    """Live progress state for a single admin job."""

    key: JobKey
    status: JobStatus = "idle"
    phase: str = ""
    current: int = 0
    total: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result: dict[str, object] | None = None


@dataclass
class JobRegistry:
    """All admin job states attached to ``app.state.admin_jobs``."""

    sync: JobState = field(default_factory=lambda: JobState(key="sync"))
    mtgjson: JobState = field(default_factory=lambda: JobState(key="mtgjson"))
    tag: JobState = field(default_factory=lambda: JobState(key="tag"))
    embed: JobState = field(default_factory=lambda: JobState(key="embed"))
    refresh_all: JobState = field(default_factory=lambda: JobState(key="refresh-all"))


def reset(job: JobState) -> None:
    """Clear progress fields ahead of a new run."""
    job.phase = ""
    job.current = 0
    job.total = 0
    job.started_at = None
    job.finished_at = None
    job.error = None
    job.result = None


def start(job: JobState) -> None:
    """Mark job running and stamp start time."""
    reset(job)
    job.status = "running"
    job.started_at = datetime.now(tz=UTC)


def finish_ok(job: JobState, result: dict[str, object] | None = None) -> None:
    """Mark job successful and stamp finish time."""
    job.status = "ok"
    job.finished_at = datetime.now(tz=UTC)
    job.result = result


def finish_error(job: JobState, error: str) -> None:
    """Mark job failed and stamp finish time."""
    job.status = "error"
    job.error = error
    job.finished_at = datetime.now(tz=UTC)


def make_progress_cb(job: JobState) -> ProgressCb:
    """Return a callback that updates ``job`` in-place at each progress tick."""

    def _cb(phase: str, current: int, total: int) -> None:
        job.phase = phase
        job.current = current
        job.total = total

    return _cb


def noop_progress(phase: str, current: int, total: int) -> None:
    """Default progress sink used when a service is called without a callback."""
    del phase, current, total
