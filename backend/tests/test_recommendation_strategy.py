"""Offline strategy choice, complete goal context and spending checks; no paid calls."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mtg_helper.services.recommendations import budget, pipeline, strategy
from tests.test_commander_discovery_check import card

pytestmark = pytest.mark.no_db


def option(title: str = "Quick setup") -> dict:
    return {
        "title": title,
        "pace": "Fast setup, then measured value",
        "early_game": "Ramp early and establish inexpensive enablers",
        "engine": "Use the commander's printed abilities repeatedly",
        "payoff": "Turn accumulated value into pressure; finishing package remains open",
        "explanation": "A proposed source-based direction",
        "uncertainties": ["Support cards have not been searched"],
    }


def drafts() -> dict:
    return {"strategies": [option(), option("Steady engine"), option("Patient pressure")]}


def test_strategy_choices_reserve_one_call_without_relaxing_card_bounds() -> None:
    assert budget.reservation("app-strategy-v2") == 9_800
    assert budget.bounds("app-strategy-v2") == {"plan": (20_000, 4_000)}
    assert budget.run_cap("app-strategy-v2") == 10_000
    assert budget.reservation() == 67_750
    assert len(budget.bounds(budget.VERSION)) == 3
    assert budget.DAILY_CAP == 1_000_000


def test_unknown_or_archived_profile_and_oversized_usage_fail_closed() -> None:
    for profile in ("unknown-profile", "app-strategy-v1"):
        for operation in (budget.bounds, budget.reservation, budget.run_cap):
            with pytest.raises(ValueError, match="Unknown"):
                operation(profile)
    receipt = {
        "model": budget.MODEL,
        "service_tier": "default",
        "usage": {"input_tokens": 100, "output_tokens": 4001},
    }
    with pytest.raises(ValueError, match="usage"):
        budget.usage_cost(receipt, budget.bounds(budget.STRATEGY_VERSION)["plan"])


def test_draft_receives_only_complete_commander_facts_not_goal_deck_or_artwork() -> None:
    leader = card("Commander", oracle_id=str(uuid4()), keywords=["UnfamiliarAbility"])
    leader["image_uri"] = "https://cards.scryfall.io/normal/front/card.jpg"
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
    assert facts["keywords"] == ["UnfamiliarAbility"] and "image_uri" not in facts
    assert facts["faces"][0]["power"] == "2"
    assert facts["faces"][1]["oracle_text"] == "{T}: Add {G}."
    fixed = pipeline.check_request("plan", payload, profile=budget.STRATEGY_VERSION)
    assert fixed.output_limit == 4000 and fixed.schema is strategy.StrategyDraft
    with pytest.raises(ValueError, match="exceeds"):
        pipeline.check_request("plan", {"oversized": "x" * 20_000}, profile=budget.STRATEGY_VERSION)
    with pytest.raises(ValueError, match="exactly one"):
        workflow.payload("review", {})


def test_three_choices_carry_full_phase_context_into_the_editable_goal() -> None:
    workflow = strategy.Workflow(context={})
    result = workflow.accept("plan", json.dumps(drafts()), {})
    assert len(result["strategies"]) == 3
    assert "candidates" not in result and "review" not in result
    for selected in result["strategies"]:
        for field in ("title", "pace", "early_game", "engine", "payoff"):
            assert selected[field] in selected["goal"]
        assert selected["uncertainties"][0] in selected["goal"]
        assert len(selected["goal"]) <= 1000
        assert strategy.StrategyChoice.model_validate(selected).goal == selected["goal"]


def test_maximum_choice_lengths_fit_the_goal_without_truncation() -> None:
    selected = {
        "title": "t" * 60,
        "pace": "p" * 80,
        "early_game": "e" * 160,
        "engine": "m" * 200,
        "payoff": "w" * 160,
        "explanation": "x" * 400,
        "uncertainties": ["u" * 100, "v" * 100],
    }
    validated = strategy.StrategyOption.model_validate(selected)
    goal = strategy.goal_for(validated)
    assert len(goal) <= 1000
    for field in ("title", "pace", "early_game", "engine", "payoff"):
        assert selected[field] in goal
    assert all(text in goal for text in selected["uncertainties"])


def test_choices_reject_bad_counts_duplicates_blank_fields_and_never_repair() -> None:
    workflow = strategy.Workflow(context={})
    for invalid in (
        {"strategies": []},
        {"strategies": [option()] * 2},
        {"strategies": [option()] * 4},
        {"strategies": [option(), option(" QUICK SETUP "), option("Other")]},
        {"strategies": [option() | {"engine": " "}, option("B"), option("C")]},
        {"strategies": [option() | {"pace": False}, option("B"), option("C")]},
        {"strategies": [option() | {"payoff": "x" * 161}, option("B"), option("C")]},
        drafts() | {"cards": []},
    ):
        with pytest.raises(ValidationError):
            workflow.accept("plan", json.dumps(invalid), {})
    with pytest.raises(ValueError, match="Duplicate"):
        workflow.accept("plan", '{"strategies":[],"strategies":[]}', {})
    with pytest.raises(ValueError):
        workflow.accept("plan", "not JSON", {})
    with pytest.raises(ValueError, match="exactly one"):
        workflow.accept("review", json.dumps(drafts()), {})
