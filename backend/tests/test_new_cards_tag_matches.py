"""Real route regressions for read-only Scryfall tag matches."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest

from tests.conftest import (
    DOCKSIDE_ORACLE_ID,
    DOUBLING_SEASON_ORACLE_ID,
    HAZEL_ORACLE_ID,
    RHYSTIC_STUDY_ORACLE_ID,
    SOL_RING_ORACLE_ID,
    create_test_account,
    create_test_deck,
)

pytestmark = pytest.mark.asyncio

PARENT_TAG = UUID("00000000-0000-4000-8000-000000000101")
CHILD_TAG = UUID("00000000-0000-4000-8000-000000000102")
PARTNER_TAG = UUID("00000000-0000-4000-8000-000000000103")
BRIDGE_TAG = UUID("00000000-0000-4000-8000-000000000104")
FOREST_ORACLE_ID = UUID("6d7b8d2c-aaaa-40e7-91de-9c8c1b44da67")
SOURCE_HASH = "a" * 64


def _facts(oracle_id: UUID, name: str, colors: list[str]) -> str:
    return json.dumps(
        {
            "oracle_id": str(oracle_id),
            "name": name,
            "color_identity": colors,
            "commander_legality": "legal",
            "layout": "normal",
            "oracle_text": "Source text.",
            "faces": [],
            "game_changer": False,
        }
    )


async def _seed_current_sources(db_pool) -> None:
    now = datetime.now(UTC)
    release = now.date() - timedelta(days=1)
    rows = [
        (HAZEL_ORACLE_ID, "Hazel", ["G", "W"]),
        (DOCKSIDE_ORACLE_ID, "Dockside", ["R"]),
        (DOUBLING_SEASON_ORACLE_ID, "Doubling Season", ["G"]),
        (SOL_RING_ORACLE_ID, "Sol Ring", []),
        (RHYSTIC_STUDY_ORACLE_ID, "Rhystic Study", ["U"]),
        (FOREST_ORACLE_ID, "Forest", ["G"]),
    ]
    await db_pool.execute(
        "UPDATE cards SET color_identity = ARRAY['U']::text[] WHERE oracle_id = $1",
        RHYSTIC_STUDY_ORACLE_ID,
    )
    await db_pool.execute(
        "INSERT INTO recommendation_sources (sha256, kind, payload) VALUES ($1, 'cards', $2) "
        "ON CONFLICT DO NOTHING",
        SOURCE_HASH,
        b"test",
    )
    for oracle_id, name, colors in rows:
        await db_pool.execute(
            "INSERT INTO new_card_catalog (oracle_id, first_paper, released_at, facts, generation) "
            "VALUES ($1, $2, $2, $3::jsonb, $4)",
            oracle_id,
            release,
            _facts(oracle_id, name, colors),
            UUID("00000000-0000-4000-8000-000000000201"),
        )
    await db_pool.execute(
        "INSERT INTO new_card_catalog_state "
        "(generation, started_at, published_at, card_count, source_sha256) "
        "VALUES ($1, $2, $2, $3, $4)",
        UUID("00000000-0000-4000-8000-000000000201"),
        now,
        len(rows),
        SOURCE_HASH,
    )
    await db_pool.executemany(
        "INSERT INTO scryfall_tags (id, slug, metadata) VALUES ($1, $2, $3::jsonb)",
        [
            (PARENT_TAG, "parent", '{"label":"Parent"}'),
            (CHILD_TAG, "child", '{"label":"Child"}'),
            (PARTNER_TAG, "partner", '{"label":"Partner"}'),
            (BRIDGE_TAG, "bridge", '{"label":"Bridge"}'),
        ],
    )
    await db_pool.executemany(
        "INSERT INTO scryfall_tag_descendants (ancestor_id, descendant_id) VALUES ($1, $2)",
        [
            (PARENT_TAG, PARENT_TAG),
            (PARENT_TAG, CHILD_TAG),
            (PARENT_TAG, BRIDGE_TAG),
            (BRIDGE_TAG, CHILD_TAG),
            (CHILD_TAG, CHILD_TAG),
            (PARTNER_TAG, PARTNER_TAG),
        ],
    )
    await db_pool.executemany(
        "INSERT INTO scryfall_tag_memberships (tag_id, oracle_id, details) "
        "VALUES ($1, $2, '{}'::jsonb)",
        [
            (PARENT_TAG, HAZEL_ORACLE_ID),
            (PARTNER_TAG, DOCKSIDE_ORACLE_ID),
            (CHILD_TAG, DOUBLING_SEASON_ORACLE_ID),
            (PARENT_TAG, SOL_RING_ORACLE_ID),
            (PARTNER_TAG, SOL_RING_ORACLE_ID),
            (CHILD_TAG, FOREST_ORACLE_ID),
            (PARENT_TAG, RHYSTIC_STUDY_ORACLE_ID),
        ],
    )
    await db_pool.execute(
        "INSERT INTO scryfall_tag_state "
        "(source_sha256, tag_sha256, archive_sha256, manifest, started_at, published_at, "
        "tag_count, membership_count) VALUES ($1, $1, $1, '{}'::jsonb, $2, $2, 1000, 1000)",
        SOURCE_HASH,
        now,
    )


async def _deck_with_sources(client, db_pool, *, partner: bool = False) -> str:
    deck_id = await create_test_deck(client)
    await _seed_current_sources(db_pool)
    if partner:
        await db_pool.execute(
            "UPDATE decks SET partner_id = (SELECT id FROM cards WHERE oracle_id = $1) "
            "WHERE id = $2",
            DOCKSIDE_ORACLE_ID,
            UUID(deck_id),
        )
    return deck_id


async def _add_completion_candidate(db_pool) -> UUID:
    oracle_id = uuid4()
    await db_pool.execute(
        "INSERT INTO cards (scryfall_id, oracle_id, name, type_line, oracle_text, color_identity, "
        "legalities, prices, is_canonical) VALUES ($1, $2, 'Completion candidate', "
        "'Artifact', 'Source text.', ARRAY['G']::text[], '{\"commander\":\"legal\"}'::jsonb, "
        "'{}'::jsonb, true)",
        uuid4(),
        oracle_id,
    )
    await db_pool.execute(
        "INSERT INTO new_card_catalog (oracle_id, first_paper, released_at, facts, generation) "
        "VALUES ($1, CURRENT_DATE, CURRENT_DATE, $2::jsonb, $3)",
        oracle_id,
        _facts(oracle_id, "Completion candidate", ["G"]),
        UUID("00000000-0000-4000-8000-000000000201"),
    )
    await db_pool.execute(
        "INSERT INTO scryfall_tag_memberships (tag_id, oracle_id, details) "
        "VALUES ($1, $2, '{}'::jsonb)",
        PARENT_TAG,
        oracle_id,
    )
    return oracle_id


async def test_ac01_get_is_read_only_and_ignores_historical_ai_state(
    client, db_pool, monkeypatch
) -> None:
    deck_id = await _deck_with_sources(client, db_pool)
    account_id = await db_pool.fetchval(
        "SELECT id FROM accounts WHERE email = $1", "default@test.local"
    )
    await db_pool.execute(
        "INSERT INTO new_card_assessments (deck_id, account_id, oracle_id, input_hash, assessment) "
        "VALUES ($1, $2, $3, 'historical', '{}'::jsonb)",
        UUID(deck_id),
        account_id,
        SOL_RING_ORACLE_ID,
    )
    await db_pool.execute(
        "UPDATE new_card_runs SET last_error = 'historical failure' WHERE singleton"
    )
    before = await db_pool.fetch(
        "SELECT (SELECT count(*) FROM accounts), (SELECT count(*) FROM decks), "
        "(SELECT count(*) FROM new_card_assessments), "
        "(SELECT count(*) FROM deck_card_plans), "
        "(SELECT count(*) FROM new_card_dismissals)"
    )

    async def block_external_transport(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("New Cards GET must not make external HTTP requests")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", block_external_transport)
    for _ in range(2):
        response = await client.get(f"/api/v1/decks/{deck_id}/new-cards")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "ready"
    assert (
        await db_pool.fetch(
            "SELECT (SELECT count(*) FROM accounts), (SELECT count(*) FROM decks), "
            "(SELECT count(*) FROM new_card_assessments), "
            "(SELECT count(*) FROM deck_card_plans), "
            "(SELECT count(*) FROM new_card_dismissals)"
        )
        == before
    )
    assert (
        await db_pool.fetchval("SELECT last_error FROM new_card_runs WHERE singleton")
        == "historical failure"
    )


async def test_ac02_matches_descendants_once_per_commander_tag_and_ranks(client, db_pool) -> None:
    deck_id = await _deck_with_sources(client, db_pool, partner=True)
    await db_pool.execute(
        "UPDATE cards SET color_identity = ARRAY['G']::text[] WHERE oracle_id = $1",
        RHYSTIC_STUDY_ORACLE_ID,
    )
    await db_pool.execute(
        "UPDATE new_card_catalog SET facts = jsonb_set(facts, '{color_identity}', '[\"G\"]') "
        "WHERE oracle_id = $1",
        RHYSTIC_STUDY_ORACLE_ID,
    )
    await db_pool.execute(
        "UPDATE new_card_catalog SET released_at = CURRENT_DATE WHERE oracle_id IN ($1, $2)",
        FOREST_ORACLE_ID,
        RHYSTIC_STUDY_ORACLE_ID,
    )
    await db_pool.execute(
        "INSERT INTO cards (scryfall_id, oracle_id, name, type_line, oracle_text, color_identity, "
        "legalities, prices, is_canonical) "
        "SELECT $1, oracle_id, name, type_line, oracle_text, color_identity, "
        "legalities, prices, false "
        "FROM cards WHERE oracle_id = $2 AND is_canonical",
        uuid4(),
        DOUBLING_SEASON_ORACLE_ID,
    )
    response = await client.get(f"/api/v1/decks/{deck_id}/new-cards")
    assert response.status_code == 200
    matches = response.json()["data"]["matches"]
    assert [match["name"] for match in matches] == [
        "Sol Ring",
        "Forest",
        "Rhystic Study",
        "Doubling Season",
    ]
    assert matches[0]["matching_tag_count"] == 2
    assert matches[-1]["matching_tag_count"] == 1
    assert {item["relation"] for item in matches[-1]["tag_matches"]} == {"descendant"}
    assert len([match for match in matches if match["name"] == "Doubling Season"]) == 1


async def test_ac03_plan_is_idempotent_after_the_candidate_is_hidden(client, db_pool) -> None:
    deck_id = await _deck_with_sources(client, db_pool)
    for _ in range(2):
        response = await client.post(f"/api/v1/decks/{deck_id}/new-cards/{SOL_RING_ORACLE_ID}/plan")
        assert response.status_code == 200, response.text
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM deck_card_plans WHERE deck_id = $1", UUID(deck_id)
        )
        == 1
    )
    assert (
        await db_pool.fetchval("SELECT count(*) FROM deck_cards WHERE deck_id = $1", UUID(deck_id))
        == 0
    )


async def test_ac03_actions_are_owner_scoped_and_dismissals_are_deck_local(client, db_pool) -> None:
    deck_id = await _deck_with_sources(client, db_pool)
    dismissed = await client.post(f"/api/v1/decks/{deck_id}/new-cards/{SOL_RING_ORACLE_ID}/dismiss")
    assert dismissed.status_code == 200
    assert str(SOL_RING_ORACLE_ID) not in {
        match["oracle_id"] for match in dismissed.json()["data"]["matches"]
    }
    await create_test_account(client, "Other")
    other_deck_id = await create_test_deck(client, name="Other Deck")
    other_result = await client.get(f"/api/v1/decks/{other_deck_id}/new-cards")
    assert other_result.status_code == 200
    assert str(SOL_RING_ORACLE_ID) in {
        match["oracle_id"] for match in other_result.json()["data"]["matches"]
    }
    for method, suffix in [
        (client.get, ""),
        (client.post, f"/{SOL_RING_ORACLE_ID}/plan"),
        (client.post, f"/{SOL_RING_ORACLE_ID}/dismiss"),
        (client.delete, f"/{SOL_RING_ORACLE_ID}/dismiss"),
    ]:
        response = await method(f"/api/v1/decks/{deck_id}/new-cards{suffix}")
        assert response.status_code == 404


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("change", ["banned", "color", "copy"])
async def test_ac03_completion_rechecks_new_card_guards(client, db_pool, batch, change) -> None:
    deck_id = UUID(await _deck_with_sources(client, db_pool))
    oracle_id = await _add_completion_candidate(db_pool)
    planned = await client.post(f"/api/v1/decks/{deck_id}/new-cards/{oracle_id}/plan")
    assert planned.status_code == 200, planned.text
    plan_id = await db_pool.fetchval("SELECT id FROM deck_card_plans WHERE deck_id = $1", deck_id)
    card_id = await db_pool.fetchval("SELECT id FROM cards WHERE oracle_id = $1", oracle_id)
    assert plan_id is not None and card_id is not None
    if change == "banned":
        await db_pool.execute(
            'UPDATE cards SET legalities = \'{"commander":"banned"}\'::jsonb WHERE id = $1',
            card_id,
        )
    elif change == "color":
        await db_pool.execute(
            "UPDATE new_card_catalog SET facts = jsonb_set(facts, '{color_identity}', '[\"U\"]') "
            "WHERE oracle_id = $1",
            oracle_id,
        )
    else:
        await db_pool.execute(
            "INSERT INTO deck_cards (deck_id, card_id) VALUES ($1, $2)", deck_id, card_id
        )
    if batch:
        response = await client.post(
            f"/api/v1/decks/{deck_id}/revisions",
            json={"title": "Complete tag match", "plan_ids": [str(plan_id)]},
        )
    else:
        response = await client.post(
            f"/api/v1/decks/{deck_id}/planned-changes/{plan_id}/complete", json={"quantity": 1}
        )
    assert response.status_code == 422, response.text
    assert (
        await db_pool.fetchval("SELECT count(*) FROM deck_card_plans WHERE id = $1", plan_id) == 1
    )
    assert (
        await db_pool.fetchval("SELECT count(*) FROM deck_revisions WHERE deck_id = $1", deck_id)
        == 0
    )


async def test_ac04_next_read_uses_current_tags_and_reports_bad_source_state(
    client, db_pool
) -> None:
    deck_id = await _deck_with_sources(client, db_pool)
    await db_pool.execute(
        "DELETE FROM scryfall_tag_memberships WHERE oracle_id = $1", SOL_RING_ORACLE_ID
    )
    response = await client.get(f"/api/v1/decks/{deck_id}/new-cards")
    assert response.status_code == 200
    assert [match["name"] for match in response.json()["data"]["matches"]] == [
        "Doubling Season",
        "Forest",
    ]
    await db_pool.execute(
        "INSERT INTO recommendation_sources (sha256, kind, payload) VALUES ($1, 'cards', $2) "
        "ON CONFLICT DO NOTHING",
        "b" * 64,
        b"mismatch",
    )
    await db_pool.execute("UPDATE scryfall_tag_state SET source_sha256 = $1", "b" * 64)
    response = await client.get(f"/api/v1/decks/{deck_id}/new-cards")
    assert response.json()["data"]["status"] == "source_mismatched"
    assert response.json()["data"]["matches"] == []
    await db_pool.execute("UPDATE scryfall_tag_state SET source_sha256 = $1", SOURCE_HASH)
    await db_pool.execute(
        "UPDATE scryfall_tag_state SET published_at = $1", datetime.now(UTC) - timedelta(days=3)
    )
    response = await client.get(f"/api/v1/decks/{deck_id}/new-cards")
    assert response.json()["data"]["status"] == "source_stale"
    await db_pool.execute("UPDATE scryfall_tag_state SET published_at = NOW()")
    await db_pool.execute(
        "DELETE FROM scryfall_tag_memberships WHERE oracle_id = $1", HAZEL_ORACLE_ID
    )
    response = await client.get(f"/api/v1/decks/{deck_id}/new-cards")
    assert response.json()["data"]["status"] == "unavailable"
