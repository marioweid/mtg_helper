"""Behavior tests for LLM-drafted theme group suggestions."""

import asyncpg
import pytest

from mtg_helper.services.theme_suggestion_service import (
    HubSuggestion,
    NewGroupProposal,
    apply_suggestion,
    generate_suggestions,
    list_suggestions,
    reject_suggestion,
)

_HUB_IDS = {
    "aristocrats": 1,
    "sacrifice": 2,
    "random_junk": 3,
}


async def _seed_hubs(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO moxfield_hubs (id, slug, tag, name, description, active, enabled)
            VALUES ($1, $2, $3, $4, $5, true, true)
            """,
            [
                (
                    1,
                    "aristocrats",
                    "aristocrats",
                    "Aristocrats",
                    "Sacrifice value.",
                ),
                (
                    2,
                    "sacrifice",
                    "sacrifice",
                    "Sacrifice",
                    "Sac outlets.",
                ),
                (
                    3,
                    "random-junk",
                    "random_junk",
                    "Random Junk",
                    "Unclear theme.",
                ),
            ],
        )
        await conn.execute(
            """
            INSERT INTO theme_groups (slug, label, description)
            VALUES ('aristocrats', 'Aristocrats', 'Sacrifice payoffs.')
            """
        )


async def _classify_assign(
    batch: list[dict], evidence: dict[str, list[str]], catalog: list[dict]
) -> list[HubSuggestion]:
    del evidence, catalog
    return [
        HubSuggestion(
            tag=row["tag"],
            action="assign",
            group_slug="aristocrats",
            confidence=0.9,
            rationale=f"{row['name']} fits aristocrats.",
        )
        for row in batch
    ]


async def _classify_mixed(
    batch: list[dict], evidence: dict[str, list[str]], catalog: list[dict]
) -> list[HubSuggestion]:
    del evidence, catalog
    return [
        HubSuggestion(
            tag="sacrifice",
            action="new_group",
            new_group=NewGroupProposal(
                slug="sacrifice_value",
                label="Sacrifice Value",
                description="Sacrifice engines and drain payoffs.",
                aliases=["sac", "sacrifice value"],
            ),
            confidence=0.85,
            rationale="Distinct from aristocrats.",
        ),
        HubSuggestion(
            tag="random_junk",
            action="skip",
            confidence=0.4,
            rationale="Too niche to group.",
        ),
    ]


async def test_generate_suggestions_stores_assignments(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_hubs(db_pool)
    monkeypatch.setattr(
        "mtg_helper.services.theme_suggestion_service._classify_batch", _classify_assign
    )

    summary = await generate_suggestions(db_pool)

    assert summary == {"sources_considered": 3, "suggestions_stored": 3, "skipped": 0}
    suggestions = await list_suggestions(db_pool)
    assert len(suggestions) == 3
    assert {row["source_tag"] for row in suggestions} == {
        "aristocrats",
        "sacrifice",
        "random_junk",
    }
    assert {row["target_slug"] for row in suggestions} == {"aristocrats"}


async def test_generate_suggestions_mixed_new_group_and_skip(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_hubs(db_pool)
    monkeypatch.setattr(
        "mtg_helper.services.theme_suggestion_service._classify_batch", _classify_mixed
    )

    summary = await generate_suggestions(db_pool)

    assert summary == {"sources_considered": 3, "suggestions_stored": 1, "skipped": 2}
    suggestions = await list_suggestions(db_pool)
    assert len(suggestions) == 1
    by_tag = {row["source_tag"]: row for row in suggestions}
    assert "sacrifice" in by_tag
    assert by_tag["sacrifice"]["target_slug"] == "sacrifice_value"
    assert by_tag["sacrifice"]["target_label"] == "Sacrifice Value"
    assert by_tag["sacrifice"]["target_aliases"] == ["sac", "sacrifice value"]
    assert "random_junk" not in by_tag


async def test_generate_suggestions_returns_empty_without_sources(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _never(*_args: object) -> list[HubSuggestion]:
        raise AssertionError("classifier must not run without sources")

    monkeypatch.setattr("mtg_helper.services.theme_suggestion_service._classify_batch", _never)

    summary = await generate_suggestions(db_pool)

    assert summary == {"sources_considered": 0, "suggestions_stored": 0, "skipped": 0}


async def test_apply_assignment_attaches_member(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_hubs(db_pool)
    monkeypatch.setattr(
        "mtg_helper.services.theme_suggestion_service._classify_batch", _classify_assign
    )
    await generate_suggestions(db_pool)
    pending = await list_suggestions(db_pool)
    sacrifice = next(row for row in pending if row["source_tag"] == "sacrifice")

    result = await apply_suggestion(db_pool, sacrifice["id"])

    assert result["status"] == "approved"
    async with db_pool.acquire() as conn:
        member = await conn.fetchval(
            """
            SELECT g.label FROM theme_group_members m
            JOIN theme_groups g ON g.id = m.group_id
            WHERE m.moxfield_hub_id = 2
            """
        )
    assert member == "Aristocrats"
    remaining = await list_suggestions(db_pool)
    assert len(remaining) == 2
    assert {row["source_tag"] for row in remaining} == {"aristocrats", "random_junk"}


async def test_apply_new_group_creates_group_and_attaches(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_hubs(db_pool)
    monkeypatch.setattr(
        "mtg_helper.services.theme_suggestion_service._classify_batch", _classify_mixed
    )
    await generate_suggestions(db_pool)
    pending = await list_suggestions(db_pool)
    sacrifice = next(row for row in pending if row["source_tag"] == "sacrifice")

    result = await apply_suggestion(db_pool, sacrifice["id"])

    assert result["status"] == "approved"
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT g.slug, g.label, g.aliases
            FROM theme_group_members m
            JOIN theme_groups g ON g.id = m.group_id
            WHERE m.moxfield_hub_id = 2
            """
        )
    assert row["slug"] == "sacrifice_value"
    assert row["label"] == "Sacrifice Value"
    assert row["aliases"] == ["sac", "sacrifice value"]


async def test_reject_marks_suggestion_rejected(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_hubs(db_pool)
    monkeypatch.setattr(
        "mtg_helper.services.theme_suggestion_service._classify_batch", _classify_assign
    )
    await generate_suggestions(db_pool)
    pending = await list_suggestions(db_pool)
    junk = next(row for row in pending if row["source_tag"] == "random_junk")

    result = await reject_suggestion(db_pool, junk["id"])

    assert result["status"] == "rejected"
    remaining = await list_suggestions(db_pool)
    assert len(remaining) == 2
    rejected = await list_suggestions(db_pool, status="rejected")
    assert [row["source_tag"] for row in rejected] == ["random_junk"]


async def test_apply_non_pending_suggestion_raises(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_hubs(db_pool)
    monkeypatch.setattr(
        "mtg_helper.services.theme_suggestion_service._classify_batch", _classify_assign
    )
    await generate_suggestions(db_pool)
    pending = await list_suggestions(db_pool)
    junk = next(row for row in pending if row["source_tag"] == "random_junk")
    await reject_suggestion(db_pool, junk["id"])

    with pytest.raises(ValueError, match="already rejected"):
        await apply_suggestion(db_pool, junk["id"])
