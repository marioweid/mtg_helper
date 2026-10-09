"""Fresh assessment authorization must neither reset failed receipts nor broaden its cap."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from openai import OpenAI

from scripts import commander_discovery_check as base
from scripts import commander_discovery_sol_assessment_check as finish
from tests.test_commander_discovery_run import Provider
from tests.test_commander_discovery_sol import frozen_context

pytestmark = pytest.mark.no_db


def test_two_assessment_calls_use_same_payloads_with_smaller_ceiling(tmp_path: Path) -> None:
    context = frozen_context(tmp_path)
    path = tmp_path / "new-results.json"
    provider = Provider(path)
    fixed_path = Path(context.protocol["assessment_file"])
    before = fixed_path.read_bytes()
    assert finish.reservation() == pytest.approx(0.55)
    policy = finish.execution(context)
    assert policy.ceiling_usd == 0.60
    report = base.Experiment(context, path, cast(OpenAI, provider), execution=policy).run()
    pools = json.loads(before)
    assert len(provider.requests) == len(report["runs"]) == 2
    assert report.get("stopped") is None
    for request, case in zip(provider.requests, ["meren", "saheeli"], strict=True):
        assert request["input"] == json.dumps(pools[case], ensure_ascii=False)
        assert request["service_tier"] == "default"
        assert request["text"]["format"]["name"] == "commander_review"
    assert fixed_path.read_bytes() == before
    assert base.summarize(report, pools, authorized_maximum=2)["authorized_maximum"] == 2
    with pytest.raises(FileExistsError):
        base.Experiment(context, path, cast(OpenAI, provider), execution=policy).run()
    assert len(provider.requests) == 2


def test_smaller_authorized_cap_is_enforced_even_below_original_one_dollar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(base.STAGES, "review", replace(base.STAGES["review"], byte_limit=90_000))
    with pytest.raises(ValueError, match="ceiling"):
        finish.reservation()


def test_remaining_cost_guard_uses_execution_ceiling_not_global_default(tmp_path: Path) -> None:
    context = frozen_context(tmp_path)
    policy = finish.execution(context)
    provider = Provider(tmp_path / "results.json")
    runner = base.Experiment(context, provider.path, cast(OpenAI, provider), execution=policy)
    runner.report["runs"] = [{"estimated_cost_usd": 0.10}]
    assert runner._within_bounds(0, "review", {}) is False
    assert runner.report["stopped"]
    assert not provider.requests


@pytest.mark.parametrize("mode", ["failure", "missing_usage", "unexpected_service_tier"])
def test_failed_reissue_is_not_automatically_retried(tmp_path: Path, mode: str) -> None:
    context = frozen_context(tmp_path)
    path = tmp_path / "results.json"
    provider = Provider(path, mode)
    report = base.Experiment(
        context, path, cast(OpenAI, provider), execution=finish.execution(context)
    ).run()
    assert report["stopped"]
    assert len(provider.requests) == len(report["runs"]) == 1


def test_completion_cannot_add_planner_or_third_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(finish, "CALLS", (*finish.CALLS, finish.CALLS[0]))
    with pytest.raises(ValueError, match="two"):
        finish.reservation()
