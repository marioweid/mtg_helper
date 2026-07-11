"""Shared theme groups over Moxfield hubs and Archidekt tags."""

import re
from typing import Any
from uuid import UUID

import asyncpg

_SEED_GROUPS = (
    (
        "plus_one_plus_one",
        "+1/+1 Counters",
        ("plus_one_plus_one", "plus_1_plus_1", "plus_1_plus_1_counters", "plus_counters"),
    ),
    ("artifacts", "Artifacts", ("artifacts",)),
    ("aristocrats", "Aristocrats", ("aristocrats",)),
    ("blink", "Blink", ("blink",)),
    ("enchantments", "Enchantments", ("enchantments",)),
    ("equipment", "Equipment", ("equipment",)),
    ("lifegain", "Lifegain", ("lifegain",)),
    ("reanimator", "Reanimator", ("reanimator",)),
    ("spellslinger", "Spellslinger", ("spellslinger",)),
    ("tokens", "Tokens", ("tokens",)),
    ("voltron", "Voltron", ("voltron",)),
)


def normalize_slug(value: str) -> str:
    """Return a stable snake-case identifier."""
    value = re.sub(r"\+(?=\d)", " plus ", value.lower())
    value = re.sub(r"-(?=\d)", " minus ", value)
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


async def seed_groups(pool: asyncpg.Pool) -> None:
    """Create conservative groups and attach exact normalized matches."""
    async with pool.acquire() as conn, conn.transaction():
        created_any = False
        for index, (slug, label, aliases) in enumerate(_SEED_GROUPS):
            created = await conn.fetchval(
                """
                INSERT INTO theme_groups (slug, label, sort_order)
                VALUES ($1, $2, $3)
                ON CONFLICT (slug) DO NOTHING
                RETURNING id
                """,
                slug,
                label,
                index,
            )
            if created is not None:
                created_any = True
                await _attach_seed_members(conn, slug, aliases)
        if created_any:
            await _migrate_legacy_deck_tags(conn)


async def _attach_seed_members(
    conn: asyncpg.Connection, group_slug: str, aliases: tuple[str, ...]
) -> None:
    await conn.execute(
        """
        INSERT INTO theme_group_members (group_id, source, moxfield_hub_id)
        SELECT g.id, 'moxfield', h.id
        FROM theme_groups g CROSS JOIN moxfield_hubs h
        WHERE g.slug = $1 AND h.tag = ANY($2::text[])
        ON CONFLICT DO NOTHING
        """,
        group_slug,
        list(aliases),
    )
    await conn.execute(
        """
        INSERT INTO theme_group_members (group_id, source, archidekt_tag_id)
        SELECT g.id, 'archidekt', t.id
        FROM theme_groups g CROSS JOIN archidekt_tags t
        WHERE g.slug = $1 AND t.tag = ANY($2::text[])
        ON CONFLICT DO NOTHING
        """,
        group_slug,
        list(aliases),
    )


async def _migrate_legacy_deck_tags(conn: asyncpg.Connection) -> None:
    """Replace unambiguous legacy Moxfield selections with stable group slugs."""
    await conn.execute(
        """
        UPDATE decks d SET archetype_tags = migrated.tags
        FROM (
            SELECT d2.id, array_agg(DISTINCT COALESCE(g.slug, old_tag)) AS tags
            FROM decks d2 CROSS JOIN LATERAL unnest(d2.archetype_tags) old_tag
            LEFT JOIN moxfield_hubs h ON h.tag = old_tag
            LEFT JOIN theme_group_members m ON m.moxfield_hub_id = h.id
            LEFT JOIN theme_groups g ON g.id = m.group_id AND g.deleted_at IS NULL
            GROUP BY d2.id
        ) migrated
        WHERE d.id = migrated.id AND d.archetype_tags IS DISTINCT FROM migrated.tags
        """
    )


async def list_theme_catalog(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return shared groups plus enabled ungrouped source tags."""
    async with pool.acquire() as conn:
        groups = await conn.fetch(
            """
            SELECT g.id, g.slug, g.label, g.description, g.sort_order,
                   count(m.id) AS member_count
            FROM theme_groups g
            LEFT JOIN theme_group_members m ON m.group_id = g.id
            WHERE g.enabled AND g.deleted_at IS NULL AND EXISTS (
                SELECT 1 FROM theme_group_members visible
                LEFT JOIN moxfield_hubs mh ON mh.id = visible.moxfield_hub_id
                LEFT JOIN archidekt_tags at ON at.id = visible.archidekt_tag_id
                WHERE visible.group_id = g.id
                  AND ((mh.active AND mh.enabled) OR (at.active AND at.enabled))
            )
            GROUP BY g.id
            ORDER BY g.sort_order, g.label
            """
        )
        ungrouped = await _load_ungrouped(conn)
    catalog = [
        {
            "category": f"theme_group:{row['id']}",
            "display_name": row["label"],
            "keywords": [{"tag": row["slug"], "label": row["label"], "deck_count": None}],
        }
        for row in groups
    ]
    if ungrouped:
        catalog.append(
            {"category": "ungrouped", "display_name": "Ungrouped", "keywords": ungrouped}
        )
    return catalog


async def _load_ungrouped(conn: asyncpg.Connection) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT 'moxfield:' || h.tag AS tag, h.name AS label
        FROM moxfield_hubs h
        LEFT JOIN theme_group_members m ON m.moxfield_hub_id = h.id
        WHERE h.active AND h.enabled AND m.id IS NULL
        UNION ALL
        SELECT 'archidekt:' || t.tag, t.name
        FROM archidekt_tags t
        LEFT JOIN theme_group_members m ON m.archidekt_tag_id = t.id
        WHERE t.active AND t.enabled AND m.id IS NULL
        ORDER BY label
        """
    )
    return [{"tag": row["tag"], "label": row["label"], "deck_count": None} for row in rows]


async def load_theme_tags(pool: asyncpg.Pool) -> set[str]:
    """Return all currently selectable shared and source-qualified tags."""
    catalog = await list_theme_catalog(pool)
    return {item["tag"] for group in catalog for item in group["keywords"]}


async def load_theme_prompt_catalog(pool: asyncpg.Pool) -> str:
    """Return compact selectable theme lines for agent prompts."""
    catalog = await list_theme_catalog(pool)
    return "\n".join(
        f"- {item['tag']}: {item['label']}" for group in catalog for item in group["keywords"]
    )


async def score_themes(
    pool: asyncpg.Pool, tags: list[str], commander_color_identity: list[str]
) -> dict[UUID, float]:
    """Resolve group, qualified, and legacy Moxfield tags using maximum score."""
    if not tags:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _SCORE_SQL,
            tags,
            commander_color_identity,
        )
    return {row["card_id"]: float(row["score"] or 0.0) for row in rows}


_SCORE_SQL = """
WITH selected_moxfield AS (
    SELECT DISTINCT h.id
    FROM moxfield_hubs h
    LEFT JOIN theme_group_members m ON m.moxfield_hub_id = h.id
    LEFT JOIN theme_groups g ON g.id = m.group_id
    WHERE h.active AND h.enabled AND (
        h.tag = ANY($1::text[]) OR 'moxfield:' || h.tag = ANY($1::text[])
        OR (g.slug = ANY($1::text[]) AND g.enabled AND g.deleted_at IS NULL)
    )
), selected_archidekt AS (
    SELECT DISTINCT t.id
    FROM archidekt_tags t
    LEFT JOIN theme_group_members m ON m.archidekt_tag_id = t.id
    LEFT JOIN theme_groups g ON g.id = m.group_id
    WHERE t.active AND t.enabled AND (
        'archidekt:' || t.tag = ANY($1::text[])
        OR (g.slug = ANY($1::text[]) AND g.enabled AND g.deleted_at IS NULL)
    )
), scores AS (
    SELECT s.card_id, s.synergy_score AS score
    FROM moxfield_hub_card_stats s JOIN selected_moxfield x ON x.id = s.hub_id
    UNION ALL
    SELECT s.card_id, s.synergy_score
    FROM archidekt_tag_card_stats s JOIN selected_archidekt x ON x.id = s.tag_id
)
SELECT scores.card_id, max(scores.score) AS score
FROM scores JOIN cards c ON c.id = scores.card_id
WHERE c.color_identity <@ $2::text[]
  AND c.legalities->>'commander' = 'legal'
  AND COALESCE(c.border_color, '') != 'gold'
  AND COALESCE(c.security_stamp, '') != 'acorn'
  AND c.type_line NOT LIKE '%Conspiracy%'
GROUP BY scores.card_id
"""


async def list_admin_state(pool: asyncpg.Pool) -> dict[str, Any]:
    """Return groups and all source tags for admin management."""
    async with pool.acquire() as conn:
        groups = await conn.fetch(
            """SELECT id, slug, label, description, sort_order, enabled, deleted_at
               FROM theme_groups ORDER BY sort_order, label"""
        )
        tags = await conn.fetch(_ADMIN_TAGS_SQL)
    return {"groups": [dict(row) for row in groups], "source_tags": [dict(row) for row in tags]}


_ADMIN_TAGS_SQL = """
SELECT 'moxfield' AS source, h.id::text AS source_id, h.tag, h.name, h.active, h.enabled,
       m.group_id, h.last_card_sync_at, count(s.card_id) AS card_count
FROM moxfield_hubs h
LEFT JOIN theme_group_members m ON m.moxfield_hub_id = h.id
LEFT JOIN moxfield_hub_card_stats s ON s.hub_id = h.id
GROUP BY h.id, m.group_id
UNION ALL
SELECT 'archidekt', t.id::text, t.tag, t.name, t.active, t.enabled,
       m.group_id, t.last_card_sync_at, count(s.card_id)
FROM archidekt_tags t
LEFT JOIN theme_group_members m ON m.archidekt_tag_id = t.id
LEFT JOIN archidekt_tag_card_stats s ON s.tag_id = t.id
GROUP BY t.id, m.group_id
ORDER BY name
"""


async def create_group(pool: asyncpg.Pool, data: dict[str, Any]) -> dict[str, Any]:
    """Create an administrator-managed theme group."""
    slug = normalize_slug(data.get("slug") or data["label"])
    label = data["label"].strip()
    if not slug or not label:
        raise ValueError("Theme group label and slug must contain letters or numbers")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO theme_groups (slug, label, description, sort_order)
               VALUES ($1, $2, $3, $4) RETURNING *""",
            slug,
            label,
            data.get("description"),
            data.get("sort_order", 0),
        )
    return dict(row)


async def update_group(pool: asyncpg.Pool, group_id: int, data: dict[str, Any]) -> None:
    """Update editable group fields while keeping its stable slug."""
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """UPDATE theme_groups SET label = COALESCE($2, label),
               description = COALESCE($3, description), sort_order = COALESCE($4, sort_order),
               enabled = COALESCE($5, enabled),
               deleted_at = CASE WHEN $6 THEN now() ELSE deleted_at END,
               updated_at = now() WHERE id = $1""",
            group_id,
            data.get("label"),
            data.get("description"),
            data.get("sort_order"),
            data.get("enabled"),
            data.get("delete", False),
        )
        if data.get("delete"):
            await conn.execute("DELETE FROM theme_group_members WHERE group_id = $1", group_id)


async def restore_group(pool: asyncpg.Pool, group_id: int) -> None:
    """Restore a soft-deleted theme group without reclaiming old members."""
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE theme_groups
               SET deleted_at = NULL, enabled = true, updated_at = now()
               WHERE id = $1""",
            group_id,
        )


async def assign_member(
    pool: asyncpg.Pool, group_id: int | None, source: str, source_id: int
) -> None:
    """Move a source tag to one group, or unassign it when group_id is null."""
    if source not in {"moxfield", "archidekt"}:
        raise ValueError("Unknown theme source")
    async with pool.acquire() as conn, conn.transaction():
        if source == "moxfield":
            await conn.execute(
                "DELETE FROM theme_group_members WHERE moxfield_hub_id = $1", source_id
            )
        else:
            await conn.execute(
                "DELETE FROM theme_group_members WHERE archidekt_tag_id = $1", source_id
            )
        if group_id is not None and source == "moxfield":
            await conn.execute(
                """INSERT INTO theme_group_members (group_id, source, moxfield_hub_id)
                   VALUES ($1, $2, $3)""",
                group_id,
                source,
                source_id,
            )
        elif group_id is not None:
            await conn.execute(
                """INSERT INTO theme_group_members (group_id, source, archidekt_tag_id)
                   VALUES ($1, $2, $3)""",
                group_id,
                source,
                source_id,
            )


async def set_source_enabled(
    pool: asyncpg.Pool, source: str, source_id: int, enabled: bool
) -> None:
    """Set the reversible administrator availability flag for a source tag."""
    if source not in {"moxfield", "archidekt"}:
        raise ValueError("Unknown theme source")
    async with pool.acquire() as conn:
        if source == "moxfield":
            await conn.execute(
                "UPDATE moxfield_hubs SET enabled = $2 WHERE id = $1", source_id, enabled
            )
        else:
            await conn.execute(
                "UPDATE archidekt_tags SET enabled = $2 WHERE id = $1", source_id, enabled
            )
