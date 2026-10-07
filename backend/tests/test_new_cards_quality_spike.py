"""Offline checks for the bounded New Cards diagnostic evaluation."""

import json
from pathlib import Path
from typing import Literal

import httpx
import pytest
from openai import OpenAI

from scripts.new_cards_quality_spike import (
    Assessment,
    AssessmentBatch,
    build_deck,
    name_index,
    run_live,
    run_one,
    score_controls,
    summarize,
    usage_cost,
    validate_assessments,
)
from scripts.new_cards_spike_fixtures import DECKS

pytestmark = pytest.mark.no_db


def test_name_resolution_does_not_replace_real_card_with_same_named_token() -> None:
    real = {
        "name": "Llanowar Elves",
        "oracle_id": "real",
        "first_paper_release": "1993-08-05",
        "legalities": {"commander": "legal"},
    }
    token = {
        "name": "Llanowar Elves",
        "oracle_id": "token",
        "first_paper_release": None,
        "legalities": {"commander": "not_legal"},
    }
    assert name_index([real, token])["Llanowar Elves"]["oracle_id"] == "real"


def test_all_fixture_decks_have_99_unique_noncommander_slots() -> None:
    for spec in DECKS:
        assert isinstance(spec["spells"], str)
        assert isinstance(spec["basics"], dict)
        names = [name.strip() for name in spec["spells"].split("|") if name.strip()]
        assert len(names) == len(set(names))
        assert spec["commander"] not in names
        assert len(names) + sum(spec["basics"].values()) == 99


def test_bad_fixture_count_fails_before_card_resolution() -> None:
    with pytest.raises(ValueError, match="total 0"):
        build_deck({"id": "empty", "spells": "", "basics": {}}, {})


def _assessment(**changes: object) -> Assessment:
    return Assessment.model_validate(
        {
            "oracle_id": "c1",
            "label": "strong",
            "reason": "Reason",
            "support_names": ["Commander"],
            "caveat": "Conditional",
            "required_changes": [],
            **changes,
        }
    )


def _case() -> dict:
    return {
        "candidates": [{"oracle_id": "c1"}],
        "deck": {"commander": {"name": "Commander"}, "physical_cards": []},
    }


def test_exact_valid_response_has_no_errors() -> None:
    assert validate_assessments(AssessmentBatch(assessments=[_assessment()]), _case()) == []


@pytest.mark.parametrize(
    "assessments", [[], [_assessment(), _assessment()], [_assessment(oracle_id="foreign")]]
)
def test_missing_duplicate_foreign_responses_fail(assessments: list[Assessment]) -> None:
    assert (
        "candidate IDs"
        in validate_assessments(AssessmentBatch(assessments=assessments), _case())[0]
    )


@pytest.mark.parametrize(
    "change",
    [
        {"support_names": ["Invented"]},
        {"required_changes": ["Add support"]},
        {"label": "worth_testing", "required_changes": ["A", "B", "C"]},
    ],
)
def test_ungrounded_and_overconfident_outputs_fail(change: dict) -> None:
    assert validate_assessments(AssessmentBatch(assessments=[_assessment(**change)]), _case())


def test_missing_control_cannot_pass() -> None:
    result = score_controls(AssessmentBatch(assessments=[]), {"c1": ["strong"]})
    assert result["matched"] == 0
    assert result["total"] == 1
    assert result["misses"]["c1"]["actual"] is None


def test_price_estimate_uses_actual_usage_with_conservative_input_rate() -> None:
    assert usage_cost({"input_tokens": 1_000_000, "output_tokens": 1_000_000}) == 1.45


def test_all_label_control_is_not_a_free_accuracy_point() -> None:
    result = score_controls(
        AssessmentBatch(assessments=[_assessment()]),
        {"c1": ["strong", "worth_testing", "reject"]},
    )
    assert result["total"] == 0
    assert result["matched"] == 0


@pytest.mark.parametrize("status", [401, 429, 500])
def test_provider_error_is_recorded_without_secret_or_retry(status: int) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "sensitive-error-detail"}})

    with OpenAI(
        api_key="test-secret",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        case = _case()
        case["deck"]["id"] = "test"
        result = run_one(client, "test-model", case, False)
    assert result["status_code"] == status
    assert len(requests) == 1
    assert "sensitive-error-detail" not in str(result)
    assert "test-secret" not in str(result)


@pytest.mark.parametrize("effort", ["low", "high"])
def test_live_contract_uses_required_short_slots_not_free_form_oracle_ids(
    effort: Literal["low", "high"],
) -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "offline contract inspection"}})

    case = _case()
    case["deck"]["id"] = "test"
    with OpenAI(
        api_key="test",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        run_one(client, "test-model", case, False, reasoning_effort=effort, max_output_tokens=16000)
    assert bodies[0]["reasoning"]["effort"] == effort
    assert bodies[0]["max_output_tokens"] == 16000
    schema = bodies[0]["text"]["format"]["schema"]
    assert schema["required"] == ["C01"]
    assert schema["additionalProperties"] is False
    assert "oracle_id" not in bodies[0]["input"]


def _provider_payload(text: str, status: str = "completed") -> dict:
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "model": "test-model",
        "status": status,
        "output": [
            {
                "type": "message",
                "id": "msg_test",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 2,
            "total_tokens": 12,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


@pytest.mark.parametrize(
    "status, error",
    [
        ("completed", "invalid_or_incomplete_structured_output"),
        ("incomplete", "provider_response_not_completed"),
    ],
)
def test_invalid_structured_output_retains_usage_evidence(status: str, error: str) -> None:
    payload = _provider_payload("not valid JSON", status)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with OpenAI(
        api_key="test", max_retries=0, http_client=httpx.Client(transport=transport)
    ) as client:
        case = _case()
        case["deck"]["id"] = "test"
        result = run_one(client, "test-model", case, False)
    assert result["error"] == error
    assert result["usage"]["input_tokens"] == 10
    assert result["estimated_cost_upper_usd"] > 0


def test_successful_provider_output_is_normalized_and_scored() -> None:
    case = _case()
    case["deck"]["id"] = "test"
    case["candidates"][0].update(name="Candidate", rules="Ability.", commander_legality="legal")
    case["expected"] = {"c1": ["reject"]}
    output = {
        "C01": {
            "label": "reject",
            "support_keys": [],
            "mechanism": "No synergy.",
            "reason": "No useful role.",
            "caveat": "",
            "required_changes": [],
            "evidence": [
                {"card_key": "C01", "face_index": None, "field": "rules", "quote": "Ability."}
            ],
        }
    }
    payload = _provider_payload(json.dumps(output))
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with OpenAI(
        api_key="test", max_retries=0, http_client=httpx.Client(transport=transport)
    ) as client:
        result = run_one(client, "test-model", case, False)
    assert result["validation_errors"] == []
    assert result["assessments"][0]["oracle_id"] == "c1"
    assert result["controls"]["matched"] == 1
    assert result["request_sha256"]
    assert result["schema_sha256"]


def test_oversized_input_fails_before_network() -> None:
    case = _case()
    case["deck"]["goal"] = "x" * 180_001
    with OpenAI(api_key="test", max_retries=0) as client:
        with pytest.raises(ValueError, match="180 KB"):
            run_one(client, "test-model", case, False)


def test_summary_counts_drift_without_repairing_missing_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.new_cards_quality_spike.CACHE", tmp_path)
    case = _case()
    case["deck"]["id"] = "test"
    case["candidates"][0]["name"] = "Candidate"
    case["expected"] = {"c1": ["strong"]}
    common = {
        "deck_id": "test",
        "seconds": 1,
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "validation_errors": [],
    }
    runs = [
        common | {"assessments": [_assessment().model_dump()]},
        common | {"assessments": [_assessment(label="reject").model_dump()]},
    ]
    result = summarize([case], {"runs": runs})
    assert result["control_matches"] == 1
    assert result["control_count"] == 2
    assert result["input_tokens"] == 20
    assert len(result["stability"][0]["changes"]) == 1


@pytest.mark.parametrize("status, count", [(400, 1), (401, 1), (403, 1), (429, 1), (500, 8)])
def test_live_run_caps_attempts_checkpoints_and_cannot_be_repeated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: int,
    count: int,
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "offline failure"}})

    client = OpenAI(
        api_key="test",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr("scripts.new_cards_quality_spike.OpenAI", lambda **kwargs: client)
    monkeypatch.setattr("scripts.new_cards_quality_spike.CACHE", tmp_path)
    case = _case()
    case["deck"]["id"] = "test"
    report = run_live([case] * 10)
    assert len(requests) == count
    assert len(report["runs"]) == count
    saved = (tmp_path / "quality-v2-results.json").read_text()
    assert json.loads(saved) == report
    with pytest.raises(ValueError, match="do not overwrite"):
        run_live([case])
    assert len(requests) == count
    assert (tmp_path / "quality-v2-results.json").read_text() == saved


def test_strict_output_schema_forbids_extra_fields() -> None:
    schema = AssessmentBatch.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Assessment"]["additionalProperties"] is False
