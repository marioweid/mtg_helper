"""LLM-drafted, human-approved theme group suggestions.

A background job reads active, ungrouped Moxfield hubs and Archidekt tags
(with their most characteristic cards as evidence), asks the shared cheap
model to either assign each to an existing theme group or propose a new
group, and stores the draft in ``theme_group_suggestions`` as ``pending``.
The admin UI lets a human approve or reject each draft; approval creates
the group (when new) and attaches the source tag through the normal
theme-service path, so everything downstream (search resolution, prompt
catalog) picks it up without code changes.
"""

import logging
from collections.abc import Callable
from typing import Any, Literal

import asyncpg
from pydantic import BaseModel, Field
from pydantic_ai import Agent, UsageLimits

from mtg_helper.services.agents._model import make_openai_model, openai_model_settings

_log = logging.getLogger(__name__)

ProgressCb = Callable[[str, int, int], None]

_BATCH_SIZE = 15
_MAX_EVIDENCE_CARDS = 5
_MAX_THEME_GROUPS = 25
_TIMEOUT_SECONDS = 120.0

# Assistant-style shared cheap model settings: low reasoning, medium verbosity
# keeps the classification cheap while still reading the group catalog.
_MODEL_SETTINGS = openai_model_settings(max_tokens=4_000, reasoning="low", verbosity="medium")


class NewGroupProposal(BaseModel):
    """A proposed brand-new theme group for a cluster of source tags."""

    slug: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    aliases: list[str] = Field(default_factory=list, max_length=12)


class HubSuggestion(BaseModel):
    """One source tag's draft classification."""

    tag: str
    action: Literal["assign", "new_group", "skip"]
    group_slug: str | None = Field(default=None, max_length=80)
    new_group: NewGroupProposal | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=500)


class SuggestionBatch(BaseModel):
    """Structured LLM output for one batch of source tags."""

    suggestions: list[HubSuggestion] = Field(default_factory=list, max_length=_BATCH_SIZE)


def _noop(phase: str, current: int, total: int) -> None:
    del phase, current, total


async def generate_suggestions(
    pool: asyncpg.Pool,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Draft theme-group suggestions for every active ungrouped source tag.

    Args:
        pool: Database pool.
        progress: Optional progress callback receiving ``(phase, current, total)``.

    Returns:
        A summary dict with the number of source tags considered and the
        number of pending suggestions stored.
    """
    cb = progress or _noop
    cb("loading ungrouped tags", 0, 1)
    catalog = await _load_group_catalog(pool)
    sources = await _load_ungrouped_sources(pool)
    if not sources:
        return {"sources_considered": 0, "suggestions_stored": 0, "skipped": 0}
    evidence = await _load_evidence(pool, sources)
    batches = [sources[i : i + _BATCH_SIZE] for i in range(0, len(sources), _BATCH_SIZE)]
    drafts: list[tuple[dict[str, Any], HubSuggestion]] = []
    for index, batch in enumerate(batches, start=1):
        cb("classifying", index, len(batches))
        for item in await _classify_batch(batch, evidence, catalog):
            if item.action == "skip":
                continue
            source = next((row for row in batch if row["tag"] == item.tag), None)
            if source is not None:
                drafts.append((source, item))
    cb("storing", 0, max(1, len(drafts)))
    await _store_suggestions(pool, drafts)
    return {
        "sources_considered": len(sources),
        "suggestions_stored": len(drafts),
        "skipped": len(sources) - len(drafts),
    }


async def _load_group_catalog(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return active shared groups for the LLM to assign into."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT slug, label, description, aliases
            FROM theme_groups
            WHERE enabled AND deleted_at IS NULL
            ORDER BY sort_order, label
            """
        )
    return [dict(row) for row in rows]


async def _load_ungrouped_sources(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return active source tags not yet assigned to any theme group."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 'moxfield' AS source, h.id AS source_id, h.tag, h.name, h.description
            FROM moxfield_hubs h
            LEFT JOIN theme_group_members m ON m.moxfield_hub_id = h.id
            WHERE h.active AND h.enabled AND m.id IS NULL
            UNION ALL
            SELECT 'archidekt', t.id, t.tag, t.name, t.description
            FROM archidekt_tags t
            LEFT JOIN theme_group_members m ON m.archidekt_tag_id = t.id
            WHERE t.active AND t.enabled AND m.id IS NULL
            ORDER BY name
            """
        )
    return [dict(row) for row in rows]


async def _load_evidence(pool: asyncpg.Pool, sources: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Return the top characteristic card names per source tag."""
    hub_ids = [row["source_id"] for row in sources if row["source"] == "moxfield"]
    tag_ids = [row["source_id"] for row in sources if row["source"] == "archidekt"]
    evidence: dict[str, list[str]] = {}
    async with pool.acquire() as conn:
        if hub_ids:
            rows = await conn.fetch(
                """
                SELECT s.hub_id AS source_id, c.name
                FROM moxfield_hub_card_stats s
                JOIN cards c ON c.id = s.card_id
                WHERE s.hub_id = ANY($1::bigint[])
                ORDER BY s.hub_id, s.synergy_score DESC
                """,
                hub_ids,
            )
            for row in rows:
                key = f"moxfield:{row['source_id']}"
                if len(evidence.setdefault(key, [])) < _MAX_EVIDENCE_CARDS:
                    evidence[key].append(row["name"])
        if tag_ids:
            rows = await conn.fetch(
                """
                SELECT s.tag_id AS source_id, c.name
                FROM archidekt_tag_card_stats s
                JOIN cards c ON c.id = s.card_id
                WHERE s.tag_id = ANY($1::bigint[])
                ORDER BY s.tag_id, s.synergy_score DESC
                """,
                tag_ids,
            )
            for row in rows:
                key = f"archidekt:{row['source_id']}"
                if len(evidence.setdefault(key, [])) < _MAX_EVIDENCE_CARDS:
                    evidence[key].append(row["name"])
    return evidence


def _catalog_prompt(catalog: list[dict[str, Any]], max_new_groups: int) -> str:
    lines = [
        f"- {row['slug']}: {row['label']}"
        + (f" - {row['description']}" if row["description"] else "")
        for row in catalog
    ]
    header = "EXISTING THEME GROUPS (assign a source tag to one of these when it fits):"
    return (
        header
        + "\n"
        + "\n".join(lines)
        + (
            f"\n\nYou may propose at most {max_new_groups} NEW group(s) when no existing "
            "group fits. Never invent groups that overlap an existing one."
        )
    )


def _source_prompt(source: dict[str, Any], evidence: dict[str, list[str]]) -> str:
    key = f"{source['source']}:{source['source_id']}"
    cards = evidence.get(key, [])
    return (
        f"- {source['tag']} ({source['name']})"
        + (f": {source['description']}" if source.get("description") else "")
        + (" | characteristic cards: " + ", ".join(cards) if cards else "")
    )


async def _classify_batch(
    batch: list[dict[str, Any]],
    evidence: dict[str, list[str]],
    catalog: list[dict[str, Any]],
) -> list[HubSuggestion]:
    """Ask the cheap model to classify one batch of source tags."""
    max_new_groups = max(0, _MAX_THEME_GROUPS - len(catalog))
    prompt = (
        "Classify each Commander theme source tag below. For each, choose exactly one:\n"
        "1. action=assign with the matching existing group_slug (preferred when a good fit "
        "exists), or\n"
        "2. action=new_group with a concise label, slug, one-sentence description, and a few "
        "search aliases, or\n"
        "3. action=skip when the tag is too niche, redundant, or unclear to group.\n"
        "Prefer a small number of high-quality groups; only propose new groups that several "
        "distinct tags or the evidence clearly support. Confidence 0-1, rationale one sentence.\n\n"
        f"{_catalog_prompt(catalog, max_new_groups)}\n\nSOURCE TAGS:\n"
        + "\n".join(_source_prompt(row, evidence) for row in batch)
    )
    result = await _classifier_agent().run(
        prompt,
        usage_limits=UsageLimits(
            request_limit=1,
            tool_calls_limit=0,
            input_tokens_limit=40_000,
            output_tokens_limit=8_000,
        ),
    )
    output = result.output
    return output.suggestions if output is not None else []


_classifier: Agent[None, SuggestionBatch] | None = None


def _classifier_agent() -> Agent[None, SuggestionBatch]:
    """Return the process-wide suggestion classifier agent."""
    global _classifier
    if _classifier is None:
        _classifier = Agent(
            model=make_openai_model(),
            output_type=SuggestionBatch,
            model_settings=_MODEL_SETTINGS,
        )
    return _classifier


async def _store_suggestions(
    pool: asyncpg.Pool, drafts: list[tuple[dict[str, Any], HubSuggestion]]
) -> None:
    """Replace pending drafts for the given source tags atomically."""
    async with pool.acquire() as conn, conn.transaction():
        for source, item in drafts:
            await conn.execute(
                """
                DELETE FROM theme_group_suggestions
                WHERE status = 'pending' AND source = $1 AND source_id = $2
                """,
                source["source"],
                source["source_id"],
            )
            if item.action == "assign":
                await _store_assign(conn, source, item)
            elif item.action == "new_group" and item.new_group is not None:
                await _store_new_group(conn, source, item)


async def _store_assign(
    conn: asyncpg.Connection, source: dict[str, Any], item: HubSuggestion
) -> None:
    group_id = await conn.fetchval(
        "SELECT id FROM theme_groups WHERE slug = $1 AND deleted_at IS NULL",
        item.group_slug,
    )
    if group_id is None:
        _log.warning("Suggestion referenced unknown group slug %r; skipping", item.group_slug)
        return
    await conn.execute(
        """
        INSERT INTO theme_group_suggestions
            (source, source_id, group_id, confidence, rationale)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (source, source_id) WHERE status = 'pending'
        DO UPDATE SET group_id = EXCLUDED.group_id, new_group_slug = NULL,
                      new_group_label = NULL, new_group_description = NULL,
                      new_group_aliases = '{}', confidence = EXCLUDED.confidence,
                      rationale = EXCLUDED.rationale, created_at = now()
        """,
        source["source"],
        source["source_id"],
        group_id,
        item.confidence,
        item.rationale,
    )


async def _store_new_group(
    conn: asyncpg.Connection, source: dict[str, Any], item: HubSuggestion
) -> None:
    proposal = item.new_group
    if proposal is None:
        return
    await conn.execute(
        """
        INSERT INTO theme_group_suggestions
            (source, source_id, new_group_slug, new_group_label,
             new_group_description, new_group_aliases, confidence, rationale)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (source, source_id) WHERE status = 'pending'
        DO UPDATE SET group_id = NULL, new_group_slug = EXCLUDED.new_group_slug,
                      new_group_label = EXCLUDED.new_group_label,
                      new_group_description = EXCLUDED.new_group_description,
                      new_group_aliases = EXCLUDED.new_group_aliases,
                      confidence = EXCLUDED.confidence,
                      rationale = EXCLUDED.rationale, created_at = now()
        """,
        source["source"],
        source["source_id"],
        proposal.slug,
        proposal.label,
        proposal.description,
        list(proposal.aliases),
        item.confidence,
        item.rationale,
    )


async def list_suggestions(pool: asyncpg.Pool, *, status: str = "pending") -> list[dict[str, Any]]:
    """Return suggestions joined with their source tag display info."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.source, s.source_id, s.confidence, s.rationale, s.status,
                   s.created_at, s.reviewed_at,
                   COALESCE(g.slug, s.new_group_slug) AS target_slug,
                   COALESCE(g.label, s.new_group_label) AS target_label,
                   COALESCE(g.description, s.new_group_description) AS target_description,
                   COALESCE(g.aliases, s.new_group_aliases) AS target_aliases,
                   COALESCE(h.name, t.name) AS source_name,
                   COALESCE(h.tag, t.tag) AS source_tag
            FROM theme_group_suggestions s
            LEFT JOIN theme_groups g ON g.id = s.group_id
            LEFT JOIN moxfield_hubs h ON h.id = s.source_id AND s.source = 'moxfield'
            LEFT JOIN archidekt_tags t ON t.id = s.source_id AND s.source = 'archidekt'
            WHERE s.status = $1
            ORDER BY s.created_at DESC, s.id DESC
            """,
            status,
        )
    return [dict(row) for row in rows]


async def apply_suggestion(pool: asyncpg.Pool, suggestion_id: int) -> dict[str, Any]:
    """Approve one pending suggestion: create the group if needed, attach the tag."""
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT * FROM theme_group_suggestions WHERE id = $1 FOR UPDATE",
            suggestion_id,
        )
        if row is None:
            raise ValueError(f"Suggestion {suggestion_id} does not exist")
        if row["status"] != "pending":
            raise ValueError(f"Suggestion {suggestion_id} is already {row['status']}")
        group_id = row["group_id"]
        if group_id is None:
            slug = row["new_group_slug"]
            group_id = await conn.fetchval(
                "SELECT id FROM theme_groups WHERE slug = $1 AND deleted_at IS NULL", slug
            )
            if group_id is None:
                label = row["new_group_label"]
                group_id = await conn.fetchval(
                    """
                    INSERT INTO theme_groups (slug, label, description, aliases, sort_order)
                    VALUES ($1, $2, $3, $4, 1000)
                    RETURNING id
                    """,
                    slug,
                    label,
                    row["new_group_description"],
                    list(row["new_group_aliases"] or []),
                )
        await _attach_source(conn, row["source"], row["source_id"], group_id)
        await conn.execute(
            """
            UPDATE theme_group_suggestions
            SET status = 'approved', reviewed_at = now()
            WHERE id = $1
            """,
            suggestion_id,
        )
    return {"id": suggestion_id, "status": "approved", "group_id": group_id}


async def _attach_source(
    conn: asyncpg.Connection, source: str, source_id: int, group_id: int
) -> None:
    if source == "moxfield":
        await conn.execute(
            """
            INSERT INTO theme_group_members (group_id, source, moxfield_hub_id)
            VALUES ($1, 'moxfield', $2)
            ON CONFLICT DO NOTHING
            """,
            group_id,
            source_id,
        )
    else:
        await conn.execute(
            """
            INSERT INTO theme_group_members (group_id, source, archidekt_tag_id)
            VALUES ($1, 'archidekt', $2)
            ON CONFLICT DO NOTHING
            """,
            group_id,
            source_id,
        )


async def reject_suggestion(pool: asyncpg.Pool, suggestion_id: int) -> dict[str, Any]:
    """Reject one pending suggestion without changing theme membership."""
    async with pool.acquire() as conn:
        status = await conn.fetchval(
            """
            UPDATE theme_group_suggestions
            SET status = 'rejected', reviewed_at = now()
            WHERE id = $1 AND status = 'pending'
            RETURNING status
            """,
            suggestion_id,
        )
    if status is None:
        raise ValueError(f"Suggestion {suggestion_id} is not pending")
    return {"id": suggestion_id, "status": "rejected"}
