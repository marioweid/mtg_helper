"""Archidekt tag catalog and tag-card membership sync."""

import asyncio
import logging
import re
from collections import Counter
from dataclasses import dataclass
from html import unescape
from typing import Any

import asyncpg
import httpx

from mtg_helper.config import settings
from mtg_helper.services.deck_url_import_service import DeckFetchError, fetch_archidekt_deck
from mtg_helper.services.moxfield_hub_service import _score_hub_cards
from mtg_helper.services.theme_service import normalize_slug

_log = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 30.0
_TAG_DECK_SAMPLE = 10
_BASELINE_DECK_SAMPLE = 80
_FETCH_CONCURRENCY = 3
_TAG_LINK = re.compile(r'href=["\']/tags/(?P<slug>[a-z0-9-]+)["\'][^>]*>(?P<name>[^<]+)<')
_DECK_LINK = re.compile(r'href=["\']/decks/(?P<id>\d+)(?:/[^"\']*)?["\']')


@dataclass(frozen=True)
class ArchidektTag:
    """One Archidekt deck tag discovered from the public catalog."""

    slug: str
    tag: str
    name: str


async def sync_tags(pool: asyncpg.Pool) -> dict[str, Any]:
    """Refresh only the Archidekt tag catalog."""
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
        tags = await fetch_tags(client=client)
    async with pool.acquire() as conn:
        await _upsert_tags(conn, tags)
    return {"archidekt_tags_processed": len(tags)}


async def sync_tag_card_stats(pool: asyncpg.Pool, *, progress: Any | None = None) -> dict[str, Any]:
    """Refresh enabled stale Archidekt tags using a source-local baseline."""
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
        tags = await fetch_tags(client=client)
        async with pool.acquire() as conn:
            await _upsert_tags(conn, tags)
            stale = await _load_stale_tags(conn)
        if not stale:
            return _sync_result(0, len(tags), 0, 0)
        baseline_ids = await _sample_deck_ids(client, "/search/decks", _BASELINE_DECK_SAMPLE)
        baseline_tally = await _tally_decks(client, baseline_ids)
        matched = 0
        for index, tag in enumerate(stale):
            if progress is not None:
                progress(f"syncing Archidekt tag {tag.name}", index, len(stale))
            try:
                deck_ids = await _sample_deck_ids(client, f"/tags/{tag.slug}", _TAG_DECK_SAMPLE)
                tally = await _tally_decks(client, deck_ids)
                stats = _score_hub_cards(tally, baseline_tally, len(deck_ids), len(baseline_ids))
                matched += await _store_stats(pool, tag, stats, len(deck_ids), len(baseline_ids))
            except (httpx.HTTPError, DeckFetchError, ValueError) as exc:
                await _record_error(pool, tag.slug, str(exc))
                _log.warning("Archidekt tag %s failed: %s", tag.slug, exc)
            await asyncio.sleep(max(0.0, settings.archidekt_tag_delay_seconds))
    if progress is not None:
        progress("syncing Archidekt tags", len(stale), len(stale))
    return _sync_result(len(stale), len(tags) - len(stale), matched, len(baseline_ids))


async def sync_one_tag_card_stats(
    pool: asyncpg.Pool,
    *,
    tag_ref: str,
    tag_sample_size: int = _TAG_DECK_SAMPLE,
    baseline_sample_size: int = _BASELINE_DECK_SAMPLE,
) -> dict[str, Any]:
    """Refresh one Archidekt tag for manual admin verification."""
    tag_sample_size = min(100, max(1, tag_sample_size))
    baseline_sample_size = min(200, max(1, baseline_sample_size))
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
        tags = await fetch_tags(client=client)
        tag = _find_tag(tags, tag_ref)
        if tag is None:
            raise ValueError(f"Archidekt tag not found: {tag_ref}")
        async with pool.acquire() as conn:
            await _upsert_tags(conn, tags)
        baseline_ids = await _sample_deck_ids(client, "/search/decks", baseline_sample_size)
        deck_ids = await _sample_deck_ids(client, f"/tags/{tag.slug}", tag_sample_size)
        baseline_tally, tag_tally = await asyncio.gather(
            _tally_decks(client, baseline_ids), _tally_decks(client, deck_ids)
        )
        stats = _score_hub_cards(tag_tally, baseline_tally, len(deck_ids), len(baseline_ids))
        matched = await _store_stats(pool, tag, stats, len(deck_ids), len(baseline_ids))
    return {
        "archidekt_tags_processed": 1,
        "tag": tag.tag,
        "tag_name": tag.name,
        "archidekt_tag_cards_matched": matched,
        "tag_decks_sampled": len(deck_ids),
        "baseline_decks_sampled": len(baseline_ids),
    }


def _find_tag(tags: list[ArchidektTag], tag_ref: str) -> ArchidektTag | None:
    needle = tag_ref.strip().lower()
    for tag in tags:
        if needle in {tag.slug.lower(), tag.tag.lower(), tag.name.lower()}:
            return tag
    return None


def _sync_result(processed: int, skipped: int, matched: int, baseline: int) -> dict[str, Any]:
    return {
        "archidekt_tags_processed": processed,
        "archidekt_tags_skipped": skipped,
        "archidekt_tag_cards_matched": matched,
        "archidekt_baseline_decks_sampled": baseline,
    }


async def fetch_tags(*, client: httpx.AsyncClient) -> list[ArchidektTag]:
    """Parse the public Archidekt tag catalog without a Next.js build id."""
    response = await client.get("https://archidekt.com/tags")
    response.raise_for_status()
    tags: dict[str, ArchidektTag] = {}
    for match in _TAG_LINK.finditer(response.text):
        slug = match.group("slug")
        name = unescape(match.group("name")).strip()
        if name and slug not in tags:
            tags[slug] = ArchidektTag(slug=slug, tag=normalize_slug(slug), name=name)
    if not tags:
        raise ValueError("Archidekt returned an empty tag catalog")
    return sorted(tags.values(), key=lambda item: item.name.lower())


async def _sample_deck_ids(client: httpx.AsyncClient, path: str, sample_size: int) -> list[str]:
    response = await client.get(f"https://archidekt.com{path}")
    response.raise_for_status()
    ids: list[str] = []
    for match in _DECK_LINK.finditer(response.text):
        deck_id = match.group("id")
        if deck_id not in ids:
            ids.append(deck_id)
        if len(ids) >= sample_size:
            break
    return ids


async def _tally_decks(client: httpx.AsyncClient, deck_ids: list[str]) -> Counter[str]:
    semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)

    async def fetch_names(deck_id: str) -> set[str]:
        async with semaphore:
            try:
                deck = await fetch_archidekt_deck(deck_id, client=client)
            except DeckFetchError as exc:
                _log.warning("Skipping Archidekt deck %s: %s", deck_id, exc)
                return set()
            return {entry.name for entry in deck.entries}

    tally: Counter[str] = Counter()
    for names in await asyncio.gather(*(fetch_names(deck_id) for deck_id in deck_ids)):
        tally.update(names)
    return tally


async def _upsert_tags(conn: asyncpg.Connection, tags: list[ArchidektTag]) -> None:
    rows = [(tag.slug, tag.tag, tag.name) for tag in tags]
    slugs = [tag.slug for tag in tags]
    async with conn.transaction():
        await conn.executemany(
            """
            INSERT INTO archidekt_tags
                (slug, tag, name, active, first_seen_at, last_seen_at, synced_at)
            VALUES ($1, $2, $3, true, now(), now(), now())
            ON CONFLICT (slug) DO UPDATE SET tag = EXCLUDED.tag, name = EXCLUDED.name,
                active = true, last_seen_at = now(), synced_at = now()
            """,
            rows,
        )
        await conn.execute(
            "UPDATE archidekt_tags SET active = false WHERE slug != ALL($1::text[])", slugs
        )


async def _load_stale_tags(conn: asyncpg.Connection) -> list[ArchidektTag]:
    rows = await conn.fetch(
        """
        SELECT slug, tag, name FROM archidekt_tags
        WHERE active AND enabled AND (
            last_card_sync_at IS NULL
            OR last_card_sync_at <= now() - ($1::float * interval '1 hour')
        ) ORDER BY name
        """,
        max(0.0, settings.archidekt_tag_stale_after_hours),
    )
    return [ArchidektTag(**dict(row)) for row in rows]


async def _store_stats(
    pool: asyncpg.Pool,
    tag: ArchidektTag,
    stats: dict[str, tuple[int, int, float, float, float]],
    tag_sample: int,
    baseline_sample: int,
) -> int:
    async with pool.acquire() as conn:
        tag_id = await conn.fetchval("SELECT id FROM archidekt_tags WHERE slug = $1", tag.slug)
        cards = await conn.fetch(
            "SELECT id, lower(name) AS name FROM cards WHERE lower(name) = ANY($1::text[])",
            [name.lower() for name in stats],
        )
        card_ids = {row["name"]: row["id"] for row in cards}
        rows = [
            (tag_id, card_ids[name.lower()], *values, tag_sample, baseline_sample)
            for name, values in stats.items()
            if name.lower() in card_ids
        ]
        async with conn.transaction():
            await conn.execute("DELETE FROM archidekt_tag_card_stats WHERE tag_id = $1", tag_id)
            await conn.executemany(
                """INSERT INTO archidekt_tag_card_stats
                   (tag_id, card_id, tag_deck_count, baseline_deck_count, tag_deck_pct,
                    baseline_deck_pct, synergy_score, tag_sample_size, baseline_sample_size)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                rows,
            )
            await conn.execute(
                """UPDATE archidekt_tags SET last_card_sync_at = now(), last_error = NULL,
                   last_error_at = NULL WHERE id = $1""",
                tag_id,
            )
    return len(rows)


async def _record_error(pool: asyncpg.Pool, slug: str, message: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE archidekt_tags SET last_error = $2, last_error_at = now()
               WHERE slug = $1""",
            slug,
            message[:1000],
        )
