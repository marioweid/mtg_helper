"""Moxfield top-decks recommendations: fetch + cache + score.

For each commander we fetch the top 10 most-liked Moxfield decks, resolve every
mainboard printing to its
oracle_id via Scryfall, and aggregate the oracle_ids. Cards appearing in more
of the top decks score higher. Resolving to oracle_id (vs. printing-level
scryfall_id) is what lets alternate-art / reprint references match our local
cards table, which only stores one printing per oracle.

The cache row lives in ``moxfield_commander_recs`` and is refreshed when
absent or older than ``max_age`` (default 28 days). 4xx responses persist a
sentinel empty payload so we don't keep retrying; 5xx / network errors fall
back to the cached payload (or sentinel) without persisting.
"""

import asyncio
import json
import logging
from datetime import UTC, timedelta
from typing import Any
from uuid import UUID

import asyncpg
import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession
from curl_cffi.requests.errors import RequestsError

from mtg_helper.config import settings

# Moxfield's API is behind Cloudflare's bot challenge. ``curl_cffi`` impersonates
# a real Chrome TLS fingerprint, which is what the challenge actually checks.
_IMPERSONATE_TARGET = "chrome"

_log = logging.getLogger(__name__)

_DEFAULT_MAX_AGE = timedelta(days=28)
_REQUEST_TIMEOUT = 30.0
_TOP_DECKS = 10
_SEARCH_PAGE_SIZE = 64

# Scryfall's /cards/collection accepts up to 75 identifiers per call. We use it
# to resolve Moxfield-referenced printing scryfall_ids to their oracle_ids;
# without this, alternate-art or reprint references fall through the local
# JOIN (our cards table only stores one printing per oracle).
_SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
_SCRYFALL_COLLECTION_BATCH = 75
_SCRYFALL_HEADERS = {"User-Agent": "mtg-helper/1.0", "Accept": "application/json"}
_SCRYFALL_INTER_BATCH_DELAY = 0.1

_CURVE_BUCKETS: tuple[str, ...] = ("0", "1", "2", "3", "4", "5", "6", "7+")
_MIN_CURVE_DECKS = 5

_SENTINEL_PAYLOAD: dict[str, Any] = {
    "moxfield_card_id": None,
    "decks": [],
    "by_oracle": {},
    "curve": None,
}

# Heuristic precon filter: only drop decks authored by the official accounts.
# Hub-name matching ("precon" / "preconstructed") was removed because it also
# trips on upgraded-precon decks, which carry real deck-building signal.
_PRECON_AUTHOR_USERNAMES: frozenset[str] = frozenset(
    {
        # Legacy / placeholder names kept for safety — never observed in
        # practice but cheap to keep.
        "wotc_official",
        "officialmtg",
        "moxfield",
        # Canonical Moxfield-operated host for every recent WotC precon
        # decklist — confirmed across Murders at Karlov Manor, Outlaws of
        # Thunder Junction, Modern Horizons 3, Bloomburrow, Duskmourn,
        # Aetherdrift, Tarkir Dragonstorm, Final Fantasy, Doctor Who, LotR,
        # Fallout, and Secret Lair Commander. The account bio states it's
        # Moxfield staff hosting official lists, not WotC themselves.
        "wizardsofthecoast",
        # Community accounts that systematically mirror raw precon decklists
        # (no upgrades). Identifiable by deck titles ending in "Precon
        # Decklist" and covering multiple sets.
        "kamininja",
        "edhpreconlists",
    }
)


async def fetch_moxfield_card_id(
    scryfall_id: str,
    name: str,
    *,
    client: Any,
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
    return author.lower() in _PRECON_AUTHOR_USERNAMES


async def fetch_top_decks(
    moxfield_card_id: str,
    *,
    client: Any,
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
    client: Any,
) -> list[str]:
    """Fetch mainboard scryfall ids for a Moxfield deck."""
    entries = await fetch_deck_card_entries(deck_id, client=client)
    return [entry["scryfall_id"] for entry in entries]


async def fetch_deck_card_entries(
    deck_id: str,
    *,
    client: Any,
) -> list[dict[str, Any]]:
    """Fetch mainboard cards with fields needed for inclusion and curve data.

    Commanders, sideboard, and other zones are intentionally excluded — only
    mainboard cards represent actual deck composition.
    """
    url = f"{settings.moxfield_base_url}/v3/decks/all/{deck_id}"
    response = await client.get(url)
    if response.status_code in (403, 404):
        _log.info("Moxfield deck %s not found (status %s)", deck_id, response.status_code)
        return []
    response.raise_for_status()
    boards = response.json().get("boards") or {}
    mainboard = (boards.get("mainboard") or {}).get("cards") or {}
    cards: list[dict[str, Any]] = []
    for entry in mainboard.values():
        card = entry.get("card") or {}
        sf_id = card.get("scryfall_id")
        if not sf_id:
            continue
        cards.append(
            {
                "scryfall_id": sf_id,
                "name": card.get("name"),
                "cmc": card.get("cmc") or card.get("mana_value"),
                "type_line": card.get("type_line") or card.get("type"),
                "quantity": int(entry.get("quantity") or 1),
            }
        )
    return cards


async def _resolve_oracle_ids(
    scryfall_ids: list[str],
    *,
    client: httpx.AsyncClient,
) -> dict[str, str]:
    """Batch-resolve printing scryfall_ids to oracle_ids via Scryfall.

    Moxfield's deck data references a specific printing per card; our local
    cards table only stores one printing per oracle (Scryfall's oracle_cards
    bulk). Joining on scryfall_id silently drops any deck entry whose
    printing differs from the one bulk picked. Resolving to oracle_id and
    joining there fixes that.

    Args:
        scryfall_ids: Unique printing ids (lowercased) to resolve.
        client: httpx client (no curl_cffi needed; Scryfall is not gated).

    Returns:
        Map of ``scryfall_id -> oracle_id`` (both lowercased). Missing ids
        and failed batches are omitted.
    """
    if not scryfall_ids:
        return {}
    out: dict[str, str] = {}
    for offset in range(0, len(scryfall_ids), _SCRYFALL_COLLECTION_BATCH):
        batch = scryfall_ids[offset : offset + _SCRYFALL_COLLECTION_BATCH]
        body = {"identifiers": [{"id": sf_id} for sf_id in batch]}
        try:
            response = await client.post(
                _SCRYFALL_COLLECTION_URL, json=body, headers=_SCRYFALL_HEADERS
            )
        except httpx.HTTPError as exc:
            _log.warning("Scryfall /cards/collection request error: %s", exc)
            continue
        if response.status_code >= 400:
            _log.warning(
                "Scryfall /cards/collection returned %s; skipping batch", response.status_code
            )
            continue
        for card in response.json().get("data") or []:
            sf_id = (card.get("id") or "").lower()
            oracle_id = (card.get("oracle_id") or "").lower()
            if sf_id and oracle_id:
                out[sf_id] = oracle_id
        if offset + _SCRYFALL_COLLECTION_BATCH < len(scryfall_ids):
            await asyncio.sleep(_SCRYFALL_INTER_BATCH_DELAY)
    return out


def _aggregate_payload(
    moxfield_card_id: str,
    deck_summaries: list[dict[str, Any]],
    deck_cards: list[list[str]],
    oracle_by_scryfall: dict[str, str],
    deck_card_entries: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Combine deck summaries + per-deck card lists into a cached payload.

    Counts oracle_id occurrences across decks (one increment per deck, even
    if a deck lists multiple printings of the same oracle). Entries whose
    scryfall_id failed to resolve to an oracle_id are dropped.
    """
    by_oracle: dict[str, int] = {}
    for cards in deck_cards:
        seen_in_deck: set[str] = set()
        for sf_id in cards:
            oracle_id = oracle_by_scryfall.get(sf_id.lower())
            if not oracle_id or oracle_id in seen_in_deck:
                continue
            seen_in_deck.add(oracle_id)
            by_oracle[oracle_id] = by_oracle.get(oracle_id, 0) + 1
    return {
        "moxfield_card_id": moxfield_card_id,
        "decks": deck_summaries,
        "by_oracle": by_oracle,
        "curve": _aggregate_curve(deck_card_entries or []),
    }


def _aggregate_curve(deck_card_entries: list[list[dict[str, Any]]]) -> dict[str, Any] | None:
    """Average non-land mana-value buckets across usable Moxfield decks."""
    per_deck = [_curve_for_deck(cards) for cards in deck_card_entries]
    usable = [curve for curve in per_deck if sum(curve.values()) > 0]
    if len(usable) < _MIN_CURVE_DECKS:
        return None
    averaged = {
        bucket: round(sum(curve[bucket] for curve in usable) / len(usable))
        for bucket in _CURVE_BUCKETS
    }
    return {
        "source": "moxfield",
        "deck_count": len(usable),
        "confidence": "high",
        "buckets": averaged,
    }


def _curve_for_deck(cards: list[dict[str, Any]]) -> dict[str, int]:
    buckets = {bucket: 0 for bucket in _CURVE_BUCKETS}
    for card in cards:
        if "Land" in str(card.get("type_line") or ""):
            continue
        bucket = _bucket_for_cmc(card.get("cmc"))
        buckets[bucket] += int(card.get("quantity") or 1)
    return buckets


def _bucket_for_cmc(raw: Any) -> str:
    try:
        value = int(float(raw or 0))
    except (TypeError, ValueError):
        value = 0
    return "7+" if value >= 7 else str(max(0, value))


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

    if (
        row is not None
        and _row_age(row) < max_age
        and not _is_empty_payload(row["payload"])
        and _has_curve_data(row["payload"])
    ):
        return _parse(row["payload"])

    owned_client = client is None
    http_client = client or CurlAsyncSession(
        impersonate=_IMPERSONATE_TARGET, timeout=_REQUEST_TIMEOUT
    )
    try:
        payload = await _refresh_payload(
            commander["scryfall_id"], commander["name"], client=http_client
        )
    except (httpx.HTTPError, RequestsError) as exc:
        _log.warning("Transient Moxfield error for %s: %s", commander["name"], exc)
        if row is not None:
            return _parse(row["payload"])
        return _SENTINEL_PAYLOAD
    finally:
        if owned_client:
            await _close_client(http_client)

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
    client: Any,
) -> dict[str, Any] | None:
    """Run the lookup → search → per-deck fetch → oracle-resolve pipeline."""
    moxfield_card_id = await fetch_moxfield_card_id(str(scryfall_id), commander_name, client=client)
    if moxfield_card_id is None:
        return None

    deck_summaries = await fetch_top_decks(moxfield_card_id, client=client)
    if not deck_summaries:
        return _aggregate_payload(moxfield_card_id, [], [], {})

    deck_cards: list[list[str]] = []
    deck_card_entries: list[list[dict[str, Any]]] = []
    for summary in deck_summaries:
        try:
            entries = await fetch_deck_card_entries(summary["id"], client=client)
        except (httpx.HTTPError, RequestsError) as exc:
            _log.warning("Skipping Moxfield deck %s due to error: %s", summary["id"], exc)
            continue
        deck_card_entries.append(entries)
        deck_cards.append([entry["scryfall_id"] for entry in entries])

    unique_sf_ids = sorted({sf.lower() for cards in deck_cards for sf in cards})
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as scryfall_client:
        oracle_by_scryfall = await _resolve_oracle_ids(unique_sf_ids, client=scryfall_client)

    return _aggregate_payload(
        moxfield_card_id, deck_summaries, deck_cards, oracle_by_scryfall, deck_card_entries
    )


async def _close_client(client: Any) -> None:
    """Close a moxfield client (httpx or curl_cffi) without crashing on either."""
    aclose = getattr(client, "aclose", None)
    if callable(aclose):
        await aclose()
        return
    close = getattr(client, "close", None)
    if callable(close):
        result = close()
        if hasattr(result, "__await__"):
            await result


async def score_inclusion(
    pool: asyncpg.Pool,
    payload: dict[str, Any],
    commander_color_identity: list[str],
) -> dict[UUID, float]:
    """Resolve payload scryfall ids to local UUIDs with weighted scores.

    A card present in all top decks scores 1.0; one in a single deck scores
    ``1 / _TOP_DECKS``. Uses the same color-identity, legality, and border
    filters as the hub scorer.

    Args:
        pool: asyncpg connection pool.
        payload: Cached payload (sentinel or real).
        commander_color_identity: Commander's color identity letters.

    Returns:
        ``{card_id: score}`` where score is in ``[0.0, 1.0]``.
    """
    by_oracle = payload.get("by_oracle") or {}
    if not by_oracle:
        return {}

    oracle_ids = list(by_oracle.keys())
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, oracle_id::text AS oid, color_identity
            FROM cards
            WHERE oracle_id::text = ANY($1::text[])
              AND is_canonical
              AND color_identity <@ $2::text[]
              AND legalities->>'commander' = 'legal'
              AND COALESCE(border_color, '') != 'gold'
              AND COALESCE(security_stamp, '') != 'acorn'
              AND type_line NOT LIKE '%Conspiracy%'
            """,
            oracle_ids,
            commander_color_identity,
        )
    scores: dict[UUID, float] = {}
    for row in rows:
        count = by_oracle.get(row["oid"], 0)
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


def _has_curve_data(payload: Any) -> bool:
    """Return True when a payload was produced by the curve-aware pipeline."""
    parsed = _parse(payload)
    return "curve" in parsed


def _is_empty_payload(payload: Any) -> bool:
    """Return True for sentinel rows that carry no usable inclusion signal.

    Catches three cases: (1) sentinel rows written while Moxfield was
    Cloudflare-blocked; (2) legacy rows from before the oracle-id migration,
    which only have ``by_scryfall``. Both force a refresh on next request.
    """
    parsed = _parse(payload)
    return not parsed.get("by_oracle")
