"""Cross-deck user profile service for implicit preference signals."""

import asyncio
import math
import time
from dataclasses import dataclass, field
from uuid import UUID

import asyncpg

_CACHE_TTL_SECONDS = 300  # 5 minutes
_TAG_FREQ_EPSILON = 1e-6
_MIN_DECKS_FOR_PROFILE = 2


@dataclass
class UserProfile:
    """Implicit user preference profile derived from cross-deck behavior."""

    feedback: dict[UUID, int] = field(default_factory=dict)
    """card_id → net vote count across other decks (up=+1, down=-1)."""

    tag_prefs: dict[str, float] = field(default_factory=dict)
    """tag → normalized relative preference [0, 1]."""


_cache: dict[UUID, tuple[float, UserProfile]] = {}


def _is_cache_valid(account_id: UUID) -> bool:
    entry = _cache.get(account_id)
    if entry is None:
        return False
    return (time.monotonic() - entry[0]) < _CACHE_TTL_SECONDS


async def _count_other_decks(
    pool: asyncpg.Pool,
    account_id: UUID,
    exclude_deck_id: UUID,
) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM decks WHERE owner_id = $1 AND id != $2",
            account_id,
            exclude_deck_id,
        )


async def _compute_cross_deck_feedback(
    pool: asyncpg.Pool,
    account_id: UUID,
    exclude_deck_id: UUID,
) -> dict[UUID, int]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT df.card_id,
                   SUM(CASE WHEN df.feedback = 'up' THEN 1 ELSE -1 END) AS net
            FROM deck_feedback df
            JOIN decks d ON df.deck_id = d.id
            WHERE d.owner_id = $1 AND d.id != $2
            GROUP BY df.card_id
            """,
            account_id,
            exclude_deck_id,
        )
    return {r["card_id"]: r["net"] for r in rows}


async def _compute_tag_preferences(
    pool: asyncpg.Pool,
    account_id: UUID,
    exclude_deck_id: UUID,
) -> dict[str, float]:
    async with pool.acquire() as conn:
        user_rows = await conn.fetch(
            """
            SELECT unnest(c.tags) AS tag, COUNT(*) AS cnt
            FROM deck_cards dc
            JOIN decks d ON dc.deck_id = d.id
            JOIN cards c ON dc.card_id = c.id
            WHERE d.owner_id = $1 AND d.id != $2
            GROUP BY tag
            """,
            account_id,
            exclude_deck_id,
        )
        global_rows = await conn.fetch(
            """
            SELECT unnest(tags) AS tag, COUNT(*) AS cnt
            FROM cards
            WHERE cardinality(tags) > 0
            GROUP BY tag
            """
        )

    total_user = sum(r["cnt"] for r in user_rows) or 1
    total_global = sum(r["cnt"] for r in global_rows) or 1

    global_freq: dict[str, float] = {r["tag"]: r["cnt"] / total_global for r in global_rows}

    raw: dict[str, float] = {}
    for r in user_rows:
        tag = r["tag"]
        user_freq = r["cnt"] / total_user
        raw[tag] = user_freq / max(global_freq.get(tag, _TAG_FREQ_EPSILON), _TAG_FREQ_EPSILON)

    if not raw:
        return {}

    max_val = max(raw.values()) or 1.0
    return {tag: val / max_val for tag, val in raw.items()}


async def get_user_profile(
    pool: asyncpg.Pool,
    account_id: UUID,
    exclude_deck_id: UUID,
) -> UserProfile | None:
    """Return a user's implicit preference profile derived from their other decks.

    Args:
        pool: asyncpg connection pool.
        account_id: The account's UUID.
        exclude_deck_id: Deck being built — excluded from profile computation.

    Returns:
        UserProfile if the user has at least 2 decks, otherwise None.
    """
    if _is_cache_valid(account_id):
        return _cache[account_id][1]

    other_deck_count = await _count_other_decks(pool, account_id, exclude_deck_id)
    if other_deck_count < _MIN_DECKS_FOR_PROFILE - 1:
        return None

    feedback, tag_prefs = await asyncio.gather(
        _compute_cross_deck_feedback(pool, account_id, exclude_deck_id),
        _compute_tag_preferences(pool, account_id, exclude_deck_id),
    )

    if not feedback and not tag_prefs:
        return None

    profile = UserProfile(feedback=feedback, tag_prefs=tag_prefs)
    _cache[account_id] = (time.monotonic(), profile)
    return profile


def score_card(
    profile: UserProfile,
    card_id: UUID,
    card_tags: list[str],
) -> float:
    """Compute a user profile score for a single card.

    Args:
        profile: The user's preference profile.
        card_id: Card UUID to score.
        card_tags: Tags on the card.

    Returns:
        Score in [0, 1]; 0.5 is neutral (no data).
    """
    net = profile.feedback.get(card_id)
    feedback_score = 0.5 + 0.5 * math.tanh(net) if net is not None else 0.5

    matching = [profile.tag_prefs[t] for t in card_tags if t in profile.tag_prefs]
    tag_score = sum(matching) / len(matching) if matching else 0.5

    return 0.6 * feedback_score + 0.4 * tag_score
