"""EDHREC commander recommendations: fetch + cache + slug derivation.

Fetches per-commander cardlists from ``json.edhrec.com`` and caches them in
``edhrec_commander_recs``. Refreshes on miss or when older than ``max_age``
(default 14 days). 4xx responses (slug not found) write a sentinel row so we
don't keep retrying; 5xx / network errors return an empty payload without
persisting.
"""

import json
import logging
import re
from datetime import UTC, timedelta
from typing import Any
from uuid import UUID

import asyncpg
import httpx

from mtg_helper.config import settings

_log = logging.getLogger(__name__)

# Real cardlist tags as they appear in EDHREC's JSON (verified 2026-04 against
# https://json.edhrec.com/pages/commanders/atraxa-praetors-voice.json).
_KNOWN_CATEGORY_TAGS: frozenset[str] = frozenset(
    {
        "newcards",
        "highsynergycards",
        "topcards",
        "gamechangers",
        "creatures",
        "instants",
        "sorceries",
        "utilityartifacts",
        "enchantments",
        "planeswalkers",
        "utilitylands",
        "manaartifacts",
        "lands",
    }
)

_DEFAULT_MAX_AGE = timedelta(days=14)
_REQUEST_TIMEOUT = 30.0

_SENTINEL_PAYLOAD: dict[str, Any] = {"categories": {}, "combos": []}

# Per-category boost weights for the deck_inclusion ranking signal. A card's
# score is the maximum weight across all categories it appears in (not the
# sum), so a card listed in highsynergycards + creatures scores 1.00, not
# 1.60.
_CATEGORY_WEIGHTS: dict[str, float] = {
    "highsynergycards": 1.00,
    "topcards": 0.85,
    "gamechangers": 0.80,  # gated on bracket >= 3 in score_inclusion
    "manaartifacts": 0.70,
    "utilityartifacts": 0.70,
    "utilitylands": 0.65,
    "creatures": 0.60,
    "instants": 0.60,
    "sorceries": 0.60,
    "enchantments": 0.60,
    "planeswalkers": 0.60,
    "lands": 0.55,
    "newcards": 0.50,
}
_COMBO_WEIGHT: float = 0.95
_GAME_CHANGERS_MIN_BRACKET: int = 3


def slugify(card_name: str) -> str:
    """Convert a commander name to its EDHREC URL slug.

    Lowercases, strips apostrophes/quotes/periods/commas, replaces remaining
    non-alphanumerics with hyphens, and collapses runs. Double-faced and split
    cards use the front face only (left of " // ").

    Examples:
        "Ms. Bumbleflower" -> "ms-bumbleflower"
        "Atraxa, Praetors' Voice" -> "atraxa-praetors-voice"
        "Bruna, the Fading Light // Brisela, Voice of Nightmares" ->
            "bruna-the-fading-light"

    Args:
        card_name: Card name as stored in our cards table.

    Returns:
        EDHREC-compatible URL slug.
    """
    front = card_name.split(" // ", maxsplit=1)[0]
    lowered = front.lower()
    stripped = re.sub(r"['\"’.,]", "", lowered)
    hyphenated = re.sub(r"[^a-z0-9]+", "-", stripped)
    return hyphenated.strip("-")


def _normalize_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduce a raw EDHREC response to the slim cached shape.

    Args:
        raw: Raw EDHREC JSON.

    Returns:
        ``{"categories": {tag: [name, ...]}, "combos": [name, ...]}``. Unknown
        category tags are skipped to keep the cache stable across upstream
        changes.
    """
    categories: dict[str, list[str]] = {}
    cardlists = raw.get("container", {}).get("json_dict", {}).get("cardlists") or []
    for cardlist in cardlists:
        tag = cardlist.get("tag")
        if tag not in _KNOWN_CATEGORY_TAGS:
            continue
        names = [cv.get("name") for cv in cardlist.get("cardviews") or [] if cv.get("name")]
        if names:
            categories[tag] = names

    combos: list[str] = []
    for entry in raw.get("panels", {}).get("combocounts") or []:
        value = entry.get("value")
        if not value or value == "See More...":
            continue
        # Format: "Card A + Card B" — split and dedupe across all combos.
        for name in (n.strip() for n in value.split(" + ")):
            if name and name not in combos:
                combos.append(name)

    return {"categories": categories, "combos": combos}


async def fetch_payload(slug: str, *, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch and normalize an EDHREC commander page.

    Args:
        slug: EDHREC slug (e.g. ``"atraxa-praetors-voice"``).
        client: Injected httpx client (lets tests stub the network).

    Returns:
        Normalized payload dict, or ``None`` when the slug is not found
        (4xx response). Raises :class:`httpx.HTTPError` on transient failures
        so the caller can decide whether to persist a sentinel.
    """
    url = f"{settings.edhrec_base_url}/{slug}.json"
    response = await client.get(url)
    if response.status_code in (403, 404):
        _log.info("EDHREC slug not found: %s (status %s)", slug, response.status_code)
        return None
    response.raise_for_status()
    return _normalize_payload(response.json())


async def get_or_refresh(
    pool: asyncpg.Pool,
    commander_id: UUID,
    *,
    max_age: timedelta = _DEFAULT_MAX_AGE,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Return cached EDHREC payload, refreshing when stale or absent.

    Args:
        pool: asyncpg connection pool.
        commander_id: Local UUID of the commander card.
        max_age: How long a cached row stays fresh.
        client: Optional injected httpx client (for tests). When None, a new
            client is created with a 30 s timeout.

    Returns:
        The normalized EDHREC payload, or the sentinel empty payload when the
        commander is missing on EDHREC. Returns the cached payload (possibly
        empty) on transient network errors so callers can keep working.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT slug, payload, fetched_at
            FROM edhrec_commander_recs
            WHERE commander_id = $1
            """,
            commander_id,
        )
        commander_name = await conn.fetchval("SELECT name FROM cards WHERE id = $1", commander_id)

    if commander_name is None:
        _log.warning("Commander %s not found; returning empty EDHREC payload", commander_id)
        return _SENTINEL_PAYLOAD

    if row is not None and _row_age(row) < max_age:
        return _parse(row["payload"])

    slug = slugify(commander_name)
    owned_client = client is None
    http_client = client or httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
    try:
        payload = await fetch_payload(slug, client=http_client)
    except httpx.HTTPError as exc:
        _log.warning("Transient EDHREC error for %s: %s", slug, exc)
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
            INSERT INTO edhrec_commander_recs (commander_id, slug, payload, fetched_at)
            VALUES ($1, $2, $3::jsonb, now())
            ON CONFLICT (commander_id) DO UPDATE SET
                slug       = EXCLUDED.slug,
                payload    = EXCLUDED.payload,
                fetched_at = now()
            """,
            commander_id,
            slug,
            json.dumps(payload_to_store),
        )
    return payload_to_store


def _collect_name_weights(payload: dict[str, Any], *, bracket: int | None) -> dict[str, float]:
    """Walk a payload and aggregate each card name's max category weight.

    ``gamechangers`` is dropped when the deck's bracket is below
    :data:`_GAME_CHANGERS_MIN_BRACKET`, mirroring EDHREC's bracket guidance.

    Args:
        payload: Normalized EDHREC payload.
        bracket: Deck's bracket (1-5); ``None`` is treated as casual / <3.

    Returns:
        ``{lower(name): weight}`` map. Names are lowercased so the SQL lookup
        can use a case-insensitive equality join.
    """
    name_weights: dict[str, float] = {}
    categories = payload.get("categories") or {}
    drop_gamechangers = bracket is None or bracket < _GAME_CHANGERS_MIN_BRACKET

    for tag, names in categories.items():
        weight = _CATEGORY_WEIGHTS.get(tag)
        if weight is None:
            continue
        if tag == "gamechangers" and drop_gamechangers:
            continue
        for name in names:
            key = name.lower()
            if weight > name_weights.get(key, 0.0):
                name_weights[key] = weight

    for name in payload.get("combos") or []:
        key = name.lower()
        if _COMBO_WEIGHT > name_weights.get(key, 0.0):
            name_weights[key] = _COMBO_WEIGHT

    return name_weights


async def score_inclusion(
    pool: asyncpg.Pool,
    payload: dict[str, Any],
    commander_color_identity: list[str],
    *,
    bracket: int | None,
) -> dict[UUID, float]:
    """Resolve EDHREC payload card names to local UUIDs with weighted scores.

    Performs a single batched ``lower(name) = ANY($1)`` lookup in ``cards``,
    filters by the commander's color identity (drops the occasional cross-
    color noise EDHREC includes via partner pages), and returns a card-id
    keyed score map ready to feed into the retrieval scorer.

    Args:
        pool: asyncpg connection pool.
        payload: Normalized EDHREC payload.
        commander_color_identity: Commander's color identity letters.
        bracket: Deck's bracket; gates ``gamechangers``.

    Returns:
        ``{card_id: score}`` where score is in [0.0, 1.0].
    """
    name_weights = _collect_name_weights(payload, bracket=bracket)
    if not name_weights:
        return {}

    lowered_names = list(name_weights.keys())
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, lower(name) AS lname, color_identity
            FROM cards
            WHERE lower(name) = ANY($1::text[])
              AND color_identity <@ $2::text[]
              AND legalities->>'commander' = 'legal'
              AND COALESCE(border_color, '') != 'gold'
              AND COALESCE(security_stamp, '') != 'acorn'
              AND type_line NOT LIKE '%Conspiracy%'
            """,
            lowered_names,
            commander_color_identity,
        )
    return {row["id"]: name_weights[row["lname"]] for row in rows}


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
