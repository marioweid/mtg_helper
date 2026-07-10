"""Local EDHREC tag catalog sync and helpers."""

import html
import re
from dataclasses import dataclass
from typing import Any

import asyncpg
import httpx

from mtg_helper.services.edhrec_theme_index_service import TAG_TO_THEME_SLUGS

_REQUEST_TIMEOUT = 30.0
_TAG_LINK_RE = re.compile(
    r'href="/tags/(?P<slug>[^"#?]+)"[^>]*>\s*(?P<label>[^<]+?)\s*</a>'
    r"(?:\s*<[^>]+>)*\s*(?P<count>[\d,.]+K?)?\s*decks?",
    re.IGNORECASE,
)

_FALLBACK_LABELS = {
    "tokens": "Tokens",
    "plus-1-plus-1-counters": "+1/+1 Counters",
    "artifacts": "Artifacts",
    "combo": "Combo",
    "aggro": "Aggro",
    "lifegain": "Lifegain",
    "spellslinger": "Spellslinger",
    "reanimator": "Reanimator",
    "aristocrats": "Aristocrats",
    "lands": "Lands Matter",
    "control": "Control",
    "equipment": "Equipment",
    "burn": "Burn",
    "ramp": "Ramp",
    "enchantress": "Enchantress",
    "treasure": "Treasure",
    "voltron": "Voltron",
    "mill": "Mill",
    "midrange": "Midrange",
    "sacrifice": "Sacrifice",
    "wheels": "Wheels",
    "auras": "Auras",
    "blink": "Blink",
    "graveyard": "Graveyard",
    "card-draw": "Card Draw",
    "landfall": "Landfall",
    "infect": "Infect",
    "stax": "Stax",
    "storm": "Storm",
    "self-mill": "Self-Mill",
    "group-hug": "Group Hug",
    "extra-turns": "Extra Turns",
    "etb": "ETB",
    "dredge": "Dredge",
    "proliferate": "Proliferate",
    "clues": "Clues",
    "food": "Food",
    "pingers": "Pingers",
    "activated-abilities": "Activated Abilities",
    "triggered-abilities": "Triggered Abilities",
    "convoke": "Convoke",
}

_TAG_ALIASES = {
    "artifact": "artifacts",
    "draw": "card_draw",
    "card_advantage": "card_draw",
    "cantrip": "card_draw",
    "lands": "lands_matter",
    "treasures": "treasure",
    "plus_one_counters": "plus_one_plus_one_counters",
    "plus_1_plus_1_counters": "plus_one_plus_one_counters",
    "plus_one_plus_1_counters": "plus_one_plus_one_counters",
    "infect_toxic": "infect",
    "extra_turn": "extra_turns",
    "card-draw": "card_draw",
}


@dataclass(frozen=True)
class EDHRECTag:
    """One EDHREC tag catalog entry."""

    slug: str
    tag: str
    label: str
    category: str = "theme"
    deck_count: int | None = None


async def sync_edhrec_tags(pool: asyncpg.Pool) -> dict[str, Any]:
    """Fetch EDHREC's tag list into the local catalog, falling back to curated tags."""
    tags = await _fetch_tags()
    if not tags:
        tags = fallback_tags()
    tags = _dedupe_by_tag(tags)
    async with pool.acquire() as conn:
        await _upsert_tags(conn, tags)
    return {"edhrec_tags_processed": len(tags)}


async def ensure_edhrec_tags(pool: asyncpg.Pool) -> None:
    """Seed the local EDHREC catalog when it is empty."""
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM edhrec_tags")
    if count == 0:
        await sync_edhrec_tags(pool)


async def load_edhrec_tags(pool: asyncpg.Pool) -> set[str]:
    """Load allowed EDHREC tag ids from the local catalog."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT tag FROM edhrec_tags")
    if not rows:
        return {tag.tag for tag in fallback_tags()}
    return {row["tag"] for row in rows}


async def load_edhrec_prompt_catalog(pool: asyncpg.Pool) -> str:
    """Return compact EDHREC theme lines for intent-extraction prompts."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tag, label, deck_count
            FROM edhrec_tags
            ORDER BY COALESCE(deck_count, 0) DESC, label ASC
            LIMIT 160
            """
        )
    if not rows:
        return "\n".join(f"- {tag.tag}: {tag.label}" for tag in fallback_tags())
    return "\n".join(
        f"- {row['tag']}: {row['label']}{_deck_count_suffix(row['deck_count'])}" for row in rows
    )


async def list_edhrec_tag_groups(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return frontend-ready EDHREC tag groups."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tag, label, category, deck_count
            FROM edhrec_tags
            ORDER BY COALESCE(deck_count, 0) DESC, label ASC
            """
        )
    if not rows:
        fallback = fallback_tags()
        return [
            {
                "category": "edhrec",
                "display_name": "EDHREC themes",
                "keywords": [
                    {"tag": item.tag, "label": item.label, "deck_count": item.deck_count}
                    for item in fallback
                ],
            }
        ]
    return [
        {
            "category": "edhrec",
            "display_name": "EDHREC themes",
            "keywords": [
                {"tag": row["tag"], "label": row["label"], "deck_count": row["deck_count"]}
                for row in rows
            ],
        }
    ]


def fallback_tags() -> list[EDHRECTag]:
    """Curated EDHREC tag fallback covering current deckbuilding categories."""
    slugs = set(_FALLBACK_LABELS) | {slug for slugs in TAG_TO_THEME_SLUGS.values() for slug in slugs}
    return _dedupe_by_tag([
        EDHRECTag(slug=slug, tag=_slug_to_tag(slug), label=_FALLBACK_LABELS.get(slug, _label(slug)))
        for slug in sorted(slugs)
    ])


async def _fetch_tags() -> list[EDHRECTag]:
    tags_url = "https://edhrec.com/tags"
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(tags_url)
            response.raise_for_status()
    except httpx.HTTPError:
        return []
    parsed = _parse_tags_html(response.text)
    return parsed or fallback_tags()


def _parse_tags_html(markup: str) -> list[EDHRECTag]:
    seen: set[str] = set()
    tags: list[EDHRECTag] = []
    for match in _TAG_LINK_RE.finditer(markup):
        slug = match.group("slug").strip("/")
        if slug in seen:
            continue
        seen.add(slug)
        label = html.unescape(match.group("label")).strip()
        tags.append(
            EDHRECTag(
                slug=slug,
                tag=_slug_to_tag(slug),
                label=label,
                deck_count=_parse_count(match.group("count")),
            )
        )
    return tags


async def _upsert_tags(conn: asyncpg.Connection, tags: list[EDHRECTag]) -> None:
    rows = [(tag.slug, tag.tag, tag.label, tag.category, tag.deck_count) for tag in tags]
    async with conn.transaction():
        await conn.execute(
            """
            DELETE FROM edhrec_tags
            WHERE slug = ANY($1::text[])
               OR tag = ANY($2::text[])
            """,
            [tag.slug for tag in tags],
            [tag.tag for tag in tags],
        )
        await conn.executemany(
            """
            INSERT INTO edhrec_tags (slug, tag, label, category, deck_count, fetched_at)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (tag) DO UPDATE SET
                slug       = EXCLUDED.slug,
                tag        = EXCLUDED.tag,
                label      = EXCLUDED.label,
                category   = EXCLUDED.category,
                deck_count = EXCLUDED.deck_count,
                fetched_at = now()
            """,
            rows,
        )


def _dedupe_by_tag(tags: list[EDHRECTag]) -> list[EDHRECTag]:
    """Keep one catalog item per canonical tag, preferring richer EDHREC data."""
    by_tag: dict[str, EDHRECTag] = {}
    for item in tags:
        current = by_tag.get(item.tag)
        if current is None or _tag_quality(item) > _tag_quality(current):
            by_tag[item.tag] = item
    return sorted(by_tag.values(), key=lambda item: item.label.lower())


def _tag_quality(item: EDHRECTag) -> tuple[int, int, int]:
    """Rank catalog duplicates by known count, curated label, then shorter slug."""
    has_count = 1 if item.deck_count is not None else 0
    known_label = 1 if item.slug in _FALLBACK_LABELS else 0
    return (has_count, known_label, -len(item.slug))


def _slug_to_tag(slug: str) -> str:
    tag = slug.replace("-1-", "_one_").replace("+", "plus")
    tag = re.sub(r"[^a-z0-9]+", "_", tag.lower()).strip("_")
    return _TAG_ALIASES.get(tag, tag)


def _label(slug: str) -> str:
    return slug.replace("-", " ").title()


def _parse_count(value: str | None) -> int | None:
    if not value:
        return None
    text = value.replace(",", "").strip().upper()
    multiplier = 1000 if text.endswith("K") else 1
    if text.endswith("K"):
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


def _deck_count_suffix(count: int | None) -> str:
    if count is None:
        return ""
    return f" ({count} EDHREC decks)"
