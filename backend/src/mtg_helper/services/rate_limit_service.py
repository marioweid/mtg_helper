"""In-memory sliding-window rate limiter.

Keyed per (endpoint, account_or_ip). Counters live in process memory only — no
persistence, no cross-replica coordination. Good enough for a single backend
replica; swap for a Postgres-table counter when scaling horizontally.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

_Timestamps = deque[float]
_buckets: dict[str, _Timestamps] = {}
_lock = Lock()


class RateLimitExceeded(Exception):  # noqa: N818 — action-like name, matches HTTP 429 domain
    """Raised when a key exceeds its configured rate limit."""

    def __init__(self, key: str, limit: int, window_s: int) -> None:
        super().__init__(f"Rate limit exceeded for {key!r}: {limit}/{window_s}s")
        self.key = key
        self.limit = limit
        self.window_s = window_s


def check(key: str, limit: int, window_s: int) -> None:
    """Record a hit against ``key`` and raise if the window limit is exceeded.

    Uses a sliding-window policy: prune any timestamps older than ``window_s``
    before comparing against ``limit``.

    Args:
        key: Opaque identifier (e.g. ``"describe:account-uuid"``).
        limit: Maximum allowed hits inside the window.
        window_s: Window length in seconds.

    Raises:
        RateLimitExceeded: If recording this hit would exceed ``limit``.
    """
    now = time.monotonic()
    cutoff = now - window_s
    with _lock:
        bucket = _buckets.get(key)
        if bucket is None:
            bucket = deque()
            _buckets[key] = bucket
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise RateLimitExceeded(key, limit, window_s)
        bucket.append(now)


def reset() -> None:
    """Clear all in-memory buckets. Intended for tests only."""
    with _lock:
        _buckets.clear()
