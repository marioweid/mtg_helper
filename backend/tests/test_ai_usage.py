"""Tests for non-sensitive, non-fatal AI usage telemetry."""

import logging

import pytest
from pydantic_ai import RunUsage

from mtg_helper.services.agents._usage import log_run_usage

pytestmark = pytest.mark.no_db


def test_logs_usage_without_prompt_output_or_cost(caplog) -> None:
    usage = RunUsage(
        requests=2,
        input_tokens=120,
        output_tokens=30,
        cache_read_tokens=80,
        cache_write_tokens=4,
        tool_calls=1,
        details={"reasoning_tokens": 10},
    )

    with caplog.at_level(logging.INFO, logger="mtg_helper.services.agents._usage"):
        log_run_usage("sentinel_workflow", "sentinel_operation", usage)

    assert "workflow=sentinel_workflow operation=sentinel_operation" in caplog.text
    assert "input_tokens=120" in caplog.text
    assert "output_tokens=30" in caplog.text
    assert "reasoning_tokens" in caplog.text
    assert "prompt sentinel" not in caplog.text
    assert "output sentinel" not in caplog.text
    assert "USD" not in caplog.text


def test_logging_failure_is_non_fatal(monkeypatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("logging unavailable")

    monkeypatch.setattr("mtg_helper.services.agents._usage.logger.info", fail)
    monkeypatch.setattr("mtg_helper.services.agents._usage.logger.error", fail)

    log_run_usage("simulation_analysis", "analyze", RunUsage(requests=1))
