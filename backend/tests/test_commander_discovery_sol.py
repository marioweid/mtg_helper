"""Sol's fixed-pool comparison must not expand paid scope or modify previous evidence."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from openai import OpenAI

from scripts import commander_discovery_check as base
from scripts import commander_discovery_sol_check as sol
from scripts.new_cards_data_spike import write_json
from tests.test_commander_discovery_run import Provider, prepared

pytestmark = pytest.mark.no_db


def frozen_context(tmp_path: Path) -> base.Prepared:
    context = prepared()
    pools, _ = base.review_inputs(context, {"runs": []})
    path = tmp_path / "fixed-assessments.json"
    write_json(path, pools)
    return replace(
        context,
        protocol={
            **context.protocol,
            "assessment_file": str(path),
            "assessment_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
    )


def test_reservation_is_four_calls_at_checked_sol_upper_rates() -> None:
    assert sol.reservation() == pytest.approx(0.75)


def test_sol_uses_identical_fixed_pools_and_single_use_four_call_ledger(tmp_path: Path) -> None:
    context = frozen_context(tmp_path)
    path = tmp_path / "results.json"
    provider = Provider(path)
    execution = sol.execution(context)
    report = base.Experiment(context, path, cast(OpenAI, provider), execution=execution).run()
    fixed = json.loads(Path(context.protocol["assessment_file"]).read_text(encoding="utf-8"))
    assert len(provider.requests) == len(report["runs"]) == 4
    assert report.get("stopped") is None
    assert all(r["model"] == sol.MODEL for r in provider.requests)
    assert all(r["store"] is False and "tools" not in r for r in provider.requests)
    assert all(r["reasoning"] == {"effort": "low"} for r in provider.requests)
    assert all(r.get("service_tier") == "default" for r in provider.requests)
    for index, case in [(2, "meren"), (3, "saheeli")]:
        assert provider.requests[index]["input"] == json.dumps(fixed[case], ensure_ascii=False)
    assert "Found" not in {c["name"] for c in fixed["meren"]["candidates"]}
    records = json.loads((tmp_path / "retrieval.json").read_text(encoding="utf-8"))
    assert records["meren"]["discoveries"][sol.MODEL]["shortlist"][0]["name"] == "Found"
    summary = base.summarize(report, fixed, authorized_maximum=4)
    assert summary["authorized_maximum"] == 4
    assert all(r["complete"] for r in summary["runs"] if r["phase"] == "review")
    with pytest.raises(FileExistsError):
        base.Experiment(context, path, cast(OpenAI, provider), execution=execution).run()
    assert len(provider.requests) == 4


@pytest.mark.parametrize(
    "mode",
    [
        "failure",
        "missing_usage",
        "unexpected_model",
        "boolean_usage",
        "missing_service_tier",
        "unexpected_service_tier",
    ],
)
def test_sol_billing_failures_stop_after_one_attempt(tmp_path: Path, mode: str) -> None:
    context = frozen_context(tmp_path)
    path = tmp_path / "results.json"
    provider = Provider(path, mode)
    report = base.Experiment(
        context, path, cast(OpenAI, provider), execution=sol.execution(context)
    ).run()
    assert report["stopped"]
    assert len(provider.requests) == len(report["runs"]) == 1
    assert base.summarize(report, {}, authorized_maximum=4)["unpriced_attempts"] == 1


def test_sol_refuses_changed_call_scope_before_any_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = frozen_context(tmp_path)
    monkeypatch.setattr(sol, "CALLS", (*sol.CALLS, sol.CALLS[0]))
    with pytest.raises(ValueError, match="four"):
        sol.execution(context)
    assert not (tmp_path / "results.json").exists()


def test_sol_refuses_changed_frozen_pool_before_any_attempt(tmp_path: Path) -> None:
    context = frozen_context(tmp_path)
    Path(context.protocol["assessment_file"]).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="assessment"):
        sol.execution(context)


def test_sol_refuses_increased_stage_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = frozen_context(tmp_path)
    monkeypatch.setitem(base.STAGES, "review", replace(base.STAGES["review"], byte_limit=500_000))
    with pytest.raises(ValueError, match="ceiling"):
        sol.execution(context)


def test_sol_refuses_retrying_client(tmp_path: Path) -> None:
    context = frozen_context(tmp_path)
    provider = Provider(tmp_path / "results.json")
    provider.max_retries = 2
    with pytest.raises(ValueError, match="max_retries"):
        base.Experiment(
            context, provider.path, cast(OpenAI, provider), execution=sol.execution(context)
        ).run()
    assert not provider.requests


def test_sol_refuses_oversized_payload_without_truncation(tmp_path: Path) -> None:
    context = frozen_context(tmp_path)
    execution = sol.execution(context)
    context.payloads["meren"]["goal"] = "x" * 30_000
    provider = Provider(tmp_path / "results.json")
    report = base.Experiment(
        context, provider.path, cast(OpenAI, provider), execution=execution
    ).run()
    assert report["stopped"]
    assert not provider.requests
