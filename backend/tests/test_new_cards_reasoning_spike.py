"""Offline money, provenance and experimental-control checks for reasoning comparison."""

import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from scripts.new_cards_reasoning_spike import (
    MAX_OUTPUT,
    arm_summary,
    build_cases,
    call_plan,
    freeze_json,
    reserved_cost,
    run_experiment,
)

pytestmark = pytest.mark.no_db


def _card(name: str) -> dict:
    return {
        "oracle_id": name,
        "name": name,
        "rules": "Ability.",
        "mana_cost": "{1}",
        "cmc": 1,
        "type_line": "Artifact",
        "color_identity": [],
        "layout": "normal",
        "commander_legality": "legal",
    }


def _cases() -> list[dict]:
    return [
        {
            "deck": {"id": f"deck-{i}", "commander": _card("Commander"), "physical_cards": []},
            "candidates": [_card(f"candidate-{j}") for j in range(8)],
            "expected": {f"candidate-{j}": ["reject"] for j in range(8)},
            "holdout_ids": [f"candidate-{j}" for j in range(4)],
        }
        for i in range(4)
    ]


def _response(request: httpx.Request) -> dict:
    payload = json.loads(json.loads(request.content)["input"])
    output = {
        card["key"]: {
            "label": "reject",
            "evidence": [
                {"card_key": card["key"], "face_index": None, "field": "rules", "quote": "Ability."}
            ],
            "support_keys": [],
            "mechanism": "No relevant interaction.",
            "reason": "Not useful here.",
            "caveat": "",
            "required_changes": [],
        }
        for card in payload["candidates"]
    }
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "model": "gpt-5.6-luna",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_test",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(output), "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 20},
        },
    }


def test_eight_counterbalanced_calls_differ_only_in_effort_and_cannot_repeat(
    tmp_path: Path,
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=_response(request))

    destination = tmp_path / "results.json"
    with OpenAI(
        api_key="test",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        report = run_experiment(client, _cases(), destination)
        with pytest.raises(FileExistsError):
            run_experiment(client, _cases(), destination)
    assert len(requests) == len(report["runs"]) == 8
    assert report["reserved_upper_usd"] < 0.50
    assert [r["reasoning"]["effort"] for r in requests] == [
        "low",
        "high",
        "high",
        "low",
        "low",
        "high",
        "high",
        "low",
    ]
    for first, second in zip(requests[::2], requests[1::2], strict=True):
        assert first["max_output_tokens"] == second["max_output_tokens"] == MAX_OUTPUT
        assert {k: v for k, v in first.items() if k != "reasoning"} == {
            k: v for k, v in second.items() if k != "reasoning"
        }
        assert "holdout_ids" not in first["input"]
        assert "expected" not in first["input"]
    assert all(
        r["state"] == "attempt_finished" and not r["validation_errors"] for r in report["runs"]
    )
    assert json.loads(destination.read_text(encoding="utf-8")) == report
    summary = arm_summary(_cases(), report["runs"], "high")
    assert summary["contract_valid_runs"] == 4
    assert summary["judgments"] == 32
    assert summary["broad_labels"]["holdout"] == {"matched": 16, "total": 16}
    assert summary["reasoning_tokens"] == 80


@pytest.mark.parametrize("problem", ["budget", "oversized", "count", "duplicate", "retry"])
def test_bad_plan_or_budget_fails_before_any_network(tmp_path: Path, problem: str) -> None:
    requests = []
    cases = _cases()
    if problem in {"budget", "oversized"}:
        cases[0]["deck"]["goal"] = "x" * (180_001 if problem == "oversized" else 175_000)
        if problem == "budget":
            for case in cases[1:]:
                case["deck"]["goal"] = cases[0]["deck"]["goal"]
    elif problem == "count":
        cases.append(cases[0])
    elif problem == "duplicate":
        cases[1]["deck"]["id"] = cases[0]["deck"]["id"]
    destination = tmp_path / "results.json"
    with OpenAI(
        api_key="test",
        max_retries=1 if problem == "retry" else 0,
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: requests.append(request) or httpx.Response(500)
            )
        ),
    ) as client:
        with pytest.raises(ValueError):
            run_experiment(client, cases, destination)
    assert requests == []
    assert not destination.exists()


@pytest.mark.parametrize("failure", ["http", "connection", "incomplete", "usage", "cost"])
def test_failed_attempt_stops_without_retry_or_replacement(tmp_path: Path, failure: str) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if failure == "http":
            return httpx.Response(500, json={"error": {"message": "private provider text"}})
        if failure == "connection":
            raise httpx.ConnectError("private network text", request=request)
        payload = _response(request)
        if failure == "incomplete":
            payload["status"] = "incomplete"
        elif failure == "usage":
            payload["usage"] = None
        else:
            payload["usage"]["input_tokens"] = 10_000_000
        return httpx.Response(200, json=payload)

    with OpenAI(
        api_key="test",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        report = run_experiment(client, _cases(), tmp_path / "results.json")
    assert len(requests) == len(report["runs"]) == 1
    assert report["stopped"]
    assert "private" not in str(report)


def test_unexpected_interruption_leaves_a_reserved_attempt_and_blocks_resume(
    tmp_path: Path,
) -> None:
    class SimulatedInterruption(BaseException):
        pass

    destination = tmp_path / "results.json"

    def handler(request: httpx.Request) -> httpx.Response:
        pending = json.loads(destination.read_text(encoding="utf-8"))
        assert pending["runs"][0]["state"] == "attempt_started"
        raise SimulatedInterruption()

    with OpenAI(
        api_key="test",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        with pytest.raises(SimulatedInterruption):
            run_experiment(client, _cases(), destination)
        with pytest.raises(FileExistsError):
            run_experiment(client, _cases(), destination)
    report = json.loads(destination.read_text(encoding="utf-8"))
    assert len(report["runs"]) == 1
    assert report["runs"][0]["state"] == "attempt_started"
    assert report["runs"][0]["reserved_upper_usd"] > 0


def test_partial_summary_keeps_missing_cases_in_denominator() -> None:
    summary = arm_summary(_cases(), [], "high")
    assert summary["broad_labels"]["holdout"] == {"matched": 0, "total": 16}
    assert summary["broad_labels"]["regression"] == {"matched": 0, "total": 16}
    assert summary["contract_valid_runs"] == 0
    assert summary["median_seconds"] is None


def test_frozen_inputs_are_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "cases.json"
    freeze_json(path, {"card": "Éowyn"})
    original = path.read_bytes()
    freeze_json(path, {"card": "Éowyn"})
    with pytest.raises(ValueError, match="Frozen artifact differs"):
        freeze_json(path, {"card": "Different"})
    assert path.read_bytes() == original


@pytest.mark.parametrize("problem", ["too_few", "duplicate_candidate"])
def test_bad_candidate_pool_fails_plan_validation(problem: str) -> None:
    cases = _cases()
    if problem == "too_few":
        cases[0]["candidates"].pop()
    else:
        cases[0]["candidates"][1] = cases[0]["candidates"][0]
    with pytest.raises(ValueError):
        call_plan(cases)


def test_reservation_covers_full_output_plus_input() -> None:
    assert reserved_cost(_cases()[0]) > MAX_OUTPUT * 1.2 / 1_000_000


def test_holdout_selection_does_not_leak_earlier_inputs() -> None:
    baseline = _cases()[:1]
    existing = _card("Commander")
    catalog = [
        existing
        | {
            "first_paper_release": "2020-01-01",
            "full_rules": "Ability.",
            "legalities": {"commander": "legal"},
        }
    ]
    spec = {
        "decks": {
            "deck-0": [
                {
                    "name": "Commander",
                    "kind": "holdout",
                    "labels": ["reject"],
                    "check": "Not a real holdout",
                }
            ]
        }
    }
    with pytest.raises(ValueError, match="holdout identity"):
        build_cases(baseline, catalog, spec)
