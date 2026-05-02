"""Moxfield top-decks recommendations: fetch + cache + score.

Mirrors :mod:`mtg_helper.services.edhrec_service`. For each commander we fetch
the top 5 most-liked Moxfield decks and aggregate the scryfall ids of every
mainboard card. Cards appearing in more of the top decks score higher.

The cache row lives in ``moxfield_commander_recs`` and is refreshed when
absent or older than ``max_age`` (default 28 days). 4xx responses persist a
sentinel empty payload so we don't keep retrying; 5xx / network errors fall
back to the cached payload (or sentinel) without persisting.
"""

import json
import logging
from datetime import UTC, timedelta
from typing import Any
from uuid import UUID

import asyncpg
import httpx

from mtg_helper.config import settings

_log = logging.getLogger(__name__)

_DEFAULT_MAX_AGE = timedelta(days=28)
_REQUEST_TIMEOUT = 30.0
_TOP_DECKS = 10
_SEARCH_PAGE_SIZE = 64

_SENTINEL_PAYLOAD: dict[str, Any] = {
    "moxfield_card_id": None,
    "decks": [],
    "by_scryfall": {},
}

# Heuristic precon filter. Conservative — under-filtering is fine, over-
# filtering throws away signal. Author usernames are case-insensitive.
_PRECON_AUTHOR_USERNAMES: frozenset[str] = frozenset({"wotc_official", "officialmtg", "moxfield"})
_PRECON_HUB_KEYWORDS: tuple[str, ...] = ("precon", "preconstructed")


async def fetch_moxfield_card_id(
    scryfall_id: str,
    name: str,
    *,
    client: httpx.AsyncClient,
) -> str | None:
    """Look up the Moxfield card id for a commander.

    Calls ``/v3/cards/named?q=<name>&count=10`` and prefers the entry whose
    ``scryfall_id`` matches our local card. Falls back to the first result
    when no exact scryfall match exists (Moxfield occasionally returns only
    alternate printings).

    Args:
        scryfall_id: The commander's Scryfall UUID (string form).
        name: The commander's display name; used as the search query.
        client: Injected httpx client.

    Returns:
        Moxfield card id (e.g. ``"N978l"``), or ``None`` when the lookup
        returns no results or 4xx.
    """
    url = f"{settings.moxfield_base_url}/v3/cards/named"
    response = await client.get(url, params={"q": name, "count": 10})
    if response.status_code in (403, 404):
        _log.info("Moxfield card lookup not found for %s (status %s)", name, response.status_code)
        return None
    response.raise_for_status()
    cards = response.json().get("cards") or []
    if not cards:
        return None
    target = scryfall_id.lower()
    for entry in cards:
        if (entry.get("scryfall_id") or "").lower() == target:
            return entry.get("id")
    return cards[0].get("id")


def _is_precon(deck: dict[str, Any]) -> bool:
    """Best-effort precon detector for a Moxfield search result deck."""
    author = (deck.get("createdByUser") or {}).get("userName") or ""
    if author.lower() in _PRECON_AUTHOR_USERNAMES:
        return True
    hubs = deck.get("hubs") or []
    for hub in hubs:
        name = (hub.get("name") if isinstance(hub, dict) else hub) or ""
        lowered = str(name).lower()
        if any(keyword in lowered for keyword in _PRECON_HUB_KEYWORDS):
            return True
    return False


async def fetch_top_decks(
    moxfield_card_id: str,
    *,
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    """Fetch the top-liked decks for a commander, dropping precons.

    Args:
        moxfield_card_id: Moxfield's card id, as returned by
            :func:`fetch_moxfield_card_id`.
        client: Injected httpx client.

    Returns:
        Up to ``_TOP_DECKS`` deck summary dicts (``id``, ``likes``), already
        ordered by likes descending.
    """
    url = f"{settings.moxfield_base_url}/v2/decks/search"
    params = {
        "pageNumber": 1,
        "pageSize": _SEARCH_PAGE_SIZE,
        "sortType": "likes",
        "sortDirection": "descending",
        "commanderCardId": moxfield_card_id,
    }
    response = await client.get(url, params=params)
    if response.status_code in (403, 404):
        _log.info(
            "Moxfield deck search not found for card %s (status %s)",
            moxfield_card_id,
            response.status_code,
        )
        return []
    response.raise_for_status()
    raw_decks = response.json().get("data") or []

    summaries: list[dict[str, Any]] = []
    for deck in raw_decks:
        if _is_precon(deck):
            continue
        public_id = deck.get("publicId") or deck.get("id")
        if not public_id:
            continue
        summaries.append(
            {
                "id": public_id,
                "likes": int(deck.get("likeCount") or 0),
            }
        )
        if len(summaries) >= _TOP_DECKS:
            break
    return summaries


async def fetch_deck_cards(
    deck_id: str,
    *,
    client: httpx.AsyncClient,
) -> list[str]:
    """Fetch the mainboard scryfall ids for a Moxfield deck.

    Commanders, sideboard, and other zones are intentionally excluded — only
    mainboard cards represent actual deck composition.

    Args:
        deck_id: Moxfield public deck id.
        client: Injected httpx client.

    Returns:
        List of scryfall id strings (one per unique mainboard card).
    """
    url = f"{settings.moxfield_base_url}/v3/decks/all/{deck_id}"
    response = await client.get(url)
    if response.status_code in (403, 404):
        _log.info("Moxfield deck %s not found (status %s)", deck_id, response.status_code)
        return []
    response.raise_for_status()
    boards = response.json().get("boards") or {}
    mainboard = (boards.get("mainboard") or {}).get("cards") or {}
    scryfall_ids: list[str] = []
    for entry in mainboard.values():
        card = entry.get("card") or {}
        sf_id = card.get("scryfall_id")
        if sf_id:
            scryfall_ids.append(sf_id)
    return scryfall_ids


def _aggregate_payload(
    moxfield_card_id: str,
    deck_summaries: list[dict[str, Any]],
    deck_cards: list[list[str]],
) -> dict[str, Any]:
    """Combine deck summaries + per-deck card lists into a cached payload."""
    by_scryfall: dict[str, int] = {}
    for cards in deck_cards:
        seen_in_deck: set[str] = set()
        for sf_id in cards:
            normalized = sf_id.lower()
            if normalized in seen_in_deck:
                continue
            seen_in_deck.add(normalized)
            by_scryfall[normalized] = by_scryfall.get(normalized, 0) + 1
    return {
        "moxfield_card_id": moxfield_card_id,
        "decks": deck_summaries,
        "by_scryfall": by_scryfall,
    }


async def get_or_refresh(
    pool: asyncpg.Pool,
    commander_id: UUID,
    *,
    max_age: timedelta = _DEFAULT_MAX_AGE,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Return cached Moxfield payload, refreshing when stale or absent.

    Args:
        pool: asyncpg connection pool.
        commander_id: Local UUID of the commander card.
        max_age: How long a cached row stays fresh.
        client: Optional injected httpx client; when ``None`` a 30 s-timeout
            client is created and closed for the call.

    Returns:
        Aggregated payload, or the sentinel empty payload when the commander
        cannot be matched on Moxfield. Returns the cached payload (possibly
        empty) on transient errors so callers keep working.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT moxfield_card_id, payload, fetched_at
            FROM moxfield_commander_recs
            WHERE commander_id = $1
            """,
            commander_id,
        )
        commander = await conn.fetchrow(
            "SELECT name, scryfall_id FROM cards WHERE id = $1", commander_id
        )

    if commander is None:
        _log.warning("Commander %s not found; returning empty Moxfield payload", commander_id)
        return _SENTINEL_PAYLOAD

    if row is not None and _row_age(row) < max_age:
        return _parse(row["payload"])

    owned_client = client is None
    http_client = client or httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
    try:
        payload = await _refresh_payload(
            commander["scryfall_id"], commander["name"], client=http_client
        )
    except httpx.HTTPError as exc:
        _log.warning("Transient Moxfield error for %s: %s", commander["name"], exc)
        if row is not None:
            return _parse(row["payload"])
        return _SENTINEL_PAYLOAD
    finally:
        if owned_client:
            await http_client.aclose()

    payload_to_store = payload if payload is not None else _SENTINEL_PAYLOAD
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO moxfield_commander_recs
                (commander_id, moxfield_card_id, payload, fetched_at)
            VALUES ($1, $2, $3::jsonb, now())
            ON CONFLICT (commander_id) DO UPDATE SET
                moxfield_card_id = EXCLUDED.moxfield_card_id,
                payload          = EXCLUDED.payload,
                fetched_at       = now()
            """,
            commander_id,
            payload_to_store.get("moxfield_card_id"),
            json.dumps(payload_to_store),
        )
    return payload_to_store


async def _refresh_payload(
    scryfall_id: str | UUID,
    commander_name: str,
    *,
    client: httpx.AsyncClient,
) -> dict[str, Any] | None:
    """Run the lookup → search → per-deck fetch pipeline."""
    moxfield_card_id = await fetch_moxfield_card_id(str(scryfall_id), commander_name, client=client)
    if moxfield_card_id is None:
        return None

    deck_summaries = await fetch_top_decks(moxfield_card_id, client=client)
    if not deck_summaries:
        return _aggregate_payload(moxfield_card_id, [], [])

    deck_cards: list[list[str]] = []
    for summary in deck_summaries:
        try:
            cards = await fetch_deck_cards(summary["id"], client=client)
        except httpx.HTTPError as exc:
            _log.warning("Skipping Moxfield deck %s due to error: %s", summary["id"], exc)
            continue
        deck_cards.append(cards)
    return _aggregate_payload(moxfield_card_id, deck_summaries, deck_cards)


async def score_inclusion(
    pool: asyncpg.Pool,
    payload: dict[str, Any],
    commander_color_identity: list[str],
) -> dict[UUID, float]:
    """Resolve payload scryfall ids to local UUIDs with weighted scores.

    A card present in all top decks scores 1.0; one in a single deck scores
    ``1 / _TOP_DECKS``. Same color-identity / legality / border filter as
    EDHREC's :func:`mtg_helper.services.edhrec_service.score_inclusion`.

    Args:
        pool: asyncpg connection pool.
        payload: Cached payload (sentinel or real).
        commander_color_identity: Commander's color identity letters.

    Returns:
        ``{card_id: score}`` where score is in ``[0.0, 1.0]``.
    """
    by_scryfall = payload.get("by_scryfall") or {}
    if not by_scryfall:
        return {}

    scryfall_ids = list(by_scryfall.keys())
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, scryfall_id::text AS sf_id, color_identity
            FROM cards
            WHERE scryfall_id::text = ANY($1::text[])
              AND color_identity <@ $2::text[]
              AND legalities->>'commander' = 'legal'
              AND COALESCE(border_color, '') != 'gold'
              AND COALESCE(security_stamp, '') != 'acorn'
              AND type_line NOT LIKE '%Conspiracy%'
            """,
            scryfall_ids,
            commander_color_identity,
        )
    scores: dict[UUID, float] = {}
    for row in rows:
        count = by_scryfall.get(row["sf_id"], 0)
        if not count:
            continue
        scores[row["id"]] = min(1.0, count / _TOP_DECKS)
    return scores


def _row_age(row: asyncpg.Record) -> timedelta:
    """Return the age of a cache row, computed against the row's own timestamp."""
    from datetime import datetime

    fetched_at = row["fetched_at"]
    return datetime.now(tz=UTC) - fetched_at


def _parse(payload: Any) -> dict[str, Any]:
    """Coerce a payload column value into a plain dict."""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        return json.loads(payload)
    return _SENTINEL_PAYLOAD
