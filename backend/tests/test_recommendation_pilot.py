"""Real PostgreSQL, API and SDK workflows; only external HTTP is replaced."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from openai import AsyncOpenAI

from mtg_helper.services import feature_flag_service
from mtg_helper.services.new_cards import catalog
from mtg_helper.services.new_cards.discovery import release_history
from mtg_helper.services.recommendations import budget, provider
from mtg_helper.services.recommendations.repository import Owner
from mtg_helper.services.recommendations.service import DiscoveryService
from mtg_helper.services.recommendations.source_repository import SourceRepository
from tests.conftest import create_test_account, create_test_deck

pytestmark = pytest.mark.asyncio


class Transport:
    def __init__(self, pool):
        self.pool = pool
        self.calls = []
        self.status = 200
        self.bad_quote = False
        self.strategy_goal = "Build around the commander's printed abilities."

    async def handle(self, request):
        body = json.loads(request.content)
        saved = await self.pool.fetchrow(
            "SELECT request, status FROM recommendation_attempts ORDER BY attempted_at DESC LIMIT 1"
        )
        assert saved["status"] == "attempted"
        assert json.loads(saved["request"]) == body
        self.calls.append(body)
        payload = json.loads(body["input"])
        if "goal" in body["text"]["format"]["schema"]["properties"]:
            output = {
                "goal": self.strategy_goal,
                "explanation": "A commander-only proposed direction, not existing-deck analysis.",
                "uncertainties": ["Unverified advice"],
            }
        elif "candidates" in payload:
            rows = {}
            for index, card in enumerate(payload["candidates"]):
                text = card["oracle_text"]
                rows[card["key"]] = {
                    "fit": "support",
                    "reason": "Proposed commander-only support, not present cards",
                    "caveat": "Unverified",
                    "evidence": [
                        {
                            "key": card["key"],
                            "quote": "Invented quotation."
                            if self.bad_quote and index
                            else text[:160],
                        }
                    ],
                }
            output = {"recommendations": list(rows), "assessments": rows}
        else:
            output = {
                "intents": ["Commander infrastructure"],
                "searches": [],
                "named_cards": ["Sol Ring", "Doubling Season"],
                "uncertainties": [],
                "rule_searches": [],
            }
        return httpx.Response(
            self.status,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": body["model"],
                "service_tier": "default",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 100,
                    "total_tokens": 200,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
                "output": [
                    {
                        "type": "message",
                        "id": "msg_test",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": json.dumps(output), "annotations": []}
                        ],
                    }
                ],
            },
        )


@pytest_asyncio.fixture
async def pilot(client, db_pool, monkeypatch):
    deck = UUID(await create_test_deck(client))
    account = await db_pool.fetchrow("SELECT * FROM accounts WHERE email = 'default@test.local'")
    owner = Owner(account["id"], account["email"])
    transport = Transport(db_pool)
    monkeypatch.setattr(
        provider,
        "AsyncOpenAI",
        lambda **kwargs: AsyncOpenAI(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport.handle))
        ),
    )
    rows = await db_pool.fetch("SELECT * FROM cards")
    sources = [
        dict(row)
        | {
            "oracle_id": str(row["oracle_id"]),
            "legalities": json.loads(row["legalities"]),
            "games": ["paper"],
            "set_type": "expansion",
            "released_at": "2025-01-01",
            "reprint": False,
        }
        for row in rows
    ]
    async with db_pool.acquire() as conn, conn.transaction():
        await catalog.publish(conn, sources, release_history(sources), datetime.now(UTC))
    await feature_flag_service.set_flag(db_pool, "recommendations", True, owner.account_id)
    service = DiscoveryService(db_pool, SourceRepository(db_pool), provider.Provider("test"))
    yield deck, owner, service, transport
    for row in rows:
        await db_pool.execute(
            "UPDATE cards SET legalities = $2::jsonb WHERE id = $1", row["id"], row["legalities"]
        )


def path(deck):
    return f"/api/v1/decks/{deck}/recommendations"


def request():
    return {"request_key": str(uuid4()), "goal": "Commander-only infrastructure"}


async def test_disabled_backend_and_unowned_deck_are_not_accessible(client, db_pool):
    deck = await create_test_deck(client)
    response = await client.get(path(deck) + "/status")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DISCOVERY_ERROR"
    other = UUID(await create_test_account(client, "Other"))
    await feature_flag_service.set_flag(db_pool, "recommendations", True, other)
    assert (await client.get(path(deck) + "/status")).status_code == 404


async def test_three_checkpointed_calls_are_real_discoveries_and_reads_are_free(pilot, client):
    deck, owner, service, transport = pilot
    assert (await client.get(path(deck) + "/status")).json()["data"]["ready"]
    browse = await client.post(path(deck) + "/preview-query", json={})
    assert browse.status_code == 200 and len(browse.json()["data"]["cards"]) == 2
    assert transport.calls == []
    body = request()
    started = await client.post(path(deck) + "/runs", json=body)
    assert started.status_code == 202
    run_id = started.json()["data"]["id"]
    view = (await client.get(path(deck) + f"/runs/{run_id}")).json()["data"]
    assert view["status"] == "completed" and view["known_cost_microusd"] == 435
    assert view["held_microusd"] == 0 and len(view["candidates"]) == 2
    assert all(c["recommended"] for c in view["candidates"])
    assert len(transport.calls) == 3
    for emitted in transport.calls:
        payload = json.loads(emitted["input"])
        assert not {"physical", "planned", "diagnostics", "community"} & payload.keys()
        assert emitted["store"] is False and emitted["service_tier"] == "default"
    duplicate = await client.post(path(deck) + "/runs", json=body)
    assert duplicate.json()["data"]["id"] == run_id and len(transport.calls) == 3
    mismatch = await client.post(path(deck) + "/runs", json=body | {"goal": "Different"})
    assert mismatch.status_code == 409
    trace = await service.trace(owner, deck, UUID(run_id))
    assert len(trace["attempts"]) == 3 and "revise_observation" in trace["data"]


async def test_quote_failure_keeps_neighbor_and_feedback_does_not_touch_legacy(
    pilot, client, db_pool
):
    deck, _, _, transport = pilot
    transport.bad_quote = True
    start = await client.post(path(deck) + "/runs", json=request())
    run_id = start.json()["data"]["id"]
    result = (await client.get(path(deck) + f"/runs/{run_id}")).json()["data"]
    assert [c["state"] for c in result["candidates"]] == ["assessed", "failed"]
    good = result["candidates"][0]["oracle_id"]
    bad = result["candidates"][1]["oracle_id"]
    endpoint = path(deck) + f"/runs/{run_id}/candidates/"
    assert (await client.post(endpoint + bad + "/plan")).status_code == 409
    assert (await client.post(endpoint + good + "/plan")).status_code == 200
    assert (await client.post(endpoint + good + "/plan")).status_code == 200
    assert await db_pool.fetchval("SELECT count(*) FROM deck_cards") == 0
    assert await db_pool.fetchval("SELECT count(*) FROM deck_card_plans") == 1
    assert await db_pool.fetchval("SELECT recommendation_origin FROM deck_card_plans")
    response = await client.post(
        path(deck) + f"/runs/{run_id}/feedback",
        json={"oracle_id": good, "verdict": "useful", "note": "Test"},
    )
    assert response.status_code == 200
    assert await db_pool.fetchval("SELECT count(*) FROM recommendation_feedback") == 1
    assert await db_pool.fetchval("SELECT count(*) FROM deck_feedback") == 0


@pytest.mark.parametrize(("endpoint", "held"), [("runs", 11_000), ("strategy-drafts", 7_400)])
async def test_unknown_billing_blocks_new_runs_and_is_never_retried(
    pilot, client, db_pool, endpoint, held
):
    deck, _, _, transport = pilot
    transport.status = 500
    body = request() if endpoint == "runs" else {"request_key": str(uuid4())}
    start = await client.post(path(deck) + f"/{endpoint}", json=body)
    run_id = start.json()["data"]["id"]
    result = (await client.get(path(deck) + f"/runs/{run_id}")).json()["data"]
    assert result["status"] == "unknown" and result["held_microusd"] == held
    assert len(transport.calls) == 1
    await db_pool.execute("UPDATE recommendation_runs SET created_at = now() - interval '2 days'")
    await db_pool.execute(
        "UPDATE recommendation_attempts SET settled_at = now() - interval '2 days'"
    )
    blocked = await client.post(path(deck) + "/runs", json=request())
    assert blocked.status_code == 409 and len(transport.calls) == 1
    draft = await client.post(path(deck) + "/strategy-drafts", json={"request_key": str(uuid4())})
    assert draft.status_code == 409 and len(transport.calls) == 1
    assert await db_pool.fetchval("SELECT count(*) FROM recommendation_attempts") == 1


async def test_expired_and_duplicate_workers_cannot_send_a_paid_request(pilot, db_pool):
    deck, owner, service, transport = pilot
    from mtg_helper.models.recommendations import GenerateRequest

    run_id, work = await service.generate(owner, deck, GenerateRequest.model_validate(request()))
    assert work
    await db_pool.execute(
        "UPDATE recommendation_runs SET lease_until = now() - interval '1 second'"
    )
    await service.run(work)
    assert transport.calls == []
    result = await service.view(owner, deck, run_id)
    assert result.status == "interrupted" and result.held_microusd == 0
    _, new_work = await service.generate(owner, deck, GenerateRequest.model_validate(request()))
    assert new_work
    await asyncio.gather(service.run(new_work), service.run(new_work))
    assert len(transport.calls) == 3
    assert await db_pool.fetchval("SELECT count(*) FROM recommendation_attempts") == 3


async def test_completion_rechecks_legality_and_preserves_whole_revision(pilot, client, db_pool):
    deck, _, _, _ = pilot
    start = await client.post(path(deck) + "/runs", json=request())
    run_id = start.json()["data"]["id"]
    result = (await client.get(path(deck) + f"/runs/{run_id}")).json()["data"]
    card_id = result["candidates"][0]["oracle_id"]
    await client.post(path(deck) + f"/runs/{run_id}/candidates/{card_id}/plan")
    plan_id = await db_pool.fetchval("SELECT id FROM deck_card_plans")
    await db_pool.execute(
        'UPDATE cards SET legalities = \'{"commander":"banned"}\' WHERE oracle_id = $1',
        UUID(card_id),
    )
    response = await client.post(
        f"/api/v1/decks/{deck}/planned-changes/{plan_id}/complete", json={"quantity": 1}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PLAN"
    assert await db_pool.fetchval("SELECT count(*) FROM deck_cards") == 0
    assert await db_pool.fetchval("SELECT count(*) FROM deck_card_plans") == 1


async def test_daily_ceiling_checks_settled_spend_and_persists_after_deck_deletion(
    pilot, client, db_pool
):
    deck, _, _, transport = pilot
    await client.post(path(deck) + "/runs", json=request())
    await db_pool.execute(
        "UPDATE recommendation_attempts SET cost_microusd = $1 WHERE phase = 'plan'",
        budget.DAILY_CAP,
    )
    assert (await client.post(path(deck) + "/runs", json=request())).status_code == 429
    assert (await client.delete(f"/api/v1/decks/{deck}")).status_code == 204
    assert await db_pool.fetchval("SELECT count(*) FROM recommendation_attempts") == 3
    fresh_deck = await create_test_deck(client)
    assert (await client.post(path(fresh_deck) + "/runs", json=request())).status_code == 429
    assert len(transport.calls) == 3


async def test_new_publication_and_worker_restart_preserve_old_run_sources(pilot, db_pool):
    from mtg_helper.models.recommendations import GenerateRequest, QueryPreview

    deck, owner, service, transport = pilot
    run_id, work = await service.generate(owner, deck, GenerateRequest.model_validate(request()))
    old = await service.sources.load(work.source_hash, work.rules_hash)
    original = old.cards[next(iter(old.cards))]["name"]
    raw = list(old.cards.values())
    raw = [c | {"oracle_text": "Changed authoritative source text."} for c in raw]
    async with db_pool.acquire() as conn, conn.transaction():
        await catalog.publish(conn, raw, {}, datetime.now(UTC))
    restarted = SourceRepository(db_pool)
    retained = await restarted.load(work.source_hash, work.rules_hash)
    assert retained.cards[next(iter(retained.cards))]["name"] == original
    await service.run(work)
    result = await service.view(owner, deck, run_id)
    assert result.status == "completed" and result.stale and len(transport.calls) == 3
    old_page = await service.preview(owner, deck, QueryPreview(snapshot_hash=work.source_hash))
    assert old_page.snapshot_hash == work.source_hash


async def test_card_continuation_survives_a_reviewed_rules_update(
    pilot, db_pool, monkeypatch, tmp_path
):
    import hashlib

    from mtg_helper.models.recommendations import QueryPreview
    from mtg_helper.services.recommendations import snapshots, source_repository

    deck, owner, service, _ = pilot
    first = await service.preview(owner, deck, QueryPreview(limit=1))
    old = await service.sources.load(first.snapshot_hash, first.rules_hash)
    raw = b"123.1. New complete source rules entry.\n"
    path = tmp_path / "rules.txt"
    path.write_bytes(raw)
    monkeypatch.setattr(snapshots, "RULES_PATH", path)
    monkeypatch.setattr(snapshots, "RULES_HASH", hashlib.sha256(raw).hexdigest())
    source_repository.rules_resource.cache_clear()
    try:
        prepared = source_repository.prepare(list(old.cards.values()))
        async with db_pool.acquire() as conn, conn.transaction():
            await source_repository.publish(conn, prepared)
        assert (await service.sources.current())[1] != first.rules_hash
        continuation = QueryPreview(
            limit=1,
            cursor=first.next_cursor,
            snapshot_hash=first.snapshot_hash,
            rules_hash=first.rules_hash,
        )
        second = await service.preview(owner, deck, continuation)
        assert second.cards[0].oracle_id != first.cards[0].oracle_id
        assert second.rules_hash == first.rules_hash
    finally:
        source_repository.rules_resource.cache_clear()


async def test_attempted_crash_holds_cost_and_late_receipt_settles_once(pilot, db_pool):
    from mtg_helper.models.recommendations import GenerateRequest

    deck, owner, service, transport = pilot
    run_id, work = await service.generate(owner, deck, GenerateRequest.model_validate(request()))
    assert await service.runs.checkpoint(work, "plan", {})
    assert not await service.runs.checkpoint(work, "plan", {})
    await db_pool.execute(
        "UPDATE recommendation_runs SET lease_until = now() - interval '1 second'"
    )
    result = await service.view(owner, deck, run_id)
    assert result.status == "interrupted" and result.held_microusd == 11_000
    for _ in range(2):
        await service.runs.receipt(work, "plan", {"late": True}, 145)
    settled = await service.view(owner, deck, run_id)
    assert settled.known_cost_microusd == 145 and settled.held_microusd == 0
    assert settled.status == "interrupted" and transport.calls == []


async def test_all_run_reads_and_actions_recheck_ownership(pilot, client, db_pool):
    deck, _, _, transport = pilot
    start = await client.post(path(deck) + "/runs", json=request())
    run_id = start.json()["data"]["id"]
    oracle_id = (await client.get(path(deck) + f"/runs/{run_id}")).json()["data"]["candidates"][0][
        "oracle_id"
    ]
    other = UUID(await create_test_account(client, "Other Owner"))
    await feature_flag_service.set_flag(db_pool, "recommendations", True, other)
    for suffix in (f"/runs/{run_id}", f"/runs/{run_id}/trace"):
        assert (await client.get(path(deck) + suffix)).status_code == 404
    for suffix, body in [
        ("/preview-query", {}),
        ("/runs", request()),
        (f"/runs/{run_id}/candidates/{oracle_id}/plan", {}),
        (f"/candidates/{oracle_id}/plan", {}),
        (f"/runs/{run_id}/feedback", {"oracle_id": oracle_id, "verdict": "useful"}),
    ]:
        assert (await client.post(path(deck) + suffix, json=body)).status_code == 404
    assert len(transport.calls) == 3


async def test_manual_browsing_plan_and_successful_completion_require_no_ai(pilot, client, db_pool):
    deck, _, _, transport = pilot
    oracle = await db_pool.fetchval("SELECT oracle_id FROM cards WHERE name = 'Sol Ring'")
    result = await client.post(path(deck) + f"/candidates/{oracle}/plan")
    assert result.status_code == 200
    plan_id = await db_pool.fetchval("SELECT id FROM deck_card_plans")
    result = await client.post(
        f"/api/v1/decks/{deck}/planned-changes/{plan_id}/complete", json={"quantity": 1}
    )
    assert result.status_code == 200
    assert await db_pool.fetchval("SELECT count(*) FROM deck_cards") == 1
    assert await db_pool.fetchval("SELECT count(*) FROM deck_card_plans") == 0
    assert transport.calls == []


async def test_origin_survives_manual_merge_repair_partial_and_batch_completion(
    pilot, client, db_pool
):
    from mtg_helper.services import oracle_duplicate_repair_service, revision_service
    from mtg_helper.services.recommendations.planning import Planner
    from mtg_helper.services.revision_service import RevisionCommand

    deck, owner, service, transport = pilot
    printing, oracle = uuid4(), uuid4()
    text = "A deck can have any number of cards named Fixture Swarm."
    card_id = await db_pool.fetchval(
        "INSERT INTO cards (scryfall_id,oracle_id,name,type_line,oracle_text,"
        "color_identity,legalities,is_canonical) VALUES ($1,$2,'Fixture Swarm','Artifact',"
        "$3,'{}','{\"commander\":\"legal\"}',true) RETURNING id",
        printing,
        oracle,
        text,
    )
    hashes = await service.sources.current()
    old = await service.sources.load(*hashes)
    raw = {
        "oracle_id": str(oracle),
        "name": "Fixture Swarm",
        "type_line": "Artifact",
        "oracle_text": text,
        "color_identity": [],
        "games": ["paper"],
        "legalities": {"commander": "legal"},
    }
    async with db_pool.acquire() as conn, conn.transaction():
        await catalog.publish(conn, [*old.cards.values(), raw], {}, datetime.now(UTC))
    await Planner(db_pool).plan(owner, deck, oracle)
    response = await client.post(
        f"/api/v1/decks/{deck}/planned-changes",
        json={"card_scryfall_id": str(printing), "direction": "addition", "quantity": 1},
    )
    assert response.status_code == 201
    alias = await db_pool.fetchval(
        "INSERT INTO cards (scryfall_id,oracle_id,name,type_line,oracle_text,color_identity,"
        "legalities,is_canonical) VALUES ($1,$2,'Fixture Swarm','Artifact',$3,'{}',"
        '\'{"commander":"legal"}\',false) RETURNING id',
        uuid4(),
        oracle,
        text,
    )
    await db_pool.execute(
        "INSERT INTO deck_card_plans (deck_id,card_id,direction,quantity) "
        "VALUES ($1,$2,'addition',1)",
        deck,
        alias,
    )
    await oracle_duplicate_repair_service.repair_active_decks(db_pool)
    plan = await db_pool.fetchrow("SELECT * FROM deck_card_plans WHERE card_id = $1", card_id)
    assert plan["recommendation_origin"] and plan["quantity"] == 3
    response = await client.post(
        f"/api/v1/decks/{deck}/planned-changes/{plan['id']}/complete", json={"quantity": 1}
    )
    assert response.status_code == 200
    plan = await db_pool.fetchrow("SELECT * FROM deck_card_plans WHERE id = $1", plan["id"])
    assert plan["recommendation_origin"] and plan["quantity"] == 2
    await revision_service.apply_revision(
        db_pool,
        deck,
        RevisionCommand(plan_ids=[plan["id"]], title="Complete remaining Swarm"),
        owner.email,
        owner.account_id,
    )
    assert (
        await db_pool.fetchval("SELECT quantity FROM deck_cards WHERE card_id = $1", card_id) == 3
    )
    assert transport.calls == []


async def test_request_bounds_unsupported_scopes_and_active_cross_deck_conflict(pilot, client):
    from mtg_helper.models.recommendations import GenerateRequest

    deck, owner, service, transport = pilot
    assert (
        await client.post(path(deck) + "/runs", json=request() | {"goal": "x" * 1001})
    ).status_code == 422
    assert (
        await client.post(path(deck) + "/runs", json=request() | {"unsupported": True})
    ).status_code == 422
    _, work = await service.generate(owner, deck, GenerateRequest.model_validate(request()))
    second_deck = UUID(await create_test_deck(client, name="Second Deck"))
    assert (await client.post(path(second_deck) + "/runs", json=request())).status_code == 409
    assert transport.calls == [] and work
