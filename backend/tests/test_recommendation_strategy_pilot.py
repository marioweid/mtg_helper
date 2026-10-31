"""Real PostgreSQL/API/SDK strategy drafts; only external provider HTTP is replaced."""

import asyncio
import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from mtg_helper.models.recommendations import StrategyDraftRequest, TermSuggestionRequest
from mtg_helper.services import feature_flag_service
from mtg_helper.services.recommendations import budget, pipeline, strategy
from mtg_helper.services.recommendations.repository import DiscoveryError
from mtg_helper.services.recommendations.service import request_payload
from tests import test_recommendation_pilot
from tests.conftest import create_test_account
from tests.test_recommendation_pilot import archived_card_run, path, request

pilot = test_recommendation_pilot.pilot
pytestmark = pytest.mark.asyncio


def draft_request():
    return {"request_key": str(uuid4())}


async def test_setup_reuses_current_draft_across_mounts_and_restores_full_choices(pilot, client):
    deck, _, _, transport = pilot
    first, duplicate = await asyncio.gather(
        *[
            client.post(
                path(deck) + "/strategy-drafts", json=draft_request() | {"reuse_latest": True}
            )
            for _ in range(2)
        ]
    )
    assert first.status_code == 202, first.text
    assert duplicate.status_code == 202, duplicate.text
    assert duplicate.json()["data"]["id"] == first.json()["data"]["id"]
    restored = await client.get(path(deck) + "/setup")
    assert restored.status_code == 200
    assert restored.json()["data"]["draft"]["strategies"][0]["early_game"]
    assert restored.json()["data"]["suggestion"] is None
    assert len(transport.calls) == 1


async def test_setup_does_not_restore_drafts_for_changed_commander(pilot, client, db_pool):
    deck, _, _, _ = pilot
    await client.post(path(deck) + "/strategy-drafts", json=draft_request())
    other = await db_pool.fetchval("SELECT id FROM cards WHERE name='Rhystic Study'")
    await db_pool.execute("UPDATE decks SET partner_id=$2 WHERE id=$1", deck, other)
    restored = await client.get(path(deck) + "/setup")
    assert restored.status_code == 200
    assert restored.json()["data"]["draft"] is None


async def test_valid_strategy_is_usable_with_unknown_pricing_without_erasing_receipt(
    pilot, client, db_pool
):
    deck, _, _, transport = pilot
    transport.reported_model = "provider-model-alias"
    first = await client.post(path(deck) + "/strategy-drafts", json=draft_request())
    run_id = first.json()["data"]["id"]
    view = (await client.get(path(deck) + f"/runs/{run_id}")).json()["data"]
    assert view["status"] == "completed" and len(view["strategies"]) == 3
    receipt = await db_pool.fetchrow(
        "SELECT status,cost_microusd,receipt FROM recommendation_attempts WHERE run_id=$1",
        UUID(run_id),
    )
    assert receipt["status"] == "unknown" and receipt["cost_microusd"] is None
    assert json.loads(receipt["receipt"])["model"] == "provider-model-alias"
    assert view["held_microusd"] > 0
    next_run = await client.post(path(deck) + "/strategy-drafts", json=draft_request())
    assert next_run.status_code == 202 and len(transport.calls) == 2


async def test_draft_is_one_checkpointed_call_and_keeps_card_results_and_deck_unchanged(
    pilot, client, db_pool
):
    deck, owner, service, transport = pilot
    cards_id = await archived_card_run(pilot)
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
    assert len(transport.calls) == 1
    emitted = transport.calls[-1]
    assert emitted["max_output_tokens"] == 4000 and emitted["store"] is False
    assert set(json.loads(emitted["input"])) == {"commanders"}
    status = (await client.get(path(deck) + "/status")).json()["data"]
    assert status["strategy"] is None
    archived = await service.trace(owner, deck, UUID(cards_id))
    assert len(archived["attempts"]) == 3
    repeated = await client.post(path(deck) + "/strategy-drafts", json=body)
    assert repeated.json()["data"]["id"] == draft["id"] and len(transport.calls) == 1
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
    assert cross_profile.status_code == 410 and len(transport.calls) == 1
    oracle_id = await db_pool.fetchval("SELECT oracle_id FROM cards WHERE name = 'Sol Ring'")
    forbidden = await client.post(path(deck) + f"/runs/{draft_id}/candidates/{oracle_id}/plan")
    assert forbidden.status_code == 410
    draft = (await client.get(path(deck) + f"/runs/{draft_id}")).json()["data"]
    selected = draft["strategies"][1]
    edited = selected["goal"] + "\nPrefer a faster start."
    saved = await client.put(path(deck) + "/strategy", json={"prose": edited})
    assert saved.status_code == 200 and len(transport.calls) == 1
    assert (await client.get(path(deck) + "/status")).json()["data"]["strategy"]["prose"] == edited


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
        await service.suggest_terms(
            owner, deck, TermSuggestionRequest(request_key=uuid4(), prose="Artifacts")
        )
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
    _, next_work = await service.draft_strategy(
        owner, deck, StrategyDraftRequest(**draft_request())
    )
    assert next_work is not None
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


async def test_current_strategy_actions_continue_past_the_old_daily_dollar_threshold(
    pilot, client, db_pool
):
    deck, _, _, transport = pilot
    await db_pool.execute(
        "INSERT INTO scryfall_tags (id,slug,metadata) VALUES ($1,'artifacts','{}')", UUID(int=1)
    )
    await client.post(path(deck) + "/strategy-drafts", json=draft_request())
    await db_pool.execute(
        "UPDATE recommendation_attempts SET cost_microusd = $1",
        budget.DAILY_CAP - budget.reservation(budget.STRATEGY_VERSION) + 1,
    )
    for endpoint, body in (
        ("strategy-drafts", draft_request()),
        ("term-suggestions", draft_request() | {"prose": "Artifacts"}),
    ):
        response = await client.post(path(deck) + f"/{endpoint}", json=body)
        assert response.status_code == 202
    assert len(transport.calls) == 3


async def test_empty_term_catalog_stops_before_checkpoint_or_provider_call(pilot, client, db_pool):
    deck, _, _, transport = pilot
    started = await client.post(
        path(deck) + "/term-suggestions", json=draft_request() | {"prose": "Artifacts"}
    )
    assert started.status_code == 202
    run_id = UUID(started.json()["data"]["id"])
    result = (await client.get(path(deck) + f"/term-suggestions/{run_id}")).json()["data"]
    assert result["status"] == "failed" and result["queries"] == []
    assert transport.calls == []
    assert await db_pool.fetchval("SELECT count(*) FROM recommendation_attempts") == 0
    assert (
        await db_pool.fetchval("SELECT held_microusd FROM recommendation_runs WHERE id=$1", run_id)
        == 0
    )


async def test_v2_terms_stay_readable_without_reuse_repricing_or_provider_replay(pilot, db_pool):
    deck, owner, service, transport = pilot
    command = TermSuggestionRequest(request_key=uuid4(), prose="Preserved historical intent")
    run_id, work = await service.suggest_terms(owner, deck, command)
    historical = {"queries": [], "strategy_revision": None, "source_hash": work.source_hash}
    await db_pool.execute(
        "UPDATE recommendation_runs SET profile=$2, status='completed', phase='done', "
        "data=$3::jsonb, held_microusd=123 WHERE id=$1",
        run_id,
        budget.TERMS_VERSION,
        json.dumps(historical),
    )
    before = await db_pool.fetchval(
        "SELECT to_jsonb(r)::text FROM recommendation_runs r WHERE id=$1", run_id
    )
    old = await service.terms_view(owner, deck, run_id)
    assert old.status == "completed"
    assert (await service.setup(owner, deck)).suggestion is None
    await service.run(replace(work, profile=budget.TERMS_VERSION))
    trace = await service.trace(owner, deck, run_id)
    assert trace["profile"] == budget.TERMS_VERSION and trace["data"] == historical
    assert (
        await db_pool.fetchval(
            "SELECT to_jsonb(r)::text FROM recommendation_runs r WHERE id=$1", run_id
        )
        == before
    )
    new_id, new_work = await service.suggest_terms(
        owner, deck, command.model_copy(update={"request_key": uuid4(), "reuse_latest": True})
    )
    assert new_id != run_id and new_work.profile == budget.BOUNDED_TERMS_VERSION
    assert transport.calls == []


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
    cards_id = await archived_card_run(pilot)
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
    assert status["strategy"] is None
    archived = (await client.get(path(deck) + f"/runs/{run_id}")).json()["data"]
    assert archived["stale"] and archived["strategies"] == []
    assert (await client.get(path(deck) + f"/runs/{cards_id}")).status_code == 200
    trace = await service.trace(owner, deck, run_id)
    assert trace["data"] == original and trace["profile"] == "app-strategy-v1"
    assert trace["attempts"][0]["cost_microusd"] == 145
    assert (await client.post(path(deck) + "/strategy-drafts", json=body)).status_code == 409
    assert len(transport.calls) == 1
    await db_pool.execute(
        "UPDATE recommendation_runs SET held_microusd = 7400, status = 'unknown' WHERE id = $1",
        run_id,
    )
    assert (
        await client.post(path(deck) + "/strategy-drafts", json=draft_request())
    ).status_code == 202
    assert (await client.post(path(deck) + "/runs", json=request())).status_code == 410
    assert len(transport.calls) == 2
    original_row = await db_pool.fetchrow("SELECT * FROM recommendation_runs WHERE id=$1", run_id)
    assert original_row["held_microusd"] == 7400 and original_row["status"] == "unknown"
