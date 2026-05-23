"""Scryfall bulk data pipeline: download, parse, and upsert cards into PostgreSQL."""

import json
import logging
import time
from datetime import date
from typing import TYPE_CHECKING, Any

import asyncpg
import httpx

from mtg_helper.config import settings

if TYPE_CHECKING:
    from mtg_helper.services.admin_jobs import ProgressCb

_log = logging.getLogger(__name__)

# Batch size for upsert operations
_BATCH_SIZE = 500

_CARD_TYPES = frozenset(
    {
        "Artifact",
        "Creature",
        "Enchantment",
        "Instant",
        "Land",
        "Planeswalker",
        "Sorcery",
        "Battle",
        "Kindred",
    }
)


def parse_type_line(type_line: str | None) -> tuple[list[str], list[str]]:
    """Parse a Scryfall type line into card types and subtypes.

    Handles double-faced cards (split on ' // '), extracts card types from the
    left side of ' — ' and subtypes from the right side.

    Args:
        type_line: Raw type line string, e.g. "Legendary Creature — Human Wizard".

    Returns:
        Tuple of (card_types, subtypes) with deduplicated values.
    """
    if not type_line:
        return [], []

    all_card_types: list[str] = []
    all_subtypes: list[str] = []

    for face in type_line.split(" // "):
        parts = face.split(" \u2014 ", maxsplit=1)
        left_words = parts[0].split()
        all_card_types.extend(w for w in left_words if w in _CARD_TYPES)
        if len(parts) > 1:
            all_subtypes.extend(parts[1].split())

    seen_types: set[str] = set()
    card_types: list[str] = []
    for t in all_card_types:
        if t not in seen_types:
            seen_types.add(t)
            card_types.append(t)

    seen_subs: set[str] = set()
    subtypes: list[str] = []
    for s in all_subtypes:
        if s not in seen_subs:
            seen_subs.add(s)
            subtypes.append(s)

    return card_types, subtypes


def _extract_image_uri(card: dict[str, Any]) -> str | None:
    """Extract the normal-size image URI from a Scryfall card object.

    Handles double-faced cards where image_uris is absent at the top level.

    Args:
        card: Raw Scryfall card dict.

    Returns:
        Image URL string, or None if unavailable.
    """
    if uris := card.get("image_uris"):
        return uris.get("normal")
    faces = card.get("card_faces") or []
    if faces:
        return (faces[0].get("image_uris") or {}).get("normal")
    return None


def _map_card(card: dict[str, Any]) -> dict[str, Any]:
    """Map a Scryfall card dict to our database schema.

    Args:
        card: Raw Scryfall card object from bulk data.

    Returns:
        Dict with keys matching the cards table columns.
    """
    card_types, subtypes = parse_type_line(card.get("type_line"))
    return {
        "scryfall_id": card["id"],
        "oracle_id": card.get("oracle_id"),
        "name": card["name"],
        "mana_cost": card.get("mana_cost"),
        "cmc": card.get("cmc"),
        "type_line": card.get("type_line"),
        "oracle_text": card.get("oracle_text"),
        "color_identity": card.get("color_identity") or [],
        "colors": card.get("colors") or [],
        "keywords": card.get("keywords") or [],
        "power": card.get("power"),
        "toughness": card.get("toughness"),
        "legalities": card.get("legalities") or {},
        "image_uri": _extract_image_uri(card),
        "prices": card.get("prices") or {},
        "rarity": card.get("rarity"),
        "set_code": card.get("set"),
        "released_at": date.fromisoformat(card["released_at"]) if card.get("released_at") else None,
        "edhrec_rank": card.get("edhrec_rank"),
        "card_types": card_types,
        "subtypes": subtypes,
        "border_color": card.get("border_color"),
        "security_stamp": card.get("security_stamp"),
        "game_changer": bool(card.get("game_changer", False)),
    }


_ILLEGAL_SET_CODES: frozenset[str] = frozenset(
    {
        "30a",  # 30th Anniversary Edition (non-tournament legal)
        "ugl",  # Unglued (silver-bordered)
        "unh",  # Unhinged (silver-bordered)
        "ust",  # Unstable (silver-bordered)
        "ced",  # Collector's Edition (gold-bordered proxy)
        "cei",  # International Edition (gold-bordered proxy)
        "wc97",  # World Championship Decks 1997
        "wc98",  # World Championship Decks 1998
        "wc99",  # World Championship Decks 1999
        "wc00",  # World Championship Decks 2000
        "wc01",  # World Championship Decks 2001
        "wc02",  # World Championship Decks 2002
        "wc03",  # World Championship Decks 2003
        "wc04",  # World Championship Decks 2004
    }
)


def _is_commander_relevant(card: dict[str, Any]) -> bool:
    """Return True if the card is relevant for Commander (legal or banned)."""
    legalities = card.get("legalities") or {}
    return legalities.get("commander") in ("legal", "banned")


def _is_commander_playable(card: dict[str, Any]) -> bool:
    """Return True if the card is legal to play in Commander.

    Filters out non-tournament-legal sets, silver/gold-bordered cards,
    acorn-stamped cards (Unfinity casual), Conspiracy cards, and ante cards.
    """
    if (card.get("set") or "").lower() in _ILLEGAL_SET_CODES:
        return False
    if card.get("border_color") == "gold":
        return False
    if card.get("security_stamp") == "acorn":
        return False
    type_line = card.get("type_line") or ""
    if "Conspiracy" in type_line:
        return False
    oracle_text = (card.get("oracle_text") or "").lower()
    if "playing for ante" in oracle_text:
        return False
    return True


async def _fetch_bulk_data_url(client: httpx.AsyncClient) -> str:
    """Fetch the download URL for the oracle_cards bulk data file.

    Args:
        client: httpx async client.

    Returns:
        Download URL string.

    Raises:
        ValueError: If the oracle_cards entry is not found.
    """
    response = await client.get(settings.scryfall_bulk_data_url)
    response.raise_for_status()
    entries = response.json().get("data", [])
    for entry in entries:
        if entry.get("type") == "oracle_cards":
            return entry["download_uri"]
    msg = "oracle_cards bulk data entry not found in Scryfall response"
    raise ValueError(msg)


async def _upsert_batch(conn: asyncpg.Connection, batch: list[dict[str, Any]]) -> None:
    """Upsert a batch of cards into the database.

    Args:
        conn: asyncpg connection.
        batch: List of mapped card dicts.
    """
    await conn.executemany(
        """
        INSERT INTO cards (
            scryfall_id, oracle_id, name, mana_cost, cmc, type_line, oracle_text,
            color_identity, colors, keywords, power, toughness, legalities,
            image_uri, prices, rarity, set_code, released_at, edhrec_rank,
            card_types, subtypes, border_color, security_stamp, game_changer, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, now()
        )
        ON CONFLICT (scryfall_id) DO UPDATE SET
            oracle_id      = EXCLUDED.oracle_id,
            name           = EXCLUDED.name,
            mana_cost      = EXCLUDED.mana_cost,
            cmc            = EXCLUDED.cmc,
            type_line      = EXCLUDED.type_line,
            oracle_text    = EXCLUDED.oracle_text,
            color_identity = EXCLUDED.color_identity,
            colors         = EXCLUDED.colors,
            keywords       = EXCLUDED.keywords,
            power          = EXCLUDED.power,
            toughness      = EXCLUDED.toughness,
            legalities     = EXCLUDED.legalities,
            image_uri      = EXCLUDED.image_uri,
            prices         = EXCLUDED.prices,
            rarity         = EXCLUDED.rarity,
            set_code       = EXCLUDED.set_code,
            released_at    = EXCLUDED.released_at,
            edhrec_rank    = EXCLUDED.edhrec_rank,
            card_types     = EXCLUDED.card_types,
            subtypes       = EXCLUDED.subtypes,
            border_color   = EXCLUDED.border_color,
            security_stamp = EXCLUDED.security_stamp,
            game_changer   = EXCLUDED.game_changer,
            updated_at     = now()
        """,
        [
            (
                c["scryfall_id"],
                c["oracle_id"],
                c["name"],
                c["mana_cost"],
                c["cmc"],
                c["type_line"],
                c["oracle_text"],
                c["color_identity"],
                c["colors"],
                c["keywords"],
                c["power"],
                c["toughness"],
                json.dumps(c["legalities"]),
                c["image_uri"],
                json.dumps(c["prices"]),
                c["rarity"],
                c["set_code"],
                c["released_at"],
                c["edhrec_rank"],
                c["card_types"],
                c["subtypes"],
                c["border_color"],
                c["security_stamp"],
                c["game_changer"],
            )
            for c in batch
        ],
    )


async def run_sync(
    pool: asyncpg.Pool,
    progress: "ProgressCb | None" = None,
) -> dict[str, Any]:
    """Download Scryfall oracle_cards bulk data and upsert into the cards table.

    Args:
        pool: asyncpg connection pool.
        progress: Optional callback ``(phase, current, total)`` invoked at
            each phase transition and after every upsert batch. Phases:
            ``"downloading"``, ``"filtering"``, ``"upserting"``.

    Returns:
        Summary dict with cards_processed and duration_seconds.
    """
    from mtg_helper.services.admin_jobs import noop_progress

    cb = progress or noop_progress
    start = time.monotonic()

    cb("downloading", 0, 0)
    async with httpx.AsyncClient(timeout=120) as client:
        download_url = await _fetch_bulk_data_url(client)
        response = await client.get(download_url)
        response.raise_for_status()
        all_cards: list[dict[str, Any]] = response.json()

    cb("filtering", 0, len(all_cards))
    relevant = [
        _map_card(c) for c in all_cards if _is_commander_relevant(c) and _is_commander_playable(c)
    ]

    total = len(relevant)
    _log.info("Upserting %d Commander-relevant cards", total)
    async with pool.acquire() as conn:
        for i in range(0, total, _BATCH_SIZE):
            await _upsert_batch(conn, relevant[i : i + _BATCH_SIZE])
            done = min(i + _BATCH_SIZE, total)
            cb("upserting", done, total)
            _log.info("Upserted %d / %d cards", done, total)

    return {
        "cards_processed": total,
        "duration_seconds": round(time.monotonic() - start, 2),
    }
