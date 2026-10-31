"""Real application seam checks for saved, local Scryfall Discover matching."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import AsyncClient

from mtg_helper.services import feature_flag_service
from mtg_helper.services.new_cards import catalog
from mtg_helper.services.recommendations import budget, provider
from tests.conftest import SOL_RING_ORACLE_ID, create_test_account, create_test_deck

PARENT = UUID("20000000-0000-0000-0000-000000000001")
CHILD = UUID("20000000-0000-0000-0000-000000000002")


@pytest_asyncio.fixture
async def discover_deck(client: AsyncClient, db_pool: asyncpg.Pool) -> str:
    """Publish a minimal complete local source and enable Discover for this account."""
    rows = await db_pool.fetch("SELECT * FROM cards")
    sources = [
        dict(row)
        | {
            "oracle_id": str(row["oracle_id"]),
            "legalities": json.loads(row["legalities"]),
            "games": ["paper"],
            "layout": "normal",
            "set_type": "expansion",
            "keywords": ["Flying"] if row["oracle_id"] == SOL_RING_ORACLE_ID else [],
        }
        for row in rows
    ]
    async with db_pool.acquire() as conn, conn.transaction():
        await catalog.publish(conn, sources, {}, datetime.now(UTC))
        source_hash = await conn.fetchval("SELECT source_sha256 FROM new_card_catalog_state")
        tag_hash = sha256(b"discover-test-tags").hexdigest()
        await conn.execute(
            "INSERT INTO recommendation_sources (sha256, kind, payload) "
            "VALUES ($1,'oracle_tags','\\x00') ON CONFLICT DO NOTHING",
            tag_hash,
        )
        await conn.execute(
            "INSERT INTO scryfall_tag_state (singleton,source_sha256,tag_sha256,archive_sha256,"
            "manifest,started_at,published_at,tag_count,membership_count) "
            "VALUES (true,$1,$2,$3,'{}',now(),now(),1000,1000)",
            source_hash,
            tag_hash,
            source_hash,
        )
        await conn.execute(
            "INSERT INTO scryfall_tags (id,slug,metadata) VALUES ($1,'parent',$2),($3,'child',$4)",
            PARENT,
            json.dumps({"label": "Parent"}),
            CHILD,
            json.dumps({"label": "Child"}),
        )
        await conn.execute(
            "INSERT INTO scryfall_tag_descendants (ancestor_id,descendant_id) "
            "VALUES ($1,$1),($1,$2),($2,$2)",
            PARENT,
            CHILD,
        )
        await conn.execute(
            "INSERT INTO scryfall_tag_memberships (tag_id,oracle_id,details) VALUES ($1,$2,'{}')",
            CHILD,
            SOL_RING_ORACLE_ID,
        )
        account = await conn.fetchrow("SELECT id FROM accounts WHERE email='default@test.local'")
    assert account is not None
    await feature_flag_service.set_flag(db_pool, "recommendations", True, account["id"])
    return await create_test_deck(client)


def path(deck_id: str) -> str:
    return f"/api/v1/decks/{deck_id}/recommendations"


def search_query(*, tags: list[UUID] | None = None, keywords: list[str] | None = None) -> dict:
    return {
        "purpose": "Selected source criteria",
        "groups": [
            {"oracle_tag_ids": [str(tag) for tag in tags or []], "printed_keywords": keywords or []}
        ],
        "card_types_any": [],
    }


@pytest.mark.asyncio
async def test_queries_filter_before_popularity_and_keep_missing_ranks(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    identities = await seed_matches(db_pool, 3)
    await db_pool.execute("UPDATE cards SET edhrec_rank=1 WHERE oracle_id=$1", identities[2])
    await db_pool.execute("UPDATE cards SET edhrec_rank=2 WHERE oracle_id=$1", identities[1])
    saved = await client.put(
        path(discover_deck) + "/strategy",
        json={
            "prose": "Flying artifacts",
            "queries": [search_query(keywords=["Flying"])],
        },
    )
    assert saved.status_code == 200
    result = (await client.get(path(discover_deck) + "/matches")).json()["data"]
    assert [row["oracle_id"] for row in result["cards"][:2]] == [
        str(identities[2]),
        str(identities[1]),
    ]
    assert result["total"] == 4


@pytest.mark.asyncio
async def test_groups_intersect_searches_union_and_evidence_ignores_failed_searches(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    identities = await seed_matches(db_pool, 2)
    await db_pool.execute(
        "INSERT INTO scryfall_tag_memberships (tag_id,oracle_id,details) VALUES ($1,$2,'{}')",
        CHILD,
        identities[0],
    )
    intersected = search_query(tags=[PARENT])
    intersected["groups"].append({"oracle_tag_ids": [], "printed_keywords": ["Flying"]})
    # The unmatched keyword-only card must not leak through the AND, even if popular.
    await db_pool.execute("UPDATE cards SET edhrec_rank=1 WHERE oracle_id=$1", identities[1])
    response = await client.put(
        path(discover_deck) + "/strategy",
        json={
            "prose": "Tagged and flying",
            "queries": [intersected],
        },
    )
    assert response.status_code == 200
    result = (await client.get(path(discover_deck) + "/matches")).json()["data"]
    assert {card["oracle_id"] for card in result["cards"]} == {
        str(SOL_RING_ORACLE_ID),
        str(identities[0]),
    }
    assert all(card["match_count"] == 2 for card in result["cards"])
    second = search_query(keywords=["Flying"])
    second["purpose"] = "Alternative"
    saved = await client.put(
        path(discover_deck) + "/strategy",
        json={
            "prose": "Alternative searches",
            "queries": [intersected, second],
            "revision": response.json()["data"]["revision"],
        },
    )
    assert saved.status_code == 200
    result = (await client.get(path(discover_deck) + "/matches")).json()["data"]
    assert result["cards"][0]["oracle_id"] == str(identities[1])
    assert {item["query_purpose"] for item in result["cards"][0]["evidence"]} == {"Alternative"}


@pytest.mark.asyncio
async def test_creature_scope_uses_front_face_not_transformed_back(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    identities = await seed_matches(db_pool, 2)
    facts = json.loads(
        await db_pool.fetchval(
            "SELECT source_facts FROM new_card_catalog WHERE oracle_id=$1", identities[0]
        )
    )
    facts.update(
        type_line="Battle — Siege // Creature — Beast",
        card_faces=[
            {"type_line": "Battle — Siege"},
            {"type_line": "Creature — Beast"},
        ],
    )
    await db_pool.execute(
        "UPDATE new_card_catalog SET source_facts=$2::jsonb WHERE oracle_id=$1",
        identities[0],
        json.dumps(facts),
    )
    facts = facts | {
        "oracle_id": str(identities[1]),
        "type_line": "Artifact Creature — Beast",
        "card_faces": [],
    }
    await db_pool.execute(
        "UPDATE new_card_catalog SET source_facts=$2::jsonb WHERE oracle_id=$1",
        identities[1],
        json.dumps(facts),
    )
    query = search_query(keywords=["Flying"])
    query["card_types_any"] = ["Creature"]
    await client.put(
        path(discover_deck) + "/strategy", json={"prose": "Creatures", "queries": [query]}
    )
    result = (await client.get(path(discover_deck) + "/matches")).json()["data"]
    assert [card["oracle_id"] for card in result["cards"]] == [str(identities[1])]
    rejected = await client.post(path(discover_deck) + f"/matches/{identities[0]}/plan")
    assert rejected.status_code == 409


@pytest.mark.asyncio
async def test_rank_changes_invalidate_cursor_and_unknown_ranks_remain_pageable(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    identities = await seed_matches(db_pool, 45)
    await db_pool.execute(
        "UPDATE cards SET edhrec_rank=7 WHERE oracle_id=ANY($1::uuid[])", identities[:41]
    )
    await db_pool.execute("UPDATE cards SET edhrec_rank=0 WHERE oracle_id=$1", identities[-1])
    await client.put(
        path(discover_deck) + "/strategy",
        json={
            "prose": "Flying",
            "queries": [search_query(keywords=["Flying"])],
        },
    )
    first = (await client.get(path(discover_deck) + "/matches")).json()["data"]
    second = (
        await client.get(path(discover_deck) + "/matches", params={"cursor": first["next_cursor"]})
    ).json()["data"]
    cards = first["cards"] + second["cards"]
    assert len({card["oracle_id"] for card in cards}) == 46
    assert all(card["global_popularity_rank"] == 7 for card in cards[:41])
    assert all(card["global_popularity_rank"] is None for card in cards[41:])
    await db_pool.execute("UPDATE cards SET edhrec_rank=1 WHERE oracle_id=$1", identities[-1])
    stale = await client.get(
        path(discover_deck) + "/matches", params={"cursor": first["next_cursor"]}
    )
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_flat_strategy_upgrade_preserves_user_state_and_does_not_resume_old_terms(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    from mtg_helper.db import apply_schema

    response = await client.put(
        path(discover_deck) + "/strategy",
        json={
            "prose": "Preserve my strategy",
            "queries": [search_query(tags=[PARENT])],
        },
    )
    before = response.json()["data"]
    deck_before = await db_pool.fetchval(
        "SELECT to_jsonb(d)::text FROM decks d WHERE id=$1", UUID(discover_deck)
    )
    await db_pool.execute(
        "ALTER TABLE discover_strategies DROP COLUMN queries; "
        "ALTER TABLE discover_strategies ADD COLUMN oracle_tag_ids uuid[] NOT NULL DEFAULT '{}'; "
        "ALTER TABLE discover_strategies ADD COLUMN printed_keywords text[] NOT NULL DEFAULT '{}'"
    )
    await db_pool.execute(
        "UPDATE discover_strategies SET oracle_tag_ids=$1, printed_keywords=$2",
        [PARENT],
        ["Flying"],
    )
    run_id = await db_pool.fetchval(
        "INSERT INTO recommendation_runs (id,account_id,deck_id,request_key,request_hash,"
        "source_hash,rules_hash,profile,context,data,status,token,held_microusd) "
        "SELECT gen_random_uuid(),account_id,deck_id,gen_random_uuid(),'old',source_sha256,"
        "source_sha256,'app-strategy-terms-v1','{}','{\"oracle_tag_ids\":[]}',"
        "'completed',gen_random_uuid(),123 FROM discover_strategies,new_card_catalog_state "
        "RETURNING id"
    )
    await apply_schema(db_pool)
    await apply_schema(db_pool)
    after = (await client.get(path(discover_deck) + "/status")).json()["data"]["strategy"]
    assert after["prose"] == before["prose"] and after["revision"] == before["revision"]
    assert after["queries"][0]["groups"] == [
        {"oracle_tag_ids": [str(PARENT)], "printed_keywords": ["Flying"]}
    ]
    assert after["queries"][0]["card_types_any"] == []
    assert (
        await db_pool.fetchval(
            "SELECT to_jsonb(d)::text FROM decks d WHERE id=$1", UUID(discover_deck)
        )
        == deck_before
    )
    row = await db_pool.fetchrow(
        "SELECT status,held_microusd,data FROM recommendation_runs WHERE id=$1", run_id
    )
    assert row["status"] == "completed" and row["held_microusd"] == 123
    assert json.loads(row["data"]) == {"oracle_tag_ids": []}
    setup = (await client.get(path(discover_deck) + "/setup")).json()["data"]
    assert setup["suggestion"] is None
    assert (
        await client.get(path(discover_deck) + f"/term-suggestions/{run_id}")
    ).status_code == 404


@pytest.mark.asyncio
async def test_commander_and_partner_relationships_expand_suggestion_catalog(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    from mtg_helper.services.recommendations.term_catalog import suggestion_catalog

    source = json.loads(
        await db_pool.fetchval(
            "SELECT source_facts FROM new_card_catalog WHERE oracle_id=$1", SOL_RING_ORACLE_ID
        )
    )
    other = uuid4()
    relation = uuid4()
    await db_pool.execute(
        "INSERT INTO scryfall_tags (id,slug,metadata) VALUES ($1,'zz-related',$2::jsonb)",
        relation,
        json.dumps({"label": "Related engine", "description": "Useful source description"}),
    )
    await db_pool.execute(
        "UPDATE scryfall_tags SET metadata=metadata || $2::jsonb WHERE id=$1",
        CHILD,
        json.dumps({"parent_ids": [str(relation)]}),
    )
    async with db_pool.acquire() as conn:
        menu = await suggestion_catalog(
            conn, [source | {"oracle_id": str(other)}, source], "A plan"
        )
    tags = {tag["id"]: tag for tag in menu.oracle_tags}
    assert (
        str(relation) in tags and tags[str(relation)]["description"] == "Useful source description"
    )
    assert str(CHILD) in tags
    assert len(tags) <= 160 and len(menu.printed_keywords) <= 120


@pytest.mark.asyncio
async def test_ac01_ac04_local_strategy_matches_need_no_model_or_rules(
    client: AsyncClient, discover_deck: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def reject_network(*args, **kwargs):
        raise AssertionError("Local discovery attempted external HTTP")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_network)
    saved = await client.put(
        path(discover_deck) + "/strategy",
        json={"prose": "Artifacts", "queries": [search_query(tags=[PARENT])]},
    )
    assert saved.status_code == 200
    first = await client.get(path(discover_deck) + "/matches")
    second = await client.get(path(discover_deck) + "/matches")
    assert first.json() == second.json()
    card = first.json()["data"]["cards"][0]
    assert card["oracle_id"] == str(SOL_RING_ORACLE_ID)
    assert card["match_count"] == 1
    assert card["evidence"][0]["relation"] == "descendant"


async def seed_matches(
    pool: asyncpg.Pool, count: int, *, colors: list[str] | None = None
) -> list[UUID]:
    """Add distinct synthetic source designs without bypassing matching or authorization."""
    raw = await pool.fetchrow(
        "SELECT facts,source_facts FROM new_card_catalog WHERE oracle_id=$1", SOL_RING_ORACLE_ID
    )
    template = json.loads(raw["source_facts"])
    summary = json.loads(raw["facts"])
    identities = [uuid4() for _ in range(count)]
    for i, identity in enumerate(identities):
        name = f"Fixture Artifact {i:03d}"
        facts = template | {
            "oracle_id": str(identity),
            "name": name,
            "color_identity": colors or [],
        }
        display = summary | {
            "oracle_id": str(identity),
            "name": name,
            "color_identity": colors or [],
        }
        await pool.execute(
            "INSERT INTO cards (scryfall_id,oracle_id,name,type_line,color_identity,legalities,"
            "keywords,is_canonical) VALUES ($1,$2,$3,'Artifact',$4,'{\"commander\":\"legal\"}',"
            "ARRAY['Flying'],true)",
            uuid4(),
            identity,
            name,
            colors or [],
        )
        await pool.execute(
            "INSERT INTO new_card_catalog (oracle_id,facts,source_facts,generation) "
            "SELECT $1,$2::jsonb,$3::jsonb,generation FROM new_card_catalog_state",
            identity,
            json.dumps(display),
            json.dumps(facts),
        )
    return identities


@pytest.mark.asyncio
async def test_ac05_ac07_all_pages_are_distinct_and_page_two_can_be_planned(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    identities = await seed_matches(db_pool, 45)
    saved = await client.put(
        path(discover_deck) + "/strategy",
        json={
            "prose": "Flying artifacts",
            "queries": [search_query(keywords=["Flying"])],
        },
    )
    assert saved.status_code == 200
    first = (await client.get(path(discover_deck) + "/matches")).json()["data"]
    assert first["total"] == 46 and len(first["cards"]) == 40
    second = (
        await client.get(
            path(discover_deck) + "/matches",
            params={
                "cursor": first["next_cursor"],
            },
        )
    ).json()["data"]
    seen = [c["oracle_id"] for c in first["cards"] + second["cards"]]
    assert len(set(seen)) == 46 and second["next_cursor"] is None
    assert set(map(str, identities)) <= set(seen)
    target = second["cards"][0]["oracle_id"]
    for _ in range(2):
        response = await client.post(path(discover_deck) + f"/matches/{target}/plan")
        assert response.status_code == 200, response.text
    stale = await client.get(
        path(discover_deck) + "/matches", params={"cursor": first["next_cursor"]}
    )
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_ac03_term_retrieval_can_select_relevant_tags_beyond_the_first_eighty(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    from mtg_helper.services.recommendations.strategy_discover import source_terms

    await db_pool.executemany(
        "INSERT INTO scryfall_tags (id,slug,metadata) VALUES ($1,$2,$3::jsonb)",
        [
            (uuid4(), f"a-fixture-{i:03d}", json.dumps({"label": f"A Fixture {i:03d}"}))
            for i in range(90)
        ],
    )
    relevant = uuid4()
    await db_pool.execute(
        "INSERT INTO scryfall_tags (id,slug,metadata) VALUES ($1,'zombie',"
        '\'{"label":"Zombie","description":"Zombie creatures"}\')',
        relevant,
    )
    async with db_pool.acquire() as conn:
        terms = await source_terms(conn, prose="Zombie creatures")
    assert relevant in [tag["id"] for tag in terms.oracle_tags]
    catalog = (await client.get(path(discover_deck) + "/source-terms")).json()["data"]
    assert len(catalog["oracle_tags"]) == 93


@pytest.mark.asyncio
async def test_ac07_partner_colors_and_commander_changes_invalidate_continuations(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    identities = await seed_matches(db_pool, 45, colors=["U"])
    await client.put(
        path(discover_deck) + "/strategy",
        json={
            "prose": "Flying artifacts",
            "queries": [search_query(keywords=["Flying"])],
        },
    )
    before = (await client.get(path(discover_deck) + "/matches")).json()["data"]
    assert before["total"] == 1
    partner = await db_pool.fetchval("SELECT id FROM cards WHERE name='Rhystic Study'")
    await db_pool.execute(
        "UPDATE decks SET partner_id=$2 WHERE id=$1", UUID(discover_deck), partner
    )
    after = (await client.get(path(discover_deck) + "/matches")).json()["data"]
    assert after["total"] == 46
    response = await client.post(path(discover_deck) + f"/matches/{identities[0]}/plan")
    assert response.status_code == 200, response.text
    cursor = (await client.get(path(discover_deck) + "/matches")).json()["data"]["next_cursor"]
    await db_pool.execute("UPDATE decks SET partner_id=NULL WHERE id=$1", UUID(discover_deck))
    assert (
        await client.get(path(discover_deck) + "/matches", params={"cursor": cursor})
    ).status_code == 409


@pytest.mark.asyncio
async def test_ac02_strategy_round_trips_and_rejects_conflicting_save(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    before = await db_pool.fetchval(
        "SELECT to_jsonb(d) FROM decks d WHERE id=$1", UUID(discover_deck)
    )
    initial = await client.put(
        path(discover_deck) + "/strategy",
        json={"prose": "Flying artifacts", "queries": [search_query(keywords=["Flying"])]},
    )
    strategy = initial.json()["data"]
    assert (await client.get(path(discover_deck) + "/status")).json()["data"][
        "strategy"
    ] == strategy
    conflict = await client.put(
        path(discover_deck) + "/strategy",
        json={
            "prose": "Changed",
            "queries": [],
            "revision": str(UUID(int=0)),
        },
    )
    assert conflict.status_code == 409
    assert (await client.get(path(discover_deck) + "/status")).json()["data"]["strategy"][
        "prose"
    ] == "Flying artifacts"
    after = await db_pool.fetchval(
        "SELECT to_jsonb(d) FROM decks d WHERE id=$1", UUID(discover_deck)
    )
    assert before == after


@pytest.mark.asyncio
async def test_ac05_cursor_is_explicitly_invalidated_by_a_dismissal(
    client: AsyncClient, discover_deck: str
) -> None:
    await client.put(
        path(discover_deck) + "/strategy",
        json={"prose": "Artifacts", "queries": [search_query(tags=[PARENT])]},
    )
    result = (await client.get(path(discover_deck) + "/matches")).json()["data"]
    oracle_id = result["cards"][0]["oracle_id"]
    assert (
        await client.post(path(discover_deck) + f"/matches/{oracle_id}/dismiss")
    ).status_code == 200
    assert (await client.get(path(discover_deck) + "/matches")).json()["data"]["cards"] == []


@pytest.mark.asyncio
async def test_ac09_retired_card_generation_cannot_start(
    client: AsyncClient, discover_deck: str
) -> None:
    response = await client.post(
        path(discover_deck) + "/runs", json={"request_key": str(UUID(int=1)), "goal": "old"}
    )
    assert response.status_code == 410


@pytest.mark.asyncio
async def test_ac03_explicit_terms_are_catalog_validated_and_never_saved_implicitly(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the provider transport is substituted; the run/accounting path is real."""

    class Transport:
        calls = 0

        async def handle(self, request: httpx.Request) -> httpx.Response:
            self.calls += 1
            frozen = json.loads(request.content)
            sent = json.loads(frozen["input"])
            assert len(sent["commanders"]) == 1
            assert all("description" in tag for tag in sent["oracle_tags"])
            schema = frozen["text"]["format"]["schema"]
            choices = schema["properties"]["oracle_tag_ids"]
            assert choices["maxItems"] == 8
            enum = schema["$defs"][choices["items"]["$ref"].split("/")[-1]]["enum"]
            assert set(enum) == {tag["id"] for tag in sent["oracle_tags"]}
            return httpx.Response(
                200,
                json={
                    "id": "resp_test",
                    "status": "completed",
                    "model": "gpt-5.6-luna",
                    "service_tier": "default",
                    "usage": {"input_tokens": 10, "output_tokens": 10},
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "oracle_tag_ids": [str(PARENT)],
                                            "printed_keywords": [],
                                            "queries": [
                                                {
                                                    "purpose": "Selected source criteria",
                                                    "groups": [
                                                        {
                                                            "oracle_tag_indices": [0],
                                                            "printed_keyword_indices": [],
                                                        }
                                                    ],
                                                    "card_types_any": [],
                                                }
                                            ],
                                        }
                                    ),
                                }
                            ],
                        }
                    ],
                },
            )

    transport = Transport()
    monkeypatch.setattr(
        provider,
        "AsyncOpenAI",
        lambda **kwargs: __import__("openai").AsyncOpenAI(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport.handle))
        ),
    )
    saved = await client.put(
        path(discover_deck) + "/strategy",
        json={"prose": "Artifacts", "queries": []},
    )
    revision = saved.json()["data"]["revision"]
    started = await client.post(
        path(discover_deck) + "/term-suggestions",
        json={
            "request_key": "10000000-0000-0000-0000-000000000001",
            "prose": "Artifacts",
            "strategy_revision": revision,
        },
    )
    assert started.status_code == 202
    run_id = started.json()["data"]["id"]
    completed = await client.get(path(discover_deck) + f"/term-suggestions/{run_id}")
    assert completed.json()["data"]["queries"] == [search_query(tags=[PARENT])]
    assert (
        await db_pool.fetchval("SELECT profile FROM recommendation_runs WHERE id=$1", UUID(run_id))
        == budget.BOUNDED_TERMS_VERSION
    )
    assert transport.calls == 1
    replay = await client.post(
        path(discover_deck) + "/term-suggestions",
        json={
            "request_key": str(uuid4()),
            "prose": "Artifacts",
            "strategy_revision": revision,
            "reuse_latest": True,
        },
    )
    assert replay.json()["data"]["id"] == run_id and transport.calls == 1
    recovered = (await client.get(path(discover_deck) + "/setup")).json()["data"]
    assert recovered["prose"] == "Artifacts"
    assert recovered["suggestion"]["queries"] == [search_query(tags=[PARENT])]
    unchanged = await db_pool.fetchrow(
        "SELECT * FROM discover_strategies WHERE deck_id=$1", UUID(discover_deck)
    )
    assert unchanged and json.loads(unchanged["queries"]) == []
    changed = await client.put(
        path(discover_deck) + "/strategy",
        json={
            "prose": "New intent",
            "revision": revision,
        },
    )
    assert changed.status_code == 200
    stale = (await client.get(path(discover_deck) + f"/term-suggestions/{run_id}")).json()["data"]
    assert stale["status"] == "interrupted" and stale["queries"] == []
    assert (await client.get(path(discover_deck) + "/setup")).json()["data"]["suggestion"] is None
    assert (await client.get(path(discover_deck) + f"/runs/{run_id}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["tag_budget", "unknown_tag", "missing_index"])
async def test_invalid_bounded_selection_keeps_receipt_and_saved_strategy_without_retry(
    client: AsyncClient,
    discover_deck: str,
    db_pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    calls = []
    raw = {
        "oracle_tag_ids": [str(PARENT)],
        "printed_keywords": [],
        "queries": [
            {
                "purpose": "Proposed search",
                "groups": [{"oracle_tag_indices": [0], "printed_keyword_indices": []}],
                "card_types_any": [],
            }
        ],
    }
    if failure == "tag_budget":
        raw["oracle_tag_ids"] *= 13
    elif failure == "unknown_tag":
        raw["oracle_tag_ids"] = [str(UUID(int=9))]
    else:
        raw["queries"][0]["groups"][0]["oracle_tag_indices"] = [1]

    async def respond(self, frozen):
        calls.append(frozen)
        return {
            "status": "completed",
            "model": budget.MODEL,
            "service_tier": "default",
            "usage": {"input_tokens": 10, "output_tokens": 10},
            "output": json.dumps(raw),
        }

    monkeypatch.setattr(provider.Provider, "request", respond)
    before = (
        await client.put(
            path(discover_deck) + "/strategy",
            json={
                "prose": "Keep my intent",
                "queries": [search_query(tags=[PARENT])],
            },
        )
    ).json()["data"]
    request = {
        "request_key": str(uuid4()),
        "prose": "Try different criteria",
        "strategy_revision": before["revision"],
    }
    started = await client.post(path(discover_deck) + "/term-suggestions", json=request)
    assert started.status_code == 202
    run_id = started.json()["data"]["id"]
    result = (await client.get(path(discover_deck) + f"/term-suggestions/{run_id}")).json()["data"]
    assert result["status"] == "failed" and result["queries"] == []
    after = (await client.get(path(discover_deck) + "/status")).json()["data"]["strategy"]
    assert after == before
    repeated = await client.post(path(discover_deck) + "/term-suggestions", json=request)
    assert repeated.json()["data"]["id"] == run_id and len(calls) == 1
    attempt = await db_pool.fetchrow(
        "SELECT receipt,cost_microusd FROM recommendation_attempts WHERE run_id=$1", UUID(run_id)
    )
    assert json.loads(attempt["receipt"])["output"] == json.dumps(raw)
    assert attempt["cost_microusd"] == budget.cost(10, 10)
    assert (
        await db_pool.fetchval(
            "SELECT held_microusd FROM recommendation_runs WHERE id=$1", UUID(run_id)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_ac06_stale_results_warn_and_mismatch_is_not_empty(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    await client.put(
        path(discover_deck) + "/strategy",
        json={"prose": "Artifacts", "queries": [search_query(tags=[PARENT])]},
    )
    await db_pool.execute("UPDATE new_card_catalog_state SET published_at=now()-interval '3 days'")
    stale = await client.get(path(discover_deck) + "/matches")
    assert stale.json()["data"]["status"] == "stale"
    assert stale.json()["data"]["cards"]
    await db_pool.execute("UPDATE scryfall_tag_state SET source_sha256=tag_sha256")
    unavailable = await client.get(path(discover_deck) + "/matches")
    assert unavailable.json()["data"]["status"] == "mismatched"
    assert unavailable.json()["data"]["cards"] == []


@pytest.mark.asyncio
async def test_ac07_plan_is_idempotent_and_never_mutates_physical_cards(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    await client.put(
        path(discover_deck) + "/strategy",
        json={"prose": "Artifacts", "queries": [search_query(tags=[PARENT])]},
    )
    oracle_id = (await client.get(path(discover_deck) + "/matches")).json()["data"]["cards"][0][
        "oracle_id"
    ]
    for _ in range(2):
        assert (
            await client.post(path(discover_deck) + f"/matches/{oracle_id}/plan")
        ).status_code == 200
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM deck_cards WHERE deck_id=$1", UUID(discover_deck)
        )
        == 0
    )
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM deck_card_plans WHERE deck_id=$1", UUID(discover_deck)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_ac08_second_account_cannot_read_owner_strategy(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    await client.put(
        path(discover_deck) + "/strategy",
        json={"prose": "Artifacts", "queries": [search_query(tags=[PARENT])]},
    )
    other = UUID(await create_test_account(client, "Other Discover Owner"))
    await feature_flag_service.set_flag(db_pool, "recommendations", True, other)
    assert (await client.get(path(discover_deck) + "/status")).status_code == 404
    assert (await client.get(path(discover_deck) + "/setup")).status_code == 404


@pytest.mark.asyncio
async def test_ac09_schema_upgrade_twice_preserves_strategy_and_legacy_accounting(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    from mtg_helper.db import apply_schema

    saved = await client.put(
        path(discover_deck) + "/strategy",
        json={"prose": "Artifacts", "queries": [search_query(tags=[PARENT])]},
    )
    before = saved.json()["data"]
    await db_pool.execute(
        "INSERT INTO recommendation_runs (id,account_id,deck_id,request_key,request_hash, "
        "source_hash,rules_hash,profile,context,token,held_microusd) "
        "SELECT gen_random_uuid(), id, $1, gen_random_uuid(), 'history', source_sha256, "
        "source_sha256, 'legacy-history', '{}', gen_random_uuid(), 0 "
        "FROM accounts, new_card_catalog_state WHERE email='default@test.local'",
        UUID(discover_deck),
    )
    await apply_schema(db_pool)
    await apply_schema(db_pool)
    after = (await client.get(path(discover_deck) + "/status")).json()["data"]["strategy"]
    assert after["prose"] == before["prose"]
    assert await db_pool.fetchval("SELECT count(*) FROM recommendation_runs") == 1


@pytest.mark.no_db
def test_ac03_explicit_setup_actions_remain_separate_from_local_match_routes() -> None:
    from mtg_helper.main import app

    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert "/api/v1/decks/{deck_id}/recommendations/strategy-drafts" in paths
    assert "/api/v1/decks/{deck_id}/recommendations/matches" in paths


@pytest.mark.no_db
def test_ac03_term_suggestions_reject_invented_source_terms() -> None:
    from mtg_helper.services.recommendations.term_queries import Workflow

    workflow = Workflow(
        context={
            "prose": "tokens",
            "strategy_revision": None,
            "source_hash": "source",
            "oracle_tags": [{"id": str(PARENT), "label": "Parent"}],
            "printed_keywords": ["Flying"],
            "commanders": [],
        }
    )
    with pytest.raises(ValueError, match="outside the Scryfall catalog"):
        workflow.accept(
            "plan",
            json.dumps({"queries": [search_query(tags=[UUID(int=9)])]}),
            {},
        )


@pytest.mark.no_db
def test_ac03_term_request_schema_requires_every_selection_field() -> None:
    from mtg_helper.services.recommendations import budget, pipeline
    from mtg_helper.services.recommendations.service import request_payload

    payload = {"strategy": "Counters", "oracle_tags": [], "printed_keywords": []}
    fixed = pipeline.check_request("plan", payload, profile=budget.TERMS_VERSION)
    frozen = request_payload("plan", payload, fixed)
    schema = frozen["text"]["format"]["schema"]
    assert set(schema.get("required", [])) == set(schema["properties"])
    assert schema["additionalProperties"] is False


@pytest.mark.asyncio
async def test_ac12_community_picks_use_their_existing_caches_not_saved_discover_terms(
    client: AsyncClient, discover_deck: str, db_pool: asyncpg.Pool
) -> None:
    commander = await db_pool.fetchval(
        "SELECT commander_id FROM decks WHERE id=$1", UUID(discover_deck)
    )
    mox = {"by_oracle": {str(SOL_RING_ORACLE_ID): 1}, "decks": [{"id": "fixture"}], "curve": None}
    arch = {
        "version": 1,
        "by_name": {"sol ring": 1},
        "sample_size": 1,
        "decks": [{"id": "fixture"}],
    }
    await db_pool.execute(
        "INSERT INTO moxfield_commander_recs (commander_id,payload,fetched_at) "
        "VALUES ($1,$2::jsonb,now())",
        commander,
        json.dumps(mox),
    )
    await db_pool.execute(
        "INSERT INTO archidekt_commander_recs (commander_id,payload,fetched_at) "
        "VALUES ($1,$2::jsonb,now())",
        commander,
        json.dumps(arch),
    )
    result = await client.get(f"/api/v1/decks/{discover_deck}/top-picks")
    assert result.status_code == 200
    assert result.json()["data"]["picks"][0]["oracle_id"] == str(SOL_RING_ORACLE_ID)
