"""Validate concrete Scryfall Oracle-tag and printed-keyword selections."""

from uuid import UUID

import asyncpg

from mtg_helper.models.ai import CommanderSuggestIntent
from mtg_helper.services.scryfall_tag_repository import require_tag_ids


async def load_keyword_tags(pool: asyncpg.Pool) -> set[str]:
    """Load exact printed keywords from canonical Scryfall card facts."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT keyword FROM cards CROSS JOIN unnest(keywords) AS keyword "
            "WHERE is_canonical"
        )
    return {row["keyword"] for row in rows}


async def load_keyword_prompt_catalog(pool: asyncpg.Pool) -> str:
    """Return source keyword text without invented mechanic descriptions."""
    return "\n".join(f"- {keyword}" for keyword in sorted(await load_keyword_tags(pool)))


async def sanitize_commander_intent(
    pool: asyncpg.Pool, intent: CommanderSuggestIntent
) -> CommanderSuggestIntent:
    """Reject selections absent from the current Scryfall source generation."""
    source_ids = _source_ids(intent.archetype_tags)
    await require_tag_ids(pool, source_ids)
    keywords = await load_keyword_tags(pool)
    unknown = sorted(set(intent.mechanic_tags) - keywords)
    if unknown:
        raise ValueError(f"Unknown printed Scryfall keyword: {unknown[0]}")
    data = intent.model_dump()
    data["archetype_tags"] = [str(source_id) for source_id in source_ids]
    return CommanderSuggestIntent(**data)


def _source_ids(values: list[str]) -> list[UUID]:
    """Parse model-provided Oracle-tag identities with an actionable error."""
    try:
        return [UUID(value) for value in values]
    except ValueError as exc:
        raise ValueError("Oracle-tag selections must be Scryfall source UUIDs") from exc
