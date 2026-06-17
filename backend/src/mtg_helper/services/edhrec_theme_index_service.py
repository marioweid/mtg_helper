"""EDHREC theme/archetype index fetch, cache, and card scoring.

This is the foundation for using EDHREC as a reusable Commander knowledge
index. It maps our current deck tags to EDHREC theme pages, caches those pages,
and resolves their cardlists into local card IDs for retrieval boosts.
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
_SENTINEL_PAYLOAD: dict[str, Any] = {"categories": {}}

# Curated bridge from our current Moxfield-style tags to EDHREC theme slugs.
# This keeps existing decks working while the EDHREC-native vocabulary grows.
TAG_TO_THEME_SLUGS: dict[str, tuple[str, ...]] = {
    "aristocrats": ("aristocrats",),
    "sacrifice": ("sacrifice", "aristocrats"),
    "token": ("tokens",),
    "treasure_matters": ("treasures",),
    "food_matters": ("food",),
    "clue_matters": ("clues",),
    "plus_one_counters": ("plus-1-plus-1-counters",),
    "proliferate": ("proliferate",),
    "voltron": ("voltron",),
    "equipment": ("equipment",),
    "graveyard": ("graveyard",),
    "reanimator": ("reanimator",),
    "mill": ("mill",),
    "landfall": ("landfall",),
    "spellslinger": ("spellslinger",),
    "storm": ("storm",),
    "cascade": ("cascade",),
    "wheels": ("wheels",),
    "lifegain": ("lifegain",),
    "blink": ("blink",),
    "energy": ("energy",),
    "stax": ("stax",),
    "group_hug": ("group-hug",),
    "extra_turn": ("extra-turns",),
    "infect_toxic": ("infect",),
}

# Generic EDHREC cardlist weights. Unknown tags default to 0.55 so future
# EDHREC categories still provide signal without outranking high-synergy cards.
_CATEGORY_WEIGHTS: dict[str, float] = {
    "highsynergycards": 1.00,
    "topcards": 0.85,
    "newcards": 0.50,
    "gamechangers": 0.80,
    "creatures": 0.60,
    "instants": 0.60,
    "sorceries": 0.60,
    "utilityartifacts": 0.70,
    "enchantments": 0.60,
    "planeswalkers": 0.60,
    "utilitylands": 0.65,
    "manaartifacts": 0.70,
    "lands": 0.55,
}
_DEFAULT_CATEGORY_WEIGHT = 0.55


def theme_slugs_for_tags(tags: list[str]) -> list[str]:
    """Return EDHREC theme slugs matching our current deck tags."""
    seen: set[str] = set()
    slugs: list[str] = []
    for tag in tags:
        for slug in TAG_TO_THEME_SLUGS.get(tag, ()):
            if slug in seen:
                continue
            seen.add(slug)
            slugs.append(slug)
    return slugs


def _theme_base_url() -> str:
    root = settings.edhrec_base_url.rsplit("/commanders", maxsplit=1)[0]
    return f"{root}/themes"


def _normalize_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduce a raw EDHREC theme response to category -> card-name lists."""
    categories: dict[str, list[str]] = {}
    cardlists = raw.get("container", {}).get("json_dict", {}).get("cardlists") or []
    for cardlist in cardlists:
        tag = cardlist.get("tag") or cardlist.get("name") or "cards"
        names = [cv.get("name") for cv in cardlist.get("cardviews") or [] if cv.get("name")]
        if names:
            categories[str(tag)] = names
    return {"categories": categories}


async def fetch_theme_payload(slug: str, *, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch and normalize one EDHREC theme page."""
    response = await client.get(f"{_theme_base_url()}/{slug}.json")
    if response.status_code in (403, 404):
        _log.info("EDHREC theme slug not found: %s (status %s)", slug, response.status_code)
        return None
    response.raise_for_status()
    return _normalize_payload(response.json())


async def get_or_refresh(
    pool: asyncpg.Pool,
    slug: str,
    *,
    display_name: str | None = None,
    source_type: str = "theme",
    max_age: timedelta = _DEFAULT_MAX_AGE,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Return cached EDHREC theme payload, refreshing when stale or absent."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT payload, fetched_at
            FROM edhrec_theme_index
            WHERE slug = $1
            """,
            slug,
        )
    if row is not None and _row_age(row) < max_age:
        return _parse(row["payload"])

    owned_client = client is None
    http_client = client or httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
    try:
        payload = await fetch_theme_payload(slug, client=http_client)
    except httpx.HTTPError as exc:
        _log.warning("Transient EDHREC theme error for %s: %s", slug, exc)
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
            INSERT INTO edhrec_theme_index (slug, display_name, source_type, payload, fetched_at)
            VALUES ($1, $2, $3, $4::jsonb, now())
            ON CONFLICT (slug) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                source_type  = EXCLUDED.source_type,
                payload      = EXCLUDED.payload,
                fetched_at   = now()
            """,
            slug,
            display_name or slug.replace("-", " ").title(),
            source_type,
            json.dumps(payload_to_store),
        )
    return payload_to_store


def _collect_name_weights(payload: dict[str, Any]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for category, names in (payload.get("categories") or {}).items():
        weight = _CATEGORY_WEIGHTS.get(category, _DEFAULT_CATEGORY_WEIGHT)
        for name in names:
            key = str(name).lower()
            if weight > weights.get(key, 0.0):
                weights[key] = weight
    return weights


async def score_themes(
    pool: asyncpg.Pool,
    tags: list[str],
    commander_color_identity: list[str],
) -> dict[UUID, float]:
    """Resolve indexed EDHREC theme cards for tags into local card-id scores."""
    slugs = theme_slugs_for_tags(tags)
    if not slugs:
        return {}

    name_weights: dict[str, float] = {}
    for slug in slugs:
        payload = await get_or_refresh(pool, slug)
        for name, weight in _collect_name_weights(payload).items():
            if weight > name_weights.get(name, 0.0):
                name_weights[name] = weight
    if not name_weights:
        return {}

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, lower(name) AS lname
            FROM cards
            WHERE lower(name) = ANY($1::text[])
              AND color_identity <@ $2::text[]
              AND legalities->>'commander' = 'legal'
              AND COALESCE(border_color, '') != 'gold'
              AND COALESCE(security_stamp, '') != 'acorn'
              AND type_line NOT LIKE '%Conspiracy%'
            """,
            list(name_weights.keys()),
            commander_color_identity,
        )
    return {row["id"]: name_weights[row["lname"]] for row in rows}


def _row_age(row: asyncpg.Record) -> timedelta:
    from datetime import datetime

    return datetime.now(tz=UTC) - row["fetched_at"]


def _parse(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        return json.loads(payload)
    return _SENTINEL_PAYLOAD
