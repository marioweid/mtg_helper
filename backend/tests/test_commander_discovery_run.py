"""Exercise the real paid-call boundary using only an external-provider double."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from openai import APIConnectionError, OpenAI

from mtg_helper.services.recommendations.discovery import Plan, card_facts
from scripts import commander_discovery_check as check
from scripts.deck_recovery_check import build_catalog

pytestmark = pytest.mark.no_db


def prepared() -> check.Prepared:
    cards = [
        {
            "name": name,
            "oracle_id": name,
            "games": ["paper"],
            "cmc": 1,
            "mana_cost": "{1}",
            "type_line": "Creature",
            "oracle_text": "Draw two cards.",
            "keywords": [],
            "color_identity": colors,
            "legalities": {"commander": "legal"},
            "layout": "normal",
        }
        for name, colors in [
            ("Meren", ["B", "G"]),
            ("Saheeli", ["G", "U", "R"]),
            ("Found", []),
            ("Forced", []),
            ("Recent", []),
        ]
    ]
    catalog = build_catalog(cards)
    cases: dict[str, Any] = {
        key: {
            "commander": name,
            "goal": "An open value brew.",
            "diagnostics": {"Forced": "Hidden diagnostic expectation"},
        }
        for key, name in [("meren", "Meren"), ("saheeli", "Saheeli")]
    }
    inputs = {
        key: {
            "commander": card_facts(check.require_card(catalog, case["commander"])),
            "goal": case["goal"],
        }
        for key, case in cases.items()
    }
    return check.Prepared(
        catalog=catalog,
        cases=cases,
        payloads=inputs,
        dates={"Recent": "2026-09-01"},
        rules={"rules": []},
        protocol={"source": {"sha256": "test"}},
    )


class Provider:
    def __init__(self, path: Path, mode: str = "ok") -> None:
        self.path = path
        self.mode = mode
        self.requests: list[dict[str, Any]] = []
        self.responses = self
        self.max_retries = 0

    def create(self, **kwargs: Any) -> Any:
        report = json.loads(self.path.read_text(encoding="utf-8"))
        assert report["runs"][-1]["state"] == "attempted"
        self.requests.append(kwargs)
        if self.mode == "failure":
            raise APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
        payload = json.loads(kwargs["input"])
        if kwargs["text"]["format"]["name"] == "commander_plan":
            assert "Forced" not in kwargs["input"]
            assert "rules" not in payload
            output = Plan(
                intents=["A useful plan"], searches=[], named_cards=["Found"], uncertainties=[]
            ).model_dump_json()
        else:
            output = json.dumps(
                {
                    "recommendations": [c["key"] for c in payload["candidates"]],
                    "assessments": [
                        {
                            "card_key": c["key"],
                            "fit": "support",
                            "reason": "Useful draw.",
                            "caveat": "",
                            "evidence": [{"key": c["key"], "quote": "Draw two cards."}],
                        }
                        for c in payload["candidates"]
                    ],
                }
            )
        counts: dict = {
            "input_tokens": 100,
            "output_tokens": 100,
            "total_tokens": 200,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        }
        counts.update(
            {
                "invalid_usage": {"input_tokens": -1},
                "boolean_usage": {"input_tokens": True},
                "oversized_usage": {"input_tokens": 1_000_000},
            }.get(self.mode, {})
        )
        usage = None if self.mode == "missing_usage" else SimpleNamespace(model_dump=lambda: counts)
        return SimpleNamespace(
            status="incomplete" if self.mode == "incomplete" else "completed",
            output_text="{}" if self.mode == "bad_plan" else output,
            model="unexpected-model" if self.mode == "unexpected_model" else kwargs["model"],
            service_tier={"missing_service_tier": None, "unexpected_service_tier": "priority"}.get(
                self.mode, "default"
            ),
            usage=usage,
            incomplete_details=SimpleNamespace(model_dump=lambda: {"reason": "max_output_tokens"})
            if self.mode == "incomplete"
            else None,
        )


def test_full_paired_run_is_single_use_bounded_and_same_pool(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    provider = Provider(path)
    experiment = check.Experiment(prepared(), path, cast(OpenAI, provider))
    report = experiment.run()
    assert len(provider.requests) == len(report["runs"]) == 8
    assert report.get("stopped") is None
    assert all(r["store"] is False and "tools" not in r for r in provider.requests)
    assert all(r["reasoning"] == {"effort": "low"} for r in provider.requests)
    assert provider.requests[4]["input"] == provider.requests[5]["input"]
    assert provider.requests[6]["input"] == provider.requests[7]["input"]
    inputs = json.loads((tmp_path / "assessment-inputs.json").read_text(encoding="utf-8"))
    summary = check.summarize(report, inputs)
    assert all(r["complete"] for r in summary["runs"] if r["phase"] == "review")
    with pytest.raises(FileExistsError):
        check.Experiment(prepared(), path, cast(OpenAI, provider)).run()
    assert len(provider.requests) == 8


@pytest.mark.parametrize(
    "mode",
    [
        "failure",
        "missing_usage",
        "unexpected_model",
        "invalid_usage",
        "boolean_usage",
        "oversized_usage",
        "missing_service_tier",
        "unexpected_service_tier",
    ],
)
def test_unpriced_or_unbounded_result_stops_without_retry(tmp_path: Path, mode: str) -> None:
    path = tmp_path / "results.json"
    provider = Provider(path, mode)
    report = check.Experiment(prepared(), path, cast(OpenAI, provider)).run()
    assert report["stopped"]
    assert len(provider.requests) == len(report["runs"]) == 1
    summary = check.summarize(report, {})
    if mode != "oversized_usage":
        assert summary["estimated_cost_usd"] is None
        assert summary["unpriced_attempts"] == 1
    with pytest.raises(FileExistsError):
        check.Experiment(prepared(), path, cast(OpenAI, provider)).run()
    assert len(provider.requests) == 1


@pytest.mark.parametrize("mode", ["incomplete", "bad_plan"])
def test_quality_failures_are_retained_not_retried(tmp_path: Path, mode: str) -> None:
    path = tmp_path / "results.json"
    provider = Provider(path, mode)
    report = check.Experiment(prepared(), path, cast(OpenAI, provider)).run()
    inputs = json.loads((tmp_path / "assessment-inputs.json").read_text(encoding="utf-8"))
    summary = check.summarize(report, inputs)
    assert len(provider.requests) == 8
    assert all(r.get("error") for r in summary["runs"])
    retrieval = json.loads((tmp_path / "retrieval.json").read_text(encoding="utf-8"))
    assert retrieval["meren"]["failed_planners"] == ["gpt-5.6-luna", "gpt-5.6-terra"]


def test_retrying_client_is_refused_before_any_request(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    provider = Provider(path)
    provider.max_retries = 2
    with pytest.raises(ValueError, match="max_retries"):
        check.Experiment(prepared(), path, cast(OpenAI, provider)).run()
    assert not provider.requests
    assert not path.exists()


def test_oversized_input_is_not_truncated_or_sent(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    provider = Provider(path)
    inputs = prepared()
    inputs.payloads["meren"]["goal"] = "x" * 30_000
    report = check.Experiment(inputs, path, cast(OpenAI, provider)).run()
    assert report["stopped"]
    assert provider.requests == []


def test_changed_call_plan_and_budget_cannot_expand_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Provider(tmp_path / "results.json")
    with monkeypatch.context() as scoped:
        scoped.setattr(check, "CALLS", (*check.CALLS, check.CALLS[0]))
        with pytest.raises(ValueError, match="eight distinct"):
            check.Experiment(prepared(), provider.path, cast(OpenAI, provider))
    with monkeypatch.context() as scoped:
        scoped.setitem(check.STAGES, "review", replace(check.STAGES["review"], byte_limit=500_000))
        with pytest.raises(ValueError, match="ceiling"):
            check.Experiment(prepared(), provider.path, cast(OpenAI, provider))
    assert provider.requests == []


def test_paid_review_without_frozen_inputs_is_explicitly_failed() -> None:
    report = {
        "runs": [
            {
                "phase": "review",
                "case_id": "meren",
                "model": "gpt-5.6-terra",
                "status": "completed",
                "output": '{"recommendations": [], "assessments": []}',
            }
        ]
    }
    summary = check.summarize(report, {})
    assert summary["runs"][0]["error"] == "missing_assessment_inputs"
