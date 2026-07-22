"""Fetch and cache Archidekt deck-frequency evidence for one commander."""

import asyncio
import json
import logging
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
import httpx

from mtg_helper.config import settings
from mtg_helper.services.deck_url_import_service import (
    DeckFetchError,
    FetchedDeck,
    fetch_archidekt_deck,
)

_log = logging.getLogger(__name__)

DEFAULT_MAX_AGE = timedelta(days=28)
_REQUEST_TIMEOUT = 30.0
_MAX_DECKS = 20
_MAX_CANDIDATES = 80
_FETCH_CONCURRENCY = 4
_MIN_DECK_CARDS = 50
_MAX_DECK_CARDS = 120
_PAYLOAD_VERSION = 1
_DECK_LINK = re.compile(r'href=["\']/decks/(?P<id>\d+)(?:/[^"\']*)?["\']')

_EMPTY_PAYLOAD: dict[str, Any] = {
    "version": _PAYLOAD_VERSION,
    "decks": [],
    "by_name": {},
    "sample_size": 0,
    "diagnostic": None,
}


def _parse(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        return json.loads(payload)
    return dict(_EMPTY_PAYLOAD)


def _age(fetched_at: datetime) -> timedelta:
    return datetime.now(tz=UTC) - fetched_at


def _normalized_names(name: str) -> set[str]:
    return {part.strip().casefold() for part in name.split(" // ") if part.strip()}


def _has_commander(deck: FetchedDeck, commander_name: str) -> bool:
    expected = _normalized_names(commander_name)
    return any(expected & _normalized_names(actual) for actual in deck.commanders)


def _probable_raw_precon(deck: FetchedDeck) -> bool:
    name = (deck.name or "").casefold()
    return "precon" in name and "upgrade" not in name


def _plausible_commander_deck(deck: FetchedDeck) -> bool:
    return _MIN_DECK_CARDS <= len(deck.entries) <= _MAX_DECK_CARDS


async def _search_deck_ids(client: httpx.AsyncClient, commander_name: str) -> list[str]:
    response = await client.get(
        "https://archidekt.com/search/decks",
        params={
            "cardName": commander_name,
            "deckFormat": 3,
            "orderBy": "-viewCount",
        },
    )
    response.raise_for_status()
    ids: list[str] = []
    for match in _DECK_LINK.finditer(response.text):
        deck_id = match.group("id")
        if deck_id not in ids:
            ids.append(deck_id)
        if len(ids) >= _MAX_CANDIDATES:
            break
    return ids


async def _fetch_candidate(
    client: httpx.AsyncClient,
    deck_id: str,
    commander_name: str,
    semaphore: asyncio.Semaphore,
) -> FetchedDeck | None:
    async with semaphore:
        try:
            deck = await fetch_archidekt_deck(deck_id, client=client)
        except (DeckFetchError, httpx.HTTPError) as exc:
            _log.info("Skipping Archidekt deck %s: %s", deck_id, exc)
            return None
    if (
        not _has_commander(deck, commander_name)
        or _probable_raw_precon(deck)
        or not _plausible_commander_deck(deck)
    ):
        return None
    return deck


async def _fetch_valid_decks(
    client: httpx.AsyncClient,
    deck_ids: list[str],
    commander_name: str,
) -> list[FetchedDeck]:
    semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)
    valid: list[FetchedDeck] = []
    for offset in range(0, len(deck_ids), _FETCH_CONCURRENCY):
        batch = deck_ids[offset : offset + _FETCH_CONCURRENCY]
        results = await asyncio.gather(
            *(_fetch_candidate(client, deck_id, commander_name, semaphore) for deck_id in batch)
        )
        valid.extend(deck for deck in results if deck is not None)
        if len(valid) >= _MAX_DECKS:
            return valid[:_MAX_DECKS]
        if offset + _FETCH_CONCURRENCY < len(deck_ids):
            await asyncio.sleep(max(0.0, settings.archidekt_tag_delay_seconds))
    return valid


def _aggregate(decks: list[FetchedDeck]) -> dict[str, Any]:
    tally: Counter[str] = Counter()
    summaries: list[dict[str, Any]] = []
    for deck in decks:
        names = {entry.name.strip().casefold() for entry in deck.entries if entry.name.strip()}
        tally.update(names)
        summaries.append({"id": deck.source_deck_id, "name": deck.name, "views": None})
    return {
        "version": _PAYLOAD_VERSION,
        "decks": summaries,
        "by_name": dict(tally),
        "sample_size": len(decks),
        "diagnostic": None if decks else "No matching public Archidekt decks found",
    }


async def _refresh(commander_name: str) -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "mtg-helper/1.0"},
    ) as client:
        deck_ids = await _search_deck_ids(client, commander_name)
        if not deck_ids:
            payload = dict(_EMPTY_PAYLOAD)
            payload["diagnostic"] = "Archidekt search returned no public decks"
            return payload
        decks = await _fetch_valid_decks(client, deck_ids, commander_name)
    return _aggregate(decks)


async def get_or_refresh(
    pool: asyncpg.Pool,
    commander_id: UUID,
    *,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> dict[str, Any]:
    """Return cached commander evidence, refreshing missing or stale rows."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT payload, fetched_at FROM archidekt_commander_recs WHERE commander_id = $1",
            commander_id,
        )
        commander_name = await conn.fetchval("SELECT name FROM cards WHERE id = $1", commander_id)
    if commander_name is None:
        return {**_EMPTY_PAYLOAD, "diagnostic": "Commander not found"}
    if row is not None:
        payload = _parse(row["payload"])
        if payload.get("version") == _PAYLOAD_VERSION and _age(row["fetched_at"]) < max_age:
            return payload
    try:
        payload = await _refresh(commander_name)
    except (httpx.HTTPError, DeckFetchError, ValueError) as exc:
        _log.warning("Archidekt commander refresh failed for %s: %s", commander_name, exc)
        if row is not None:
            stale = _parse(row["payload"])
            return {**stale, "runtime_error": "Archidekt refresh failed; using cached data"}
        return {**_EMPTY_PAYLOAD, "runtime_error": "Archidekt is currently unavailable"}
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO archidekt_commander_recs (commander_id, payload, fetched_at)
            VALUES ($1, $2::jsonb, now())
            ON CONFLICT (commander_id) DO UPDATE
            SET payload = EXCLUDED.payload, fetched_at = now()
            """,
            commander_id,
            json.dumps(payload),
        )
    return payload
