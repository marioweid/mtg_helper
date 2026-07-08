"""MTGJSON enrichment pipeline.

Downloads MTGJSON AllPrintings, extracts metadata that is useful for comparing
against our Scryfall-derived card rows, stores it in a sidecar table, and returns
a diff summary. MTGJSON keywords are used as optional exact mechanic filters;
EDHREC-style tags remain the primary Commander deckbuilding vocabulary.
"""

import io
import json
import logging
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

import asyncpg
import httpx

from mtg_helper.config import settings

if TYPE_CHECKING:
    from mtg_helper.services.admin_jobs import ProgressCb

_log = logging.getLogger(__name__)

_BATCH_SIZE = 500
_DIFF_SAMPLE_LIMIT = 20
_HTTP_HEADERS = {"User-Agent": "mtg-helper-local/1.0"}
_KEYWORD_CATEGORIES = {
    "abilityWords": "ability_word",
    "keywordAbilities": "keyword_ability",
    "keywordActions": "keyword_action",
}


@dataclass(frozen=True)
class MTGJSONCardMetadata:
    """Normalized MTGJSON card metadata keyed by Scryfall printing id."""

    scryfall_id: str
    mtgjson_uuid: str
    name: str
    keywords: list[str]
    types: list[str]
    supertypes: list[str]
    subtypes: list[str]
    edhrec_saltiness: float | None
    is_funny: bool
    is_online_only: bool
    is_rebalanced: bool
    is_game_changer: bool
    leadership_skills: dict[str, Any]
    related_cards: dict[str, Any]
    raw_identifiers: dict[str, Any]


@dataclass(frozen=True)
class MTGJSONKeyword:
    """Official keyword catalog item from MTGJSON ``Keywords.json``."""

    keyword: str
    tag: str
    label: str
    category: str
    mtgjson_version: str | None
    mtgjson_date: date | None


def _dedupe(values: list[Any] | None) -> list[str]:
    """Return a stable, string-only, deduplicated list."""
    if not values:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not isinstance(value, str) or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def keyword_to_tag(keyword: str) -> str:
    """Convert a printed MTGJSON keyword into our canonical snake-case tag."""
    tag = re.sub(r"[^a-z0-9]+", "_", keyword.strip().lower()).strip("_")
    if not tag:
        return "keyword"
    if tag[0].isdigit():
        return f"kw_{tag}"
    return tag


def _scryfall_id(card: dict[str, Any]) -> str | None:
    identifiers = card.get("identifiers") or {}
    value = identifiers.get("scryfallId")
    return value if isinstance(value, str) and value else None


def _map_card(card: dict[str, Any]) -> MTGJSONCardMetadata | None:
    """Map an MTGJSON card object to sidecar metadata.

    Returns None when MTGJSON has no Scryfall printing id; those rows cannot be
    safely joined to our existing ``cards.scryfall_id`` primary source.
    """
    sid = _scryfall_id(card)
    uuid = card.get("uuid")
    name = card.get("name")
    if not sid or not isinstance(uuid, str) or not isinstance(name, str):
        return None
    return MTGJSONCardMetadata(
        scryfall_id=sid,
        mtgjson_uuid=uuid,
        name=name,
        keywords=_dedupe(card.get("keywords")),
        types=_dedupe(card.get("types")),
        supertypes=_dedupe(card.get("supertypes")),
        subtypes=_dedupe(card.get("subtypes")),
        edhrec_saltiness=card.get("edhrecSaltiness"),
        is_funny=bool(card.get("isFunny", False)),
        is_online_only=bool(card.get("isOnlineOnly", False)),
        is_rebalanced=bool(card.get("isRebalanced", False)),
        is_game_changer=bool(card.get("isGameChanger", False)),
        leadership_skills=card.get("leadershipSkills") or {},
        related_cards=card.get("relatedCards") or {},
        raw_identifiers=card.get("identifiers") or {},
    )


def _decode_payload(content: bytes) -> dict[str, Any]:
    """Decode MTGJSON JSON bytes, accepting either plain JSON or zip archives."""
    if zipfile.is_zipfile(io.BytesIO(content)):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            json_names = [name for name in archive.namelist() if name.endswith(".json")]
            if not json_names:
                raise ValueError("MTGJSON archive did not contain a JSON file")
            with archive.open(json_names[0]) as handle:
                return json.loads(handle.read())
    return json.loads(content)


def _extract_cards(payload: dict[str, Any]) -> list[MTGJSONCardMetadata]:
    """Extract sidecar metadata from an AllPrintings payload."""
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("MTGJSON payload missing object data")

    cards: list[MTGJSONCardMetadata] = []
    for set_payload in data.values():
        if not isinstance(set_payload, dict):
            continue
        for raw_card in set_payload.get("cards") or []:
            if not isinstance(raw_card, dict):
                continue
            mapped = _map_card(raw_card)
            if mapped is not None:
                cards.append(mapped)
    return cards


async def _fetch_cards(client: httpx.AsyncClient) -> list[MTGJSONCardMetadata]:
    response = await client.get(settings.mtgjson_all_printings_url, headers=_HTTP_HEADERS)
    response.raise_for_status()
    return _extract_cards(_decode_payload(response.content))


async def _fetch_keyword_catalog(client: httpx.AsyncClient) -> list[MTGJSONKeyword]:
    response = await client.get(settings.mtgjson_keywords_url, headers=_HTTP_HEADERS)
    response.raise_for_status()
    return _extract_keyword_catalog(response.json())


def _extract_keyword_catalog(payload: dict[str, Any]) -> list[MTGJSONKeyword]:
    """Extract the official MTGJSON keyword catalog into canonical tags."""
    meta = payload.get("meta") or {}
    raw_date = meta.get("date")
    parsed_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else None
    version = meta.get("version") if isinstance(meta.get("version"), str) else None
    data = payload.get("data") or {}
    keywords: list[MTGJSONKeyword] = []
    for source_key, category in _KEYWORD_CATEGORIES.items():
        for keyword in data.get(source_key) or []:
            if isinstance(keyword, str) and keyword.strip():
                label = keyword.strip()
                keywords.append(
                    MTGJSONKeyword(
                        keyword=label,
                        tag=keyword_to_tag(label),
                        label=label,
                        category=category,
                        mtgjson_version=version,
                        mtgjson_date=parsed_date,
                    )
                )
    return keywords


async def _upsert_batch(conn: asyncpg.Connection, batch: list[MTGJSONCardMetadata]) -> None:
    """Upsert one batch into the MTGJSON sidecar table."""
    await conn.executemany(
        """
        INSERT INTO mtgjson_card_metadata (
            scryfall_id, mtgjson_uuid, name, keywords, types, supertypes, subtypes,
            edhrec_saltiness, is_funny, is_online_only, is_rebalanced,
            is_game_changer, leadership_skills, related_cards, raw_identifiers,
            updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13::jsonb, $14::jsonb, $15::jsonb, now()
        )
        ON CONFLICT (scryfall_id) DO UPDATE SET
            mtgjson_uuid      = EXCLUDED.mtgjson_uuid,
            name              = EXCLUDED.name,
            keywords          = EXCLUDED.keywords,
            types             = EXCLUDED.types,
            supertypes        = EXCLUDED.supertypes,
            subtypes          = EXCLUDED.subtypes,
            edhrec_saltiness  = EXCLUDED.edhrec_saltiness,
            is_funny          = EXCLUDED.is_funny,
            is_online_only    = EXCLUDED.is_online_only,
            is_rebalanced     = EXCLUDED.is_rebalanced,
            is_game_changer   = EXCLUDED.is_game_changer,
            leadership_skills = EXCLUDED.leadership_skills,
            related_cards     = EXCLUDED.related_cards,
            raw_identifiers   = EXCLUDED.raw_identifiers,
            updated_at        = now()
        """,
        [
            (
                c.scryfall_id,
                c.mtgjson_uuid,
                c.name,
                c.keywords,
                c.types,
                c.supertypes,
                c.subtypes,
                c.edhrec_saltiness,
                c.is_funny,
                c.is_online_only,
                c.is_rebalanced,
                c.is_game_changer,
                json.dumps(c.leadership_skills),
                json.dumps(c.related_cards),
                json.dumps(c.raw_identifiers),
            )
            for c in batch
        ],
    )


async def _upsert_keyword_catalog(conn: asyncpg.Connection, keywords: list[MTGJSONKeyword]) -> None:
    """Replace the local official keyword catalog with the latest MTGJSON set."""
    async with conn.transaction():
        await conn.executemany(
            """
            INSERT INTO mtgjson_keywords (
                keyword, tag, label, category, mtgjson_version, mtgjson_date, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, now())
            ON CONFLICT (keyword) DO UPDATE SET
                tag             = EXCLUDED.tag,
                label           = EXCLUDED.label,
                category        = EXCLUDED.category,
                mtgjson_version = EXCLUDED.mtgjson_version,
                mtgjson_date    = EXCLUDED.mtgjson_date,
                updated_at      = now()
            """,
            [
                (
                    item.keyword,
                    item.tag,
                    item.label,
                    item.category,
                    item.mtgjson_version,
                    item.mtgjson_date,
                )
                for item in keywords
            ],
        )
        await conn.execute(
            "DELETE FROM mtgjson_keywords WHERE keyword <> ALL($1::text[])",
            [item.keyword for item in keywords],
        )


def _same_values(left: list[str], right: list[str]) -> bool:
    """Compare metadata lists as case-sensitive sets."""
    return set(left) == set(right)


def _diff_sample(row: asyncpg.Record, field: str) -> dict[str, object]:
    return {
        "name": row["name"],
        "scryfall_id": str(row["scryfall_id"]),
        "field": field,
        "cards": list(row[f"card_{field}"]),
        "mtgjson": list(row[f"mtgjson_{field}"]),
    }


def _count_diffs(rows: list[asyncpg.Record], field: str) -> tuple[int, list[dict[str, object]]]:
    count = 0
    samples: list[dict[str, object]] = []
    for row in rows:
        if _same_values(list(row[f"card_{field}"]), list(row[f"mtgjson_{field}"])):
            continue
        count += 1
        if len(samples) < _DIFF_SAMPLE_LIMIT:
            samples.append(_diff_sample(row, field))
    return count, samples


async def _diff_existing(conn: asyncpg.Connection) -> dict[str, object]:
    """Compare current ``cards`` metadata with the MTGJSON sidecar."""
    rows = await conn.fetch(
        """
        SELECT
            c.name,
            c.scryfall_id,
            c.keywords AS card_keywords,
            m.keywords AS mtgjson_keywords,
            c.card_types AS card_types,
            m.types AS mtgjson_types,
            c.subtypes AS card_subtypes,
            m.subtypes AS mtgjson_subtypes
        FROM cards c
        JOIN mtgjson_card_metadata m ON m.scryfall_id = c.scryfall_id
        ORDER BY c.name
        """
    )
    keyword_count, keyword_samples = _count_diffs(rows, "keywords")
    type_count, type_samples = _count_diffs(rows, "types")
    subtype_count, subtype_samples = _count_diffs(rows, "subtypes")
    return {
        "matched_cards": len(rows),
        "keyword_differences": keyword_count,
        "type_differences": type_count,
        "subtype_differences": subtype_count,
        "samples": keyword_samples + type_samples + subtype_samples,
    }


async def run_sync(
    pool: asyncpg.Pool,
    progress: "ProgressCb | None" = None,
) -> dict[str, object]:
    """Download MTGJSON metadata, upsert sidecar rows, and report diffs."""
    from mtg_helper.services.admin_jobs import noop_progress

    cb = progress or noop_progress
    started = time.monotonic()

    cb("downloading", 0, 0)
    async with httpx.AsyncClient(timeout=180) as client:
        cards = await _fetch_cards(client)
        keywords = await _fetch_keyword_catalog(client)

    total = len(cards)
    cb("upserting", 0, total)
    async with pool.acquire() as conn:
        await _upsert_keyword_catalog(conn, keywords)
        for i in range(0, total, _BATCH_SIZE):
            await _upsert_batch(conn, cards[i : i + _BATCH_SIZE])
            cb("upserting", min(i + _BATCH_SIZE, total), total)
        cb("comparing", 0, 0)
        diff = await _diff_existing(conn)

    _log.info("MTGJSON sync upserted %d rows; diff=%s", total, diff)
    return {
        "mtgjson_cards_processed": total,
        "duration_seconds": round(time.monotonic() - started, 2),
        "mtgjson_keywords_processed": len(keywords),
        **diff,
    }


async def sync_keywords(pool: asyncpg.Pool) -> dict[str, object]:
    """Refresh only the small MTGJSON official keyword catalog."""
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=30) as client:
        keywords = await _fetch_keyword_catalog(client)
    async with pool.acquire() as conn:
        await _upsert_keyword_catalog(conn, keywords)
    return {
        "mtgjson_keywords_processed": len(keywords),
        "duration_seconds": round(time.monotonic() - started, 2),
    }
