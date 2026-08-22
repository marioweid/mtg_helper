"""Mana curve recommendation helpers for Commander decks."""

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from mtg_helper.models.mana_curve import DeckManaCurve, ManaCurveRecommendation

BUCKETS: tuple[str, ...] = ("0", "1", "2", "3", "4", "5", "6", "7+")
MIN_MOXFIELD_DECKS = 5

# Generic Commander target for non-land mainboard spells. Sum: 62.
FALLBACK_BUCKETS: dict[str, int] = {
    "0": 3,
    "1": 5,
    "2": 14,
    "3": 15,
    "4": 11,
    "5": 7,
    "6": 4,
    "7+": 3,
}


def empty_buckets() -> dict[str, int]:
    """Return a zero-filled curve bucket map."""
    return {bucket: 0 for bucket in BUCKETS}


def bucket_for_cmc(cmc: Decimal | float | int | None) -> str:
    """Return the canonical curve bucket for a card mana value."""
    if cmc is None:
        return "0"
    value = int(cmc)
    return "7+" if value >= 7 else str(max(0, value))


def current_curve(cards: list[Any]) -> dict[str, int]:
    """Compute a quantity-weighted non-land curve from card-like objects."""
    buckets = empty_buckets()
    for card in cards:
        type_line = _read(card, "type_line") or ""
        if "Land" in type_line:
            continue
        quantity = int(_read(card, "quantity") or 1)
        bucket = bucket_for_cmc(_read(card, "cmc"))
        buckets[bucket] += quantity
    return buckets


async def deck_curve(
    pool: asyncpg.Pool,
    commander_id: UUID,
    cards: list[Any],
) -> DeckManaCurve:
    """Build current/recommended curve data for a deck."""
    current = current_curve(cards)
    recommended = await recommendation_for_commander(pool, commander_id)
    return DeckManaCurve(
        current=current,
        recommended=recommended,
        delta=_delta(current, recommended.buckets),
        progress_delta=_progress_delta(current, recommended.buckets),
    )


async def recommendation_for_commander(
    pool: asyncpg.Pool,
    commander_id: UUID,
) -> ManaCurveRecommendation:
    """Return a Moxfield-derived recommendation or generic fallback."""
    payload = await _cached_moxfield_payload(pool, commander_id)
    curve = payload.get("curve") if isinstance(payload, dict) else None
    if isinstance(curve, dict) and curve.get("source") == "moxfield":
        deck_count = int(curve.get("deck_count") or 0)
        buckets = _normalize_buckets(curve.get("buckets"))
        if deck_count >= MIN_MOXFIELD_DECKS and sum(buckets.values()) > 0:
            return ManaCurveRecommendation(
                source="moxfield",
                deck_count=deck_count,
                confidence="high",
                buckets=buckets,
            )
    return fallback_recommendation()


async def _cached_moxfield_payload(pool: asyncpg.Pool, commander_id: UUID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        payload = await conn.fetchval(
            "SELECT payload FROM moxfield_commander_recs WHERE commander_id = $1", commander_id
        )
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        return json.loads(payload)
    return {}


def fallback_recommendation() -> ManaCurveRecommendation:
    """Return the generic Commander fallback curve recommendation."""
    return ManaCurveRecommendation(
        source="fallback",
        deck_count=0,
        confidence="fallback",
        buckets=dict(FALLBACK_BUCKETS),
    )


def _normalize_buckets(raw: object) -> dict[str, int]:
    buckets = empty_buckets()
    if not isinstance(raw, dict):
        return buckets
    for bucket in BUCKETS:
        buckets[bucket] = max(0, int(raw.get(bucket) or 0))
    return buckets


def _delta(current: dict[str, int], target: dict[str, int]) -> dict[str, int]:
    return {bucket: target.get(bucket, 0) - current.get(bucket, 0) for bucket in BUCKETS}


def _progress_delta(current: dict[str, int], target: dict[str, int]) -> dict[str, int]:
    current_total = sum(current.values())
    target_total = sum(target.values()) or 1
    scale = min(1.0, current_total / target_total)
    scaled = {bucket: round(target.get(bucket, 0) * scale) for bucket in BUCKETS}
    return _delta(current, scaled)


def _read(card: Any, field: str) -> Any:
    if isinstance(card, dict):
        return card.get(field)
    return getattr(card, field, None)
