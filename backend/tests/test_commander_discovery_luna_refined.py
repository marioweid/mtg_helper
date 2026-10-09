"""Exercise real fresh-Luna workflow and spending guards with only provider I/O doubled."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from openai import APIConnectionError, OpenAI

from mtg_helper.services.recommendations import refinement as refined
from mtg_helper.services.recommendations.discovery import card_facts
from scripts import commander_discovery_check as base
from scripts import commander_discovery_luna_pipeline as pipeline
from scripts import commander_discovery_luna_refined_check as check
from tests.test_commander_discovery_run import prepared

pytestmark = pytest.mark.no_db


def workspace() -> pipeline.Workspace:
    source = prepared()
    initial = source.payloads
    pools = {
        case: payload
        | {
            "candidates": [
                card_facts(base.require_card(source.catalog, name)) | {"key": key}
                for key, name in [("C00", "Found"), ("C01", "Forced")]
            ],
            "rules": [],
        }
        for case, payload in initial.items()
    }
    return pipeline.Workspace(
        prepared=source,
        initial=initial,
        pools=pools,
        entries=refined.parse_rules("123.1. A marker modifies a player."),
    )


class Provider:
    """External response stub; workflow, schemas, retrieval and validation remain real."""

    def __init__(self, path: Path, mode: str = "ok") -> None:
        self.path = path
        self.mode = mode
        self.max_retries = 0
        self.requests: list[dict[str, Any]] = []
        self.responses = self

    def create(self, **kwargs: Any) -> Any:
        report = json.loads(self.path.read_text(encoding="utf-8"))
        assert report["runs"][-1]["state"] == "attempted"
        self.requests.append(kwargs)
        if self.mode == "failure":
            raise APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
        phase = kwargs["text"]["format"]["name"].removeprefix("commander_")
        payload = json.loads(kwargs["input"])
        if phase != "review":
            assert "Forced" not in kwargs["input"]
            output = refined.RefinementPlan(
                intents=["Value"],
                searches=[],
                uncertainties=[],
                named_cards=["Found" if phase == "plan" else "Recent"],
                rule_searches=[
                    refined.RuleQuery(
                        purpose="Inspect resource", text_all=["marker"], text_any=[], cursor=None
                    )
                ],
            ).model_dump_json()
        else:
            assert payload["revised_plan"]["named_cards"] == ["Recent"]
            output = json.dumps(
                {
                    "recommendations": ["C00"],
                    "assessments": {
                        c["key"]: {
                            "fit": "support",
                            "reason": "Useful draw.",
                            "caveat": "",
                            "evidence": [{"key": c["key"], "quote": "Draw two cards."}],
                        }
                        for c in payload["candidates"]
                    },
                }
            )
        usage = {"input_tokens": 100, "output_tokens": 100}
        usage.update(
            {
                "invalid_usage": {"input_tokens": -1},
                "boolean_usage": {"input_tokens": True},
                "oversized_usage": {"input_tokens": 1_000_000},
            }.get(self.mode, {})
        )
        return SimpleNamespace(
            status="incomplete" if self.mode == "incomplete" else "completed",
            output_text="{}" if self.mode == "bad_json" else output,
            model="unexpected" if self.mode == "model" else kwargs["model"],
            service_tier={"tier": "priority", "missing_tier": None}.get(self.mode, "default"),
            usage=None if self.mode == "usage" else SimpleNamespace(model_dump=lambda: usage),
            incomplete_details=None,
        )


def test_six_calls_are_single_use_checkpointed_and_revision_replaces_initial(
    tmp_path: Path,
) -> None:
    path = tmp_path / "results.json"
    provider = Provider(path)
    report = check.Experiment(workspace(), path, cast(OpenAI, provider)).run()
    assert len(report["runs"]) == len(provider.requests) == 6
    assert report.get("stopped") is None
    assert report["reserved_usd"] == pytest.approx(0.1355)
    assert all(
        r["service_tier"] == "default" and not r["store"] and "tools" not in r
        for r in provider.requests
    )
    records = json.loads((tmp_path / "observations/review-meren.json").read_text(encoding="utf-8"))
    assert [c["name"] for c in records["admission"]["initial"]["shortlist"]] == ["Found"]
    assert [c["name"] for c in records["admission"]["replacement"]["shortlist"]] == ["Recent"]
    assert (
        workspace().pools["meren"]["candidates"]
        == json.loads(provider.requests[4]["input"])["candidates"]
    )
    summary = check.summarize(report, tmp_path)
    assert all(r["complete"] for r in summary["runs"] if r["phase"] == "review")
    assert summary["estimated_cost_usd"] < pipeline.BUDGET_USD
    with pytest.raises(FileExistsError):
        check.Experiment(workspace(), path, cast(OpenAI, provider)).run()
    assert len(provider.requests) == 6


@pytest.mark.parametrize(
    "mode",
    [
        "failure",
        "usage",
        "tier",
        "missing_tier",
        "model",
        "invalid_usage",
        "boolean_usage",
        "oversized_usage",
        "incomplete",
        "bad_json",
    ],
)
def test_unknown_billing_bounds_or_quality_failure_stops_without_retry(
    tmp_path: Path, mode: str
) -> None:
    path = tmp_path / "results.json"
    provider = Provider(path, mode)
    report = check.Experiment(workspace(), path, cast(OpenAI, provider)).run()
    assert report["stopped"]
    assert len(provider.requests) == len(report["runs"]) == 1
    summary = check.summarize(report, tmp_path)
    if mode not in {"oversized_usage", "incomplete", "bad_json"}:
        assert summary["estimated_cost_usd"] is None
    assert (tmp_path / "requests/plan-meren.json").exists()


def test_retries_or_oversized_inputs_never_reach_provider(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    provider = Provider(path)
    provider.max_retries = 1
    with pytest.raises(ValueError, match="max_retries"):
        check.Experiment(workspace(), path, cast(OpenAI, provider)).run()
    assert not path.exists()
    provider.max_retries = 0
    context = workspace()
    context.initial["meren"]["goal"] = "x" * 30_000
    report = check.Experiment(context, path, cast(OpenAI, provider)).run()
    assert report["stopped"]
    assert provider.requests == []


def test_remaining_spend_guard_stops_before_any_request(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    provider = Provider(path)
    experiment = check.Experiment(workspace(), path, cast(OpenAI, provider))
    experiment.report["runs"] = [{"phase": "prior", "case_id": "test", "estimated_cost_usd": 0.20}]
    report = experiment.run()
    assert "Remaining reservation" in report["stopped"]
    assert provider.requests == []


def test_changed_assessment_facts_are_refused_before_live_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    pools = workspace().pools
    runs = [
        {
            "phase": "review",
            "case_id": case,
            "status": "completed",
            "input_sha256": hashlib.sha256(
                json.dumps(payload, ensure_ascii=False).encode()
            ).hexdigest(),
        }
        for case, payload in pools.items()
        for _ in range(2)
    ]
    (tmp_path / "results.json").write_text(json.dumps({"runs": runs}), encoding="utf-8")
    monkeypatch.setattr(base, "DESTINATION", tmp_path)
    pipeline.verify_pools(pools)
    pools["meren"]["goal"] = "Altered"
    with pytest.raises(ValueError, match="differ"):
        pipeline.verify_pools(pools)
    with pytest.raises(ValueError, match="exactly"):
        pipeline.verify_pools({})


def test_missing_duplicate_and_incomplete_prerequisite_is_not_substituted() -> None:
    run = {"phase": "plan", "case_id": "meren", "status": "incomplete"}
    for runs in [[], [run, run], [run]]:
        with pytest.raises(ValueError, match="prerequisite"):
            pipeline.decode_plan({"runs": runs}, "plan", "meren")


def test_authorization_scope_and_reservation_cannot_expand(monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as scoped:
        scoped.setattr(pipeline, "CALLS", (*pipeline.CALLS, ("review", "third")))
        with pytest.raises(ValueError, match="six fixed"):
            pipeline.reservation()
    with monkeypatch.context() as scoped:
        scoped.setattr(pipeline, "BUDGET_USD", 1)
        with pytest.raises(ValueError, match="six fixed"):
            pipeline.reservation()
    with monkeypatch.context() as scoped:
        scoped.setitem(pipeline.BOUNDS, "review", (1_000_000, 10_000))
        with pytest.raises(ValueError, match="exceeds"):
            pipeline.reservation()
