"""Behavior checks for the isolated, source-only role experiment."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from mtg_helper.services.recommendations import budget, pipeline, provider
from mtg_helper.services.recommendations.service import request_payload
from scripts import discover_role_calls as calls
from scripts import discover_role_controls as controls
from scripts import discover_role_experiment as experiment

pytestmark = pytest.mark.no_db

A = UUID(int=1)
B = UUID(int=2)


def test_roles_diversify_and_deduplicate_instead_of_rewarding_repeated_overlap() -> None:
    assert experiment.round_robin([["a", "b", "c"], ["a", "d"], [], ["e"]]) == [
        "a",
        "e",
        "b",
        "d",
        "c",
    ]


def test_groups_require_intersection_but_allow_alternatives_inside_each_group() -> None:
    lane = experiment.RoleLane(
        purpose="Recurring engine",
        groups=[
            {"oracle_tag_ids": [A], "printed_keywords": []},
            {"oracle_tag_ids": [B], "printed_keywords": ["Persist"]},
        ],
        card_types_any=["Creature"],
    )
    cards = [
        {"oracle_id": "a", "source_facts": {"type_line": "Creature", "keywords": []}},
        {"oracle_id": "b", "source_facts": {"type_line": "Creature", "keywords": ["Persist"]}},
        {"oracle_id": "c", "source_facts": {"type_line": "Artifact", "keywords": ["Persist"]}},
        {"oracle_id": "d", "source_facts": {"type_line": "Creature", "keywords": []}},
    ]
    members = {str(A): {"a", "b", "c"}, str(B): {"a", "d"}}
    assert experiment.lane_members(lane, cards, members) == {"a", "b"}


def test_empty_group_is_not_an_unfiltered_search() -> None:
    with pytest.raises(ValueError, match="nonempty"):
        experiment.TermGroup(oracle_tag_ids=[], printed_keywords=[])


def plan_payload() -> dict[str, Any]:
    return {"oracle_tags": [{"id": str(A)}, {"id": str(B)}], "printed_keywords": ["Persist"]}


def plan_text(*, tag: UUID = A, keyword: str = "Persist") -> str:
    return json.dumps(
        {
            "lanes": [
                {
                    "purpose": "Engine",
                    "groups": [{"oracle_tag_ids": [str(tag)], "printed_keywords": [keyword]}],
                    "card_types_any": [],
                }
            ]
        }
    )


@pytest.mark.parametrize("tag,keyword", [(UUID(int=9), "Persist"), (A, "Invented")])
def test_role_plan_rejects_source_terms_not_in_supplied_menu(tag: UUID, keyword: str) -> None:
    with pytest.raises(ValueError, match="outside the supplied catalog"):
        experiment.validate_plan(plan_text(tag=tag, keyword=keyword), plan_payload())


def test_plan_validates_actual_source_ids_and_rejects_duplicate_lanes() -> None:
    plan = experiment.validate_plan(plan_text(), plan_payload())
    assert experiment.flat_criteria(plan) == {
        "oracle_tag_ids": [A],
        "printed_keywords": ["Persist"],
    }
    data = json.loads(plan_text())
    data["lanes"] *= 2
    with pytest.raises(ValueError, match="repeats the same lane"):
        experiment.validate_plan(json.dumps(data), plan_payload())


def test_whole_plan_retains_baseline_eight_tag_budget() -> None:
    lanes = [
        {
            "purpose": str(i),
            "groups": [
                {"oracle_tag_ids": [str(UUID(int=i + j)) for j in range(3)], "printed_keywords": []}
            ],
            "card_types_any": [],
        }
        for i in (1, 4, 7)
    ]
    with pytest.raises(ValueError, match="eight distinct"):
        experiment.RolePlan.model_validate({"lanes": lanes})


def test_round_robin_handles_empty_and_duplicate_only_pools() -> None:
    assert experiment.round_robin([]) == []
    assert experiment.round_robin([[], []]) == []
    assert experiment.round_robin([["a", "a"], ["a"]]) == ["a"]


def test_equivalent_lane_constraints_do_not_gain_extra_round_robin_slots() -> None:
    first = experiment.RoleLane(
        purpose="First",
        groups=[
            {"oracle_tag_ids": [A, B], "printed_keywords": []},
            {"oracle_tag_ids": [], "printed_keywords": ["Persist"]},
        ],
        card_types_any=["Creature", "Artifact"],
    )
    second = experiment.RoleLane(
        purpose="Different words",
        groups=[
            {"oracle_tag_ids": [], "printed_keywords": ["Persist"]},
            {"oracle_tag_ids": [B, A], "printed_keywords": []},
        ],
        card_types_any=["Artifact", "Creature"],
    )
    assert experiment.lane_signature(first) == experiment.lane_signature(second)


def protocol_fixture() -> dict[str, Any]:
    payload = {"strategy": "An engine", "oracle_tags": [], "printed_keywords": []}
    records = []
    for key, arm in calls.CALLS:
        if arm == "roles":
            request = calls.role_request(payload)
        else:
            fixed = pipeline.check_request("plan", payload, profile=budget.TERMS_VERSION)
            request = request_payload("plan", payload, fixed)
        records.append(
            {
                "deck": key,
                "arm": arm,
                "payload": payload,
                "request": request,
                "input_bound": len(json.dumps(request, ensure_ascii=False).encode()) + 2_000,
            }
        )
    return {
        "calls": records,
        "code_hashes": calls.code_hashes(),
        "reserved_microusd": calls.reservation(records),
    }


@pytest.mark.parametrize("change", ["extra", "order", "model", "output", "size"])
def test_reservation_rejects_changed_authorizations(change: str) -> None:
    protocol = protocol_fixture()
    records = protocol["calls"]
    if change == "extra":
        records.append(records[0])
    elif change == "order":
        records.reverse()
    elif change == "model":
        records[0]["request"]["model"] = "different"
    elif change == "output":
        records[0]["request"]["max_output_tokens"] += 1
    else:
        records[0]["input_bound"] += 1
    with pytest.raises(ValueError):
        calls.reservation(records)


def test_four_calls_are_reserved_below_authorized_ceiling() -> None:
    protocol = protocol_fixture()
    assert 0 < protocol["reserved_microusd"] <= 100_000
    calls.validate_protocol(protocol)


class Sender(provider.Provider):
    def __init__(self, path: Path, *, unknown: bool = False) -> None:
        super().__init__("test")
        self.path = path
        self.unknown = unknown
        self.count = 0

    async def request(self, frozen: dict[str, Any]) -> dict[str, Any]:
        self.count += 1
        ledger = json.loads(self.path.read_text())
        assert len(ledger["attempts"]) == self.count
        assert ledger["attempts"][-1]["state"] == "attempted"
        return {
            "status": "completed",
            "model": budget.MODEL,
            "service_tier": "default",
            "output": "{}",
            "usage": None if self.unknown else {"input_tokens": 10, "output_tokens": 10},
        }


@pytest.mark.asyncio
async def test_attempts_are_checkpointed_and_authorization_cannot_be_reused(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    sender = Sender(path)
    protocol = protocol_fixture()
    report = await calls.run_live(protocol, path, sender)
    assert sender.count == 4
    assert len(report["attempts"]) == 4
    with pytest.raises(FileExistsError):
        await calls.run_live(protocol, path, sender)
    assert sender.count == 4


@pytest.mark.asyncio
async def test_missing_usage_stops_without_further_calls_or_zero_cost_claim(tmp_path: Path) -> None:
    sender = Sender(tmp_path / "ledger.json", unknown=True)
    report = await calls.run_live(protocol_fixture(), sender.path, sender)
    assert sender.count == 1
    assert "stopped" in report
    assert "estimated_cost_microusd" not in report["attempts"][0]


@pytest.mark.asyncio
async def test_timeout_does_not_retry_and_preserves_attempt_checkpoint(tmp_path: Path) -> None:
    class TimeoutSender(Sender):
        async def request(self, frozen: dict[str, Any]) -> dict[str, Any]:
            await super().request(frozen)
            raise TimeoutError("Sensitive transport details must not reach saved diagnostics")

    sender = TimeoutSender(tmp_path / "ledger.json")
    report = await calls.run_live(protocol_fixture(), sender.path, sender)
    assert sender.count == 1
    assert report["attempts"][0]["state"] == "attempted"
    assert report["attempts"][0]["error"] == "TimeoutError"
    assert "Sensitive" not in sender.path.read_text()


def test_request_tampering_is_rejected_even_when_size_and_reservation_are_updated() -> None:
    protocol = protocol_fixture()
    call = protocol["calls"][0]
    call["request"]["instructions"] = "Changed instructions"
    call["input_bound"] = len(json.dumps(call["request"], ensure_ascii=False).encode()) + 2_000
    protocol["reserved_microusd"] = calls.reservation(protocol["calls"])
    with pytest.raises(ValueError, match="request changed"):
        calls.validate_protocol(protocol)


def test_structured_role_output_requires_all_fields_and_forbids_extras() -> None:
    schema = experiment.RolePlan.model_json_schema()
    for entry in [schema, *schema["$defs"].values()]:
        if entry.get("type") == "object":
            assert set(entry["required"]) == set(entry["properties"])
            assert entry["additionalProperties"] is False


def test_ranking_ablations_keep_eligibility_and_do_not_drop_missing_popularity() -> None:
    plan = experiment.RolePlan.model_validate(
        {
            "lanes": [
                {
                    "purpose": "Engine",
                    "groups": [{"oracle_tag_ids": [str(A)], "printed_keywords": []}],
                    "card_types_any": [],
                },
                {
                    "purpose": "Complement",
                    "groups": [{"oracle_tag_ids": [str(B)], "printed_keywords": []}],
                    "card_types_any": [],
                },
            ]
        }
    )
    cards = [
        {
            "oracle_id": "a",
            "name": "A",
            "match_count": 2,
            "edhrec_rank": 1,
            "source_facts": {"type_line": "Artifact", "keywords": []},
        },
        {
            "oracle_id": "b",
            "name": "B",
            "match_count": 1,
            "edhrec_rank": None,
            "source_facts": {"type_line": "Creature", "keywords": []},
        },
        {
            "oracle_id": "c",
            "name": "C",
            "match_count": 1,
            "edhrec_rank": 2,
            "source_facts": {"type_line": "Creature", "keywords": []},
        },
    ]
    memberships = {str(A): {"a", "b", "outside-eligible-pool"}, str(B): {"a", "c"}}
    result = experiment.compare_roles(plan, cards, memberships, {"b", "c"})
    for arm in result["arms"].values():
        assert arm["total"] == 3
        assert arm["reference_hits_in_pool"] == 2
        assert {row["oracle_id"] for row in arm["cards"]} == {"a", "b", "c"}


def test_empty_role_lanes_are_reported_and_do_not_erase_other_roles() -> None:
    plan = experiment.RolePlan.model_validate(
        {
            "lanes": [
                {
                    "purpose": "Empty",
                    "groups": [{"oracle_tag_ids": [str(A)], "printed_keywords": []}],
                    "card_types_any": [],
                },
                {
                    "purpose": "Nonempty",
                    "groups": [{"oracle_tag_ids": [str(B)], "printed_keywords": []}],
                    "card_types_any": [],
                },
            ]
        }
    )
    cards = [
        {
            "oracle_id": "a",
            "name": "A",
            "match_count": 1,
            "edhrec_rank": None,
            "source_facts": {"type_line": "Creature", "keywords": []},
        }
    ]
    result = experiment.compare_roles(plan, cards, {str(A): set(), str(B): {"a"}}, {"a"})
    assert [row["matches"] for row in result["lanes"]] == [0, 1]
    assert result["arms"]["role_round_robin"]["reference_hits_at_10"] == 1


def test_popularity_control_is_not_an_overlap_count_tiebreak() -> None:
    rows = [
        {"name": "A", "oracle_id": "a", "match_count": 9, "edhrec_rank": 100},
        {"name": "B", "oracle_id": "b", "match_count": 1, "edhrec_rank": 1},
        {"name": "C", "oracle_id": "c", "match_count": 5, "edhrec_rank": None},
    ]
    assert [row["oracle_id"] for row in controls.global_popularity(rows)] == ["b", "a", "c"]
    assert rows[0]["oracle_id"] == "a"
