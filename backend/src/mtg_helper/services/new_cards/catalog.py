"""Bounded shared catalog ingestion, published with the canonical card transaction."""

import asyncio
import gzip
import json
import tempfile
import zlib
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

import asyncpg
import httpx

from mtg_helper.services.new_cards.discovery import (
    ReleaseHistory,
    card_facts,
    paper_card,
    release_history,
)
from mtg_helper.services.recommendations import source_repository
from mtg_helper.services.scryfall_exports import BulkExport, stream_export

_MAX_BYTES = 130 * 1024 * 1024
_MAX_HISTORY_BYTES = 2 * 1024 * 1024 * 1024
_MAX_HISTORY_LINE_BYTES = 2 * 1024 * 1024
_MAX_HISTORY_RECORDS = 1_000_000


def _records(stream: BinaryIO) -> Iterator[dict[str, Any]]:
    size = count = 0
    try:
        with gzip.GzipFile(fileobj=stream, mode="rb") as archive:
            while line := archive.readline(_MAX_HISTORY_LINE_BYTES + 1):
                size += len(line)
                if len(line) > _MAX_HISTORY_LINE_BYTES or size > _MAX_HISTORY_BYTES:
                    raise ValueError("Scryfall printing history exceeds decompression limits")
                if not line.strip():
                    continue
                count += 1
                if count > _MAX_HISTORY_RECORDS:
                    raise ValueError("Scryfall printing history exceeds record limit")
                card = json.loads(line)
                if not isinstance(card, dict) or card.get("object") != "card":
                    raise ValueError("Invalid Scryfall card record; previous catalog retained")
                yield card
    except (OSError, EOFError, zlib.error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Scryfall printing-history gzip JSONL; retain sources") from exc


async def download_history(client: httpx.AsyncClient, url: str) -> dict[str, ReleaseHistory]:
    """Stream compressed history to temporary disk, then reduce it without a full object list."""
    BulkExport.trusted_download(url)
    with (
        tempfile.TemporaryDirectory() as directory,
        (Path(directory) / "history.gz").open("w+b") as target,
    ):
        async for chunk in stream_export(client, url, _MAX_BYTES):
            target.write(chunk)
        target.seek(0)
        history = await asyncio.to_thread(release_history, _records(target))
    if len(history) < 1000:
        raise ValueError(
            "Scryfall history is empty or unexpectedly small; previous catalog retained"
        )
    return history


async def lock_generation(conn: asyncpg.Connection, started: datetime, count: int) -> bool:
    """Serialize all Scryfall writers and refuse old or suspiciously truncated snapshots."""
    await conn.execute("SELECT pg_advisory_xact_lock(71382041)")
    previous = await conn.fetchrow("SELECT * FROM new_card_catalog_state WHERE singleton")
    if previous is not None and previous["started_at"] > started:
        return False
    minimum = max(1000, int(previous["card_count"] * 0.9)) if previous else 1000
    if count < minimum:
        raise ValueError("Scryfall snapshot shrank unexpectedly; previous catalog retained")
    return True


async def publish(
    conn: asyncpg.Connection,
    cards: list[dict[str, Any]],
    history: dict[str, ReleaseHistory],
    started: datetime,
    *,
    source: source_repository.Publication | None = None,
) -> None:
    """Publish complete source facts/history atomically; never delete user plans or cards."""
    source = source or await asyncio.to_thread(source_repository.prepare, cards)
    await source_repository.publish(conn, source)
    generation = uuid4()
    rows = []
    for card in cards:
        if not card.get("oracle_id"):
            continue
        entry = history.get(card["oracle_id"], ReleaseHistory())
        facts = card_facts(card)
        rows.append(
            (
                facts.oracle_id,
                entry.first_paper,
                entry.release if paper_card(card) else None,
                facts.model_dump_json(),
                generation,
                json.dumps(source.cards[str(facts.oracle_id)]),
            )
        )
    for offset in range(0, len(rows), 500):
        await conn.executemany(
            """
            INSERT INTO new_card_catalog
                (oracle_id, first_paper, released_at, facts, generation, source_facts)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb)
            ON CONFLICT (oracle_id) DO UPDATE SET first_paper = EXCLUDED.first_paper,
                released_at = EXCLUDED.released_at, facts = EXCLUDED.facts,
                generation = EXCLUDED.generation, source_facts = EXCLUDED.source_facts
            """,
            rows[offset : offset + 500],
        )
    # Tombstone discovery only: historical facts and user decisions remain addressable.
    await conn.execute(
        "UPDATE new_card_catalog SET released_at = NULL WHERE generation <> $1", generation
    )
    await conn.execute(
        """
        INSERT INTO new_card_catalog_state
            (singleton, generation, started_at, published_at, card_count, source_sha256)
        VALUES (true, $1, $2, now(), $3, $4)
        ON CONFLICT (singleton) DO UPDATE SET generation = EXCLUDED.generation,
            started_at = EXCLUDED.started_at, published_at = EXCLUDED.published_at,
            card_count = EXCLUDED.card_count, source_sha256 = EXCLUDED.source_sha256
        """,
        generation,
        started,
        len(cards),
        source.digest,
    )
