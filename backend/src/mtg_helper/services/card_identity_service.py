"""Canonical oracle-card identity and Commander copy-limit helpers."""

import logging
import re
from typing import Any
from uuid import UUID

import asyncpg

_log = logging.getLogger(__name__)

_FINITE_COPY_RULE = re.compile(
    r"a deck can have up to ([a-z0-9 -]+?) cards named",
    re.IGNORECASE,
)
_UNLIMITED_COPY_RULE = re.compile(
    r"a deck can have any number of cards named",
    re.IGNORECASE,
)
_ONES = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


def oracle_key(row: Any) -> UUID:
    """Return the stable oracle key for a card-like record or model."""
    oracle_id = row["oracle_id"] if isinstance(row, asyncpg.Record) else row.oracle_id
    card_id = row["id"] if isinstance(row, asyncpg.Record) else row.id
    return oracle_id or card_id


async def canonical_card_by_scryfall(
    conn: asyncpg.Connection,
    scryfall_id: UUID,
) -> asyncpg.Record | None:
    """Resolve any printing Scryfall ID to the current canonical local card."""
    return await conn.fetchrow(
        """
        SELECT candidate.*
        FROM cards source
        JOIN LATERAL (
            SELECT c.*
            FROM cards c
            WHERE COALESCE(c.oracle_id, c.id) = COALESCE(source.oracle_id, source.id)
            ORDER BY c.is_canonical DESC, c.released_at DESC NULLS LAST, c.scryfall_id
            LIMIT 1
        ) candidate ON true
        WHERE source.scryfall_id = $1
        """,
        scryfall_id,
    )


async def canonical_card_by_id(
    conn: asyncpg.Connection,
    card_id: UUID,
) -> asyncpg.Record | None:
    """Resolve any local card row to the current canonical local card."""
    return await conn.fetchrow(
        """
        SELECT candidate.*
        FROM cards source
        JOIN LATERAL (
            SELECT c.*
            FROM cards c
            WHERE COALESCE(c.oracle_id, c.id) = COALESCE(source.oracle_id, source.id)
            ORDER BY c.is_canonical DESC, c.released_at DESC NULLS LAST, c.scryfall_id
            LIMIT 1
        ) candidate ON true
        WHERE source.id = $1
        """,
        card_id,
    )


def commander_copy_limit(type_line: str | None, oracle_text: str | None) -> int | None:
    """Return the legal Commander copy limit; ``None`` means unlimited."""
    card_types = set((type_line or "").split("—", 1)[0].split())
    if {"Basic", "Land"}.issubset(card_types):
        return None
    text = oracle_text or ""
    if _UNLIMITED_COPY_RULE.search(text):
        return None
    match = _FINITE_COPY_RULE.search(text)
    if match is None:
        return 1
    parsed = _parse_number(match.group(1))
    if parsed is None:
        _log.warning("Unrecognized Commander copy-limit text: %s", match.group(0))
        return 1
    return parsed


def clamp_quantity(quantity: int, limit: int | None) -> int:
    """Clamp a deck quantity to its non-negative legal range."""
    return max(0, quantity) if limit is None else max(0, min(quantity, limit))


def _parse_number(raw: str) -> int | None:
    normalized = raw.strip().lower().replace("-", " ")
    if normalized.isdigit():
        value = int(normalized)
        return value if 1 <= value <= 99 else None
    tokens = [token for token in normalized.split() if token != "and"]
    if len(tokens) == 1:
        return _ONES.get(tokens[0]) or _TENS.get(tokens[0])
    if len(tokens) == 2 and tokens[0] in _TENS and tokens[1] in _ONES:
        return _TENS[tokens[0]] + _ONES[tokens[1]]
    return None
