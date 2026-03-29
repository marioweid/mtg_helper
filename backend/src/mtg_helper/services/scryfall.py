"""Scryfall bulk data pipeline: download, parse, and upsert cards into PostgreSQL."""

import json
import time
from datetime import date
from typing import Any

import asyncpg
import httpx

from mtg_helper.config import settings

# Batch size for upsert operations
_BATCH_SIZE = 500


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
    }


def _is_commander_relevant(card: dict[str, Any]) -> bool:
    """Return True if the card is relevant for Commander (legal or banned)."""
    legalities = card.get("legalities") or {}
    return legalities.get("commander") in ("legal", "banned")


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
            image_uri, prices, rarity, set_code, released_at, edhrec_rank, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17, $18, $19, now()
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
            )
            for c in batch
        ],
    )


async def run_sync(pool: asyncpg.Pool) -> dict[str, Any]:
    """Download Scryfall oracle_cards bulk data and upsert into the cards table.

    Args:
        pool: asyncpg connection pool.

    Returns:
        Summary dict with cards_processed and duration_seconds.
    """
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=120) as client:
        download_url = await _fetch_bulk_data_url(client)
        response = await client.get(download_url)
        response.raise_for_status()
        all_cards: list[dict[str, Any]] = response.json()

    relevant = [_map_card(c) for c in all_cards if _is_commander_relevant(c)]

    async with pool.acquire() as conn:
        for i in range(0, len(relevant), _BATCH_SIZE):
            await _upsert_batch(conn, relevant[i : i + _BATCH_SIZE])

    return {
        "cards_processed": len(relevant),
        "duration_seconds": round(time.monotonic() - start, 2),
    }
