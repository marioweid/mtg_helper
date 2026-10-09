"""Offline strategy-draft contract and spending checks; no paid calls or database."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mtg_helper.services.recommendations import budget, pipeline, strategy
from tests.test_commander_discovery_check import card

pytestmark = pytest.mark.no_db


def test_strategy_draft_reserves_one_call_without_relaxing_recommendation_bounds() -> None:
    assert budget.reservation("app-strategy-v1") == 7_400
    assert budget.bounds("app-strategy-v1") == {"plan": (20_000, 2_000)}
    assert budget.run_cap("app-strategy-v1") == 10_000
    assert budget.reservation() == 67_750
    assert len(budget.bounds(budget.VERSION)) == 3
    assert budget.DAILY_CAP == 1_000_000


def test_unknown_paid_profile_and_oversized_draft_usage_fail_closed() -> None:
    for operation in (budget.bounds, budget.reservation, budget.run_cap):
        with pytest.raises(ValueError, match="Unknown"):
            operation("unknown-profile")
    receipt = {
        "model": budget.MODEL,
        "service_tier": "default",
        "usage": {"input_tokens": 100, "output_tokens": 2001},
    }
    with pytest.raises(ValueError, match="usage"):
        budget.usage_cost(receipt, budget.bounds(budget.STRATEGY_VERSION)["plan"])


def test_draft_receives_only_complete_commander_facts_not_existing_goal_or_deck() -> None:
    leader = card("Commander", oracle_id=str(uuid4()), keywords=["UnfamiliarAbility"])
    leader["card_faces"] = [
        {
            "name": "Front",
            "type_line": "Creature",
            "mana_cost": "{G}",
            "oracle_text": "New ability.",
            "power": "2",
            "toughness": "3",
        },
        {"name": "Back", "type_line": "Land", "oracle_text": "{T}: Add {G}."},
    ]
    workflow = strategy.Workflow(
        context={
            "commander": leader,
            "goal": "Do not send this",
            "physical": ["Support"],
            "excluded_ids": ["Other"],
            "planned": ["Addition"],
        }
    )
    payload = workflow.payload("plan", {})
    assert set(payload) == {"commander"}
    facts = payload["commander"]
    assert facts["keywords"] == ["UnfamiliarAbility"]
    assert facts["faces"][0]["power"] == "2"
    assert facts["faces"][1]["oracle_text"] == "{T}: Add {G}."
    fixed = pipeline.check_request("plan", payload, profile=budget.STRATEGY_VERSION)
    assert fixed.output_limit == 2000 and fixed.schema is strategy.StrategyDraft
    with pytest.raises(ValueError, match="exceeds"):
        pipeline.check_request("plan", {"oversized": "x" * 20_000}, profile=budget.STRATEGY_VERSION)
    with pytest.raises(ValueError, match="exactly one"):
        workflow.payload("review", {})


def test_strategy_accepts_an_editable_goal_not_cards_and_never_repairs() -> None:
    workflow = strategy.Workflow(context={})
    draft = {
        "goal": "  Use the commander abilities  ",
        "explanation": "A proposed source-based direction",
        "uncertainties": [],
    }
    result = workflow.accept("plan", json.dumps(draft), {})
    assert result["strategy_draft"]["goal"] == "Use the commander abilities"
    assert "candidates" not in result and "review" not in result
    for invalid in (
        draft | {"goal": " "},
        draft | {"goal": "x" * 1001},
        draft | {"explanation": False},
        draft | {"cards": []},
    ):
        with pytest.raises(ValidationError):
            workflow.accept("plan", json.dumps(invalid), {})
    with pytest.raises(ValueError, match="Duplicate"):
        workflow.accept("plan", '{"goal":"one","goal":"two"}', {})
    with pytest.raises(ValueError):
        workflow.accept("plan", "not JSON", {})
    with pytest.raises(ValueError, match="exactly one"):
        workflow.accept("review", json.dumps(draft), {})
