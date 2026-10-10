"""Real PostgreSQL/API/SDK strategy drafts; only external provider HTTP is replaced."""

import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from mtg_helper.models.recommendations import GenerateRequest, StrategyDraftRequest
from mtg_helper.services import feature_flag_service
from mtg_helper.services.recommendations import budget, pipeline, strategy
from mtg_helper.services.recommendations.repository import DiscoveryError
from mtg_helper.services.recommendations.service import request_payload
from tests import test_recommendation_pilot
from tests.conftest import create_test_account
from tests.test_recommendation_pilot import path, request

pilot = test_recommendation_pilot.pilot
pytestmark = pytest.mark.asyncio


def draft_request():
    return {"request_key": str(uuid4())}


async def test_draft_is_one_checkpointed_call_and_keeps_card_results_and_deck_unchanged(
    pilot, client, db_pool
):
    deck, owner, service, transport = pilot
    cards = await client.post(path(deck) + "/runs", json=request())
    cards_id = cards.json()["data"]["id"]
    before = await db_pool.fetchval("SELECT description FROM decks WHERE id = $1", deck)
    body = draft_request()
    started = await client.post(path(deck) + "/strategy-drafts", json=body)
    assert started.status_code == 202
    draft_id = started.json()["data"]["id"]
    draft = (await client.get(path(deck) + f"/runs/{draft_id}")).json()["data"]
    assert draft["profile"] == budget.STRATEGY_VERSION and draft["status"] == "completed"
    assert len(draft["strategies"]) == 3 and not draft["candidates"]
    assert draft["strategies"][0]["title"] == transport.strategy_title
    assert draft["strategies"][0]["early_game"] in draft["strategies"][0]["goal"]
    assert draft["known_cost_microusd"] == 145 and draft["held_microusd"] == 0
    assert len(transport.calls) == 4
    emitted = transport.calls[-1]
    assert emitted["max_output_tokens"] == 4000 and emitted["store"] is False
    assert set(json.loads(emitted["input"])) == {"commander"}
    status = (await client.get(path(deck) + "/status")).json()["data"]
    assert status["run"]["id"] == cards_id and status["strategy_run"]["id"] == draft["id"]
    assert status["strategy_cap_microusd"] == 10_000
    assert status["strategy_reserved_microusd"] == 9_800
    assert status["strategy_maximum_calls"] == 1
    repeated = await client.post(path(deck) + "/strategy-drafts", json=body)
    assert repeated.json()["data"]["id"] == draft["id"] and len(transport.calls) == 4
    trace = await service.trace(owner, deck, UUID(draft["id"]))
    assert trace["profile"] == budget.STRATEGY_VERSION and len(trace["attempts"]) == 1
    assert await db_pool.fetchval("SELECT description FROM decks WHERE id = $1", deck) == before
    assert await db_pool.fetchval("SELECT count(*) FROM deck_cards") == 0
    assert await db_pool.fetchval("SELECT count(*) FROM deck_card_plans") == 0
    assert await db_pool.fetchval("SELECT count(*) FROM recommendation_feedback") == 0


async def test_draft_can_guide_a_later_explicit_edited_goal_but_not_authorize_card_advice(
    pilot, client, db_pool
):
    deck, _, _, transport = pilot
    body = draft_request()
    started = await client.post(path(deck) + "/strategy-drafts", json=body)
    draft_id = started.json()["data"]["id"]
    assert len(transport.calls) == 1
    cross_profile = await client.post(
        path(deck) + "/runs",
        json={
            **body,
            "goal": "Draft a commander-only strategy",
        },
    )
    assert cross_profile.status_code == 409 and len(transport.calls) == 1
    oracle_id = await db_pool.fetchval("SELECT oracle_id FROM cards WHERE name = 'Sol Ring'")
    forbidden = await client.post(path(deck) + f"/runs/{draft_id}/candidates/{oracle_id}/plan")
    assert forbidden.status_code == 409
    draft = (await client.get(path(deck) + f"/runs/{draft_id}")).json()["data"]
    selected = draft["strategies"][1]
    edited = selected["goal"] + "\nPrefer a faster start."
    generated = await client.post(path(deck) + "/runs", json=request() | {"goal": edited})
    assert generated.status_code == 202 and len(transport.calls) == 4
    assert json.loads(transport.calls[1]["input"])["strategy"] == edited
    assert (await client.get(path(deck) + "/status")).json()["data"]["strategy_run"][
        "id"
    ] == draft_id


async def test_invalid_draft_stops_after_one_known_call_without_overwriting_goal_or_repair(
    pilot, client
):
    deck, _, _, transport = pilot
    transport.strategy_title = " "
    body = draft_request()
    started = await client.post(path(deck) + "/strategy-drafts", json=body)
    draft_id = started.json()["data"]["id"]
    result = (await client.get(path(deck) + f"/runs/{draft_id}")).json()["data"]
    assert result["status"] == "failed" and result["strategies"] == []
    assert result["known_cost_microusd"] == 145 and result["held_microusd"] == 0
    assert len(transport.calls) == 1
    await client.post(path(deck) + "/strategy-drafts", json=body)
    assert len(transport.calls) == 1


async def test_both_profiles_share_active_account_claim_and_profile_fences(pilot, db_pool):
    deck, owner, service, transport = pilot
    run_id, work = await service.draft_strategy(
        owner, deck, StrategyDraftRequest(**draft_request())
    )
    assert work is not None
    assert (
        await db_pool.fetchval(
            "SELECT held_microusd FROM recommendation_runs WHERE id = $1", run_id
        )
        == 9_800
    )
    with pytest.raises(DiscoveryError, match="already active"):
        await service.generate(owner, deck, GenerateRequest(**request()))
    assert not await service.runs.checkpoint(replace(work, profile=budget.VERSION), "plan", {})
    assert transport.calls == []
    await service.run(work)
    await service.run(work)
    assert len(transport.calls) == 1


async def test_expired_draft_keeps_unknown_hold_and_settles_a_late_receipt_once(pilot, db_pool):
    deck, owner, service, transport = pilot
    run_id, work = await service.draft_strategy(
        owner, deck, StrategyDraftRequest(**draft_request())
    )
    payload = strategy.Workflow(context=work.context).payload("plan", {})
    fixed = pipeline.check_request("plan", payload, profile=work.profile)
    frozen = request_payload("plan", payload, fixed)
    assert await service.runs.checkpoint(work, "plan", frozen)
    await db_pool.execute(
        "UPDATE recommendation_runs SET lease_until = now() - interval '1 minute' WHERE id = $1",
        run_id,
    )
    await service.runs.expire(owner)
    await service.run(work)
    assert transport.calls == []
    assert (
        await db_pool.fetchval(
            "SELECT held_microusd FROM recommendation_runs WHERE id = $1", run_id
        )
        == 9_800
    )
    with pytest.raises(DiscoveryError, match="billing hold"):
        await service.draft_strategy(owner, deck, StrategyDraftRequest(**draft_request()))
    receipt = {
        "model": budget.MODEL,
        "service_tier": "default",
        "usage": {"input_tokens": 100, "output_tokens": 100},
    }
    price = budget.usage_cost(receipt, budget.bounds(work.profile)["plan"])
    await service.runs.receipt(work, "plan", receipt, price)
    await service.runs.receipt(work, "plan", receipt, price)
    row = await db_pool.fetchrow("SELECT * FROM recommendation_runs WHERE id = $1", run_id)
    assert row["held_microusd"] == 0 and row["known_cost_microusd"] == 145
    assert row["status"] == "interrupted"
    assert not await service.runs.publish(work, "plan", {"strategies": []})


async def test_draft_and_cards_consume_the_same_daily_spending_allowance(pilot, client, db_pool):
    deck, _, _, transport = pilot
    await client.post(path(deck) + "/strategy-drafts", json=draft_request())
    await db_pool.execute(
        "UPDATE recommendation_attempts SET cost_microusd = $1",
        budget.DAILY_CAP - budget.reservation(budget.STRATEGY_VERSION) + 1,
    )
    for endpoint, body in (("strategy-drafts", draft_request()), ("runs", request())):
        response = await client.post(path(deck) + f"/{endpoint}", json=body)
        assert response.status_code == 429
    assert len(transport.calls) == 1


async def test_draft_start_requires_capability_ownership_and_exact_request_contract(pilot, client):
    deck, owner, service, transport = pilot
    await feature_flag_service.set_flag(service.pool, "recommendations", False, owner.account_id)
    assert (
        await client.post(path(deck) + "/strategy-drafts", json=draft_request())
    ).status_code == 404
    await feature_flag_service.set_flag(service.pool, "recommendations", True, owner.account_id)
    invalid = await client.post(
        path(deck) + "/strategy-drafts", json=draft_request() | {"goal": "X"}
    )
    assert invalid.status_code == 422
    other = UUID(await create_test_account(client, "Other"))
    await feature_flag_service.set_flag(service.pool, "recommendations", True, other)
    assert (
        await client.post(path(deck) + "/strategy-drafts", json=draft_request())
    ).status_code == 404
    assert transport.calls == []


async def test_archived_single_draft_stays_strategy_history_without_repricing_or_reuse(
    pilot, client, db_pool
):
    deck, owner, service, transport = pilot
    cards = await client.post(path(deck) + "/runs", json=request())
    cards_id = cards.json()["data"]["id"]
    body = draft_request()
    started = await client.post(path(deck) + "/strategy-drafts", json=body)
    run_id = UUID(started.json()["data"]["id"])
    original = {
        "strategy_draft": {"goal": "Archived goal", "explanation": "Old", "uncertainties": []}
    }
    await db_pool.execute(
        "UPDATE recommendation_runs SET profile = 'app-strategy-v1', data = $2::jsonb "
        "WHERE id = $1",
        run_id,
        json.dumps(original),
    )
    status = (await client.get(path(deck) + "/status")).json()["data"]
    assert status["run"]["id"] == cards_id
    assert status["strategy_run"]["id"] == str(run_id)
    assert status["strategy_run"]["stale"] and status["strategy_run"]["strategies"] == []
    trace = await service.trace(owner, deck, run_id)
    assert trace["data"] == original and trace["profile"] == "app-strategy-v1"
    assert trace["attempts"][0]["cost_microusd"] == 145
    assert (await client.post(path(deck) + "/strategy-drafts", json=body)).status_code == 409
    assert len(transport.calls) == 4
    await db_pool.execute(
        "UPDATE recommendation_runs SET held_microusd = 7400, status = 'unknown' WHERE id = $1",
        run_id,
    )
    assert (
        await client.post(path(deck) + "/strategy-drafts", json=draft_request())
    ).status_code == 409
    assert (await client.post(path(deck) + "/runs", json=request())).status_code == 409
    assert len(transport.calls) == 4
