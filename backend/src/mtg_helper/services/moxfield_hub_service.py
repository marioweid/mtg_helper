"""Moxfield hub catalog and hub-card membership sync."""

import asyncio
import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg
import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession
from curl_cffi.requests.errors import RequestsError

from mtg_helper.config import settings
from mtg_helper.services import moxfield_recs_service

_log = logging.getLogger(__name__)

_IMPERSONATE_TARGET = "chrome"
_REQUEST_TIMEOUT = 30.0
_HUB_PAGE_SIZE = 200
_HUB_DECK_SAMPLE = 10
_BASELINE_DECK_SAMPLE = 80
_DECK_FETCH_CONCURRENCY = 1
_MIN_HUB_DECKS = 5
_MIN_HUB_PCT = 0.10
_MIN_SYNERGY = 0.05
_BASIC_LANDS = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "snow-covered plains",
        "snow-covered island",
        "snow-covered swamp",
        "snow-covered mountain",
        "snow-covered forest",
    }
)


@dataclass(frozen=True)
class Hub:
    """One Moxfield hub catalog item."""

    id: int
    tag: str
    slug: str
    name: str
    description: str | None
    shows_in_decklist: bool


async def sync_hubs(pool: asyncpg.Pool) -> dict[str, Any]:
    """Refresh the Moxfield hub catalog without rebuilding card stats."""
    async with CurlAsyncSession(
        impersonate=_IMPERSONATE_TARGET,
        timeout=_REQUEST_TIMEOUT,
    ) as client:
        hubs = await fetch_hubs(client=client)
    async with pool.acquire() as conn:
        await _upsert_hubs(conn, hubs)
    return {"moxfield_hubs_processed": len(hubs)}


async def sync_hub_card_stats(
    pool: asyncpg.Pool,
    *,
    progress: Any | None = None,
) -> dict[str, Any]:
    """Sync active Moxfield hubs and derive card membership from deck samples."""
    async with CurlAsyncSession(
        impersonate=_IMPERSONATE_TARGET,
        timeout=_REQUEST_TIMEOUT,
    ) as client:
        hubs = await fetch_hubs(client=client)
        async with pool.acquire() as conn:
            await _upsert_hubs(conn, hubs)
            stale_hub_ids = await _stale_hub_ids(conn, hubs)
        stale_hubs = [hub for hub in hubs if hub.id in stale_hub_ids]
        if not stale_hubs:
            return {
                "moxfield_hubs_processed": 0,
                "moxfield_hubs_skipped": len(hubs),
                "moxfield_hub_cards_matched": 0,
                "baseline_decks_sampled": 0,
                "hub_delay_seconds": settings.moxfield_hub_delay_seconds,
                "stale_after_hours": settings.moxfield_hub_stale_after_hours,
            }
        baseline = await _sample_decks(client, None, _BASELINE_DECK_SAMPLE)
        baseline_tally = await _tally_decks(client, baseline)
        total = len(stale_hubs)
        processed = 0
        matched_cards = 0
        for hub in stale_hubs:
            if progress is not None:
                progress(f"syncing hub {hub.name}", processed, total)
            deck_ids = await _sample_decks(client, hub.name, _HUB_DECK_SAMPLE)
            hub_tally = await _tally_decks(client, deck_ids)
            stats = _score_hub_cards(hub_tally, baseline_tally, len(deck_ids), len(baseline))
            matched_cards += await _store_hub_stats(pool, hub, stats, len(deck_ids), len(baseline))
            processed += 1
            if processed < total:
                await _sleep_between_hubs()
        if progress is not None:
            progress("syncing hubs", total, total)
    await rebuild_card_hub_tags(pool)
    return {
        "moxfield_hubs_processed": len(stale_hubs),
        "moxfield_hubs_skipped": len(hubs) - len(stale_hubs),
        "moxfield_hub_cards_matched": matched_cards,
        "baseline_decks_sampled": len(baseline),
        "hub_delay_seconds": settings.moxfield_hub_delay_seconds,
        "stale_after_hours": settings.moxfield_hub_stale_after_hours,
    }


async def sync_one_hub_card_stats(
    pool: asyncpg.Pool,
    *,
    hub_ref: str,
    hub_sample_size: int = _HUB_DECK_SAMPLE,
    baseline_sample_size: int = _BASELINE_DECK_SAMPLE,
    deck_ids: list[str] | None = None,
    baseline_deck_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Refresh card membership for one Moxfield hub."""
    hub_sample_size = _clamp_sample_size(hub_sample_size)
    baseline_sample_size = _clamp_sample_size(baseline_sample_size)
    async with CurlAsyncSession(
        impersonate=_IMPERSONATE_TARGET,
        timeout=_REQUEST_TIMEOUT,
    ) as client:
        hubs = await fetch_hubs(client=client)
        hub = _find_hub(hubs, hub_ref)
        if hub is None:
            raise ValueError(f"Moxfield hub not found: {hub_ref}")
        baseline_ids = baseline_deck_ids or await _sample_decks(
            client,
            None,
            baseline_sample_size,
        )
        hub_ids = deck_ids or await _sample_decks(client, hub.name, hub_sample_size)
        baseline_tally = await _tally_decks(client, baseline_ids)
        hub_tally = await _tally_decks(client, hub_ids)
        stats = _score_hub_cards(hub_tally, baseline_tally, len(hub_ids), len(baseline_ids))
        async with pool.acquire() as conn:
            await _upsert_hubs(conn, hubs)
        matched_cards = await _store_hub_stats(pool, hub, stats, len(hub_ids), len(baseline_ids))
    await rebuild_card_hub_tags(pool)
    return {
        "moxfield_hubs_processed": 1,
        "hub": hub.tag,
        "hub_name": hub.name,
        "moxfield_hub_cards_matched": matched_cards,
        "hub_decks_sampled": len(hub_ids),
        "baseline_decks_sampled": len(baseline_ids),
        "explicit_hub_decks": deck_ids is not None,
        "explicit_baseline_decks": baseline_deck_ids is not None,
    }


async def load_hub_tags(pool: asyncpg.Pool) -> set[str]:
    """Return active Moxfield hub tag ids."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tag FROM moxfield_hubs WHERE active AND enabled ORDER BY name"
        )
    return {row["tag"] for row in rows}


async def load_hub_prompt_catalog(pool: asyncpg.Pool) -> str:
    """Return compact hub lines for LLM keyword extraction prompts."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT h.tag, h.name, count(s.card_id) AS card_count
            FROM moxfield_hubs h
            LEFT JOIN moxfield_hub_card_stats s ON s.hub_id = h.id
            WHERE h.active AND h.enabled
            GROUP BY h.id, h.tag, h.name
            ORDER BY h.name
            """
        )
    return "\n".join(f"- {row['tag']}: {row['name']} ({row['card_count']} cards)" for row in rows)


async def list_hub_tag_groups(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return frontend-ready active Moxfield hub groups."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tag, name, description
            FROM moxfield_hubs
            WHERE active AND enabled
            ORDER BY name
            """
        )
    return [
        {
            "category": "moxfield_hubs",
            "display_name": "Moxfield themes",
            "keywords": [
                {"tag": row["tag"], "label": row["name"], "deck_count": None} for row in rows
            ],
        }
    ]


async def list_hubs(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return active Moxfield hubs for admin controls."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT h.id, h.tag, h.name, h.description, h.active, h.enabled,
                   h.last_seen_at, h.synced_at, h.last_card_sync_at,
                   count(s.card_id) AS card_count,
                   max(s.fetched_at) AS last_stat_fetch_at
            FROM moxfield_hubs h
            LEFT JOIN moxfield_hub_card_stats s ON s.hub_id = h.id
            GROUP BY h.id
            ORDER BY h.name
            """
        )
    return [dict(row) for row in rows]


async def score_hubs(
    pool: asyncpg.Pool,
    tags: list[str],
    commander_color_identity: list[str],
) -> dict[UUID, float]:
    """Resolve selected hub tags into local card-id synergy scores."""
    if not tags:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT canonical.id AS card_id, max(s.synergy_score) AS score
            FROM moxfield_hub_card_stats s
            JOIN moxfield_hubs h ON h.id = s.hub_id
            JOIN cards source ON source.id = s.card_id
            JOIN cards canonical
              ON COALESCE(canonical.oracle_id, canonical.id)
               = COALESCE(source.oracle_id, source.id)
             AND canonical.is_canonical
            WHERE h.tag = ANY($1::text[])
              AND h.active AND h.enabled
              AND canonical.color_identity <@ $2::text[]
              AND canonical.legalities->>'commander' = 'legal'
              AND COALESCE(canonical.border_color, '') != 'gold'
              AND COALESCE(canonical.security_stamp, '') != 'acorn'
              AND canonical.type_line NOT LIKE '%Conspiracy%'
            GROUP BY canonical.id
            """,
            tags,
            commander_color_identity,
        )
    return {row["card_id"]: float(row["score"] or 0.0) for row in rows}


async def rebuild_card_hub_tags(pool: asyncpg.Pool) -> None:
    """Denormalize hub membership onto cards for fast tag filtering."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE cards SET hub_tags = '{}'")
        await conn.execute(
            """
            UPDATE cards c
            SET hub_tags = ranked.tags
            FROM (
                SELECT card_id, array_agg(tag ORDER BY score DESC, tag) AS tags
                FROM (
                    SELECT s.card_id, h.tag, max(s.synergy_score) AS score
                    FROM moxfield_hub_card_stats s
                    JOIN moxfield_hubs h ON h.id = s.hub_id
                    WHERE h.active AND h.enabled
                    GROUP BY s.card_id, h.tag
                ) x
                GROUP BY card_id
            ) ranked
            WHERE c.id = ranked.card_id
            """
        )


async def fetch_hubs(*, client: Any) -> list[Hub]:
    """Fetch all hubs from Moxfield's paginated hub catalog."""
    hubs: list[Hub] = []
    page = 1
    while True:
        response = await client.get(
            f"{settings.moxfield_base_url}/v1/hubs",
            params={"pageNumber": page, "pageSize": _HUB_PAGE_SIZE},
        )
        response.raise_for_status()
        payload = response.json()
        for raw in payload.get("data") or []:
            hub = _hub_from_raw(raw)
            if hub is not None:
                hubs.append(hub)
        if page >= int(payload.get("totalPages") or page):
            break
        page += 1
    return hubs


async def _sleep_between_hubs() -> None:
    delay = max(0.0, settings.moxfield_hub_delay_seconds)
    if delay > 0:
        await asyncio.sleep(delay)


def _clamp_sample_size(value: int) -> int:
    return min(200, max(1, int(value)))


def _find_hub(hubs: list[Hub], hub_ref: str) -> Hub | None:
    needle = hub_ref.strip().lower()
    if not needle:
        return None
    for hub in hubs:
        if needle in {str(hub.id), hub.tag.lower(), hub.slug.lower(), hub.name.lower()}:
            return hub
    return None


async def _stale_hub_ids(conn: asyncpg.Connection, hubs: list[Hub]) -> set[int]:
    ids = [hub.id for hub in hubs]
    if not ids:
        return set()
    stale_after_hours = max(0.0, settings.moxfield_hub_stale_after_hours)
    rows = await conn.fetch(
        """
        SELECT id
        FROM moxfield_hubs
        WHERE id = ANY($1::int[])
          AND enabled
          AND (
              last_card_sync_at IS NULL
              OR last_card_sync_at <= now() - ($2::float * interval '1 hour')
          )
        """,
        ids,
        stale_after_hours,
    )
    return {row["id"] for row in rows}


async def _upsert_hubs(conn: asyncpg.Connection, hubs: list[Hub]) -> None:
    rows = [(h.id, h.slug, h.tag, h.name, h.description, h.shows_in_decklist) for h in hubs]
    ids = [h.id for h in hubs]
    async with conn.transaction():
        await conn.executemany(
            """
            INSERT INTO moxfield_hubs
                (id, slug, tag, name, description, shows_in_decklist, active,
                 first_seen_at, last_seen_at, synced_at)
            VALUES ($1, $2, $3, $4, $5, $6, true, now(), now(), now())
            ON CONFLICT (id) DO UPDATE SET
                slug = EXCLUDED.slug,
                tag = EXCLUDED.tag,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                shows_in_decklist = EXCLUDED.shows_in_decklist,
                active = true,
                last_seen_at = now(),
                synced_at = now()
            """,
            rows,
        )
        if ids:
            await conn.execute(
                "UPDATE moxfield_hubs SET active = false WHERE id != ALL($1::int[])",
                ids,
            )


async def _sample_decks(client: Any, hub_name: str | None, sample_size: int) -> list[str]:
    url = f"{settings.moxfield_base_url}/v2/decks/search"
    params: dict[str, Any] = {
        "pageNumber": 1,
        "pageSize": sample_size,
        "sortType": "updated",
        "sortDirection": "descending",
        "fmt": "commander",
    }
    if hub_name:
        params["hubName"] = hub_name
    response = await client.get(url, params=params)
    response.raise_for_status()
    deck_ids: list[str] = []
    for deck in response.json().get("data") or []:
        public_id = deck.get("publicId") or deck.get("id")
        if public_id:
            deck_ids.append(public_id)
    return deck_ids


async def _tally_decks(client: Any, deck_ids: list[str]) -> Counter[str]:
    semaphore = asyncio.Semaphore(_DECK_FETCH_CONCURRENCY)

    async def _fetch(deck_id: str) -> list[str]:
        async with semaphore:
            try:
                entries = await moxfield_recs_service.fetch_deck_card_entries(
                    deck_id,
                    client=client,
                )
            except (httpx.HTTPError, RequestsError) as exc:
                _log.warning("Skipping Moxfield deck %s while syncing hubs: %s", deck_id, exc)
                return []
            names: list[str] = []
            for entry in entries:
                name = _entry_name(entry)
                if name and name.lower() not in _BASIC_LANDS:
                    names.append(name)
            return sorted(set(names))

    tally: Counter[str] = Counter()
    for names in await asyncio.gather(*(_fetch(deck_id) for deck_id in deck_ids)):
        tally.update(names)
    return tally


def _score_hub_cards(
    hub_tally: Counter[str],
    baseline_tally: Counter[str],
    hub_sample: int,
    baseline_sample: int,
) -> dict[str, tuple[int, int, float, float, float]]:
    if hub_sample < _MIN_HUB_DECKS or baseline_sample == 0:
        return {}
    scores: dict[str, tuple[int, int, float, float, float]] = {}
    for name, hub_count in hub_tally.items():
        hub_pct = hub_count / hub_sample
        baseline_count = baseline_tally.get(name, 0)
        baseline_pct = baseline_count / baseline_sample
        synergy = hub_pct - baseline_pct
        if hub_pct < _MIN_HUB_PCT or synergy < _MIN_SYNERGY:
            continue
        scores[name] = (hub_count, baseline_count, hub_pct, baseline_pct, synergy)
    return scores


async def _store_hub_stats(
    pool: asyncpg.Pool,
    hub: Hub,
    stats: dict[str, tuple[int, int, float, float, float]],
    hub_sample: int,
    baseline_sample: int,
) -> int:
    names = list(stats)
    if not names:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM moxfield_hub_card_stats WHERE hub_id = $1", hub.id)
                await conn.execute(
                    "UPDATE moxfield_hubs SET last_card_sync_at = now() WHERE id = $1",
                    hub.id,
                )
        return 0
    async with pool.acquire() as conn:
        card_rows = await conn.fetch(
            "SELECT id, name FROM cards WHERE is_canonical AND lower(name) = ANY($1::text[])",
            [name.lower() for name in names],
        )
        cards_by_name = {row["name"].lower(): row["id"] for row in card_rows}
        rows = [
            (hub.id, cards_by_name[name.lower()], *values, hub_sample, baseline_sample)
            for name, values in stats.items()
            if name.lower() in cards_by_name
        ]
        async with conn.transaction():
            await conn.execute("DELETE FROM moxfield_hub_card_stats WHERE hub_id = $1", hub.id)
            await conn.execute(
                "UPDATE moxfield_hubs SET last_card_sync_at = now() WHERE id = $1",
                hub.id,
            )
            await conn.executemany(
                """
                INSERT INTO moxfield_hub_card_stats
                    (hub_id, card_id, hub_deck_count, baseline_deck_count,
                     hub_deck_pct, baseline_deck_pct, synergy_score,
                     hub_sample_size, baseline_sample_size, fetched_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
                """,
                rows,
            )
    return len(rows)


def _hub_from_raw(raw: dict[str, Any]) -> Hub | None:
    hub_id = raw.get("id")
    name = str(raw.get("name") or "").strip()
    if hub_id is None or not name:
        return None
    slug = _slugify(name)
    return Hub(
        id=int(hub_id),
        slug=slug,
        tag=slug.replace("-", "_"),
        name=name,
        description=raw.get("description"),
        shows_in_decklist=bool(raw.get("showsInDeckList")),
    )


def _slugify(value: str) -> str:
    value = re.sub(r"\+(?=\d)", " plus ", value.lower())
    value = re.sub(r"-(?=\d)", " minus ", value)
    slug = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return slug or "hub"


def _entry_name(entry: dict[str, Any]) -> str | None:
    return entry.get("name") or entry.get("card_name")
