"""Tests for the Scryfall-only admin maintenance jobs."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient

from mtg_helper.services.admin_jobs import (
    JobRegistry,
    JobState,
    finish_error,
    finish_ok,
    make_progress_cb,
    start,
)


def test_registry_initial_state() -> None:
    """Only source-publication jobs are registered."""
    registry = JobRegistry()
    for job in (registry.sync, registry.refresh_all):
        assert job.status == "idle"
        assert job.current == 0
        assert job.total == 0
        assert job.started_at is None
        assert job.finished_at is None
        assert job.error is None


def test_job_lifecycle_records_progress_and_failure() -> None:
    job = JobState(key="sync")
    start(job)
    make_progress_cb(job)("publishing", 1, 2)
    finish_error(job, "source unavailable")
    assert (job.status, job.phase, job.current, job.total) == ("error", "publishing", 1, 2)
    assert job.error == "source unavailable"


def test_job_lifecycle_records_result() -> None:
    job = JobState(key="sync")
    start(job)
    finish_ok(job, {"cards_processed": 42})
    assert job.status == "ok"
    assert job.result == {"cards_processed": 42}


@pytest.mark.asyncio
async def test_status_endpoint_returns_only_scryfall_job_slots(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/status")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"sync", "refresh_all", "scryfall_sources"}
    assert body["sync"]["key"] == "sync"
    assert body["refresh_all"]["key"] == "refresh-all"


@pytest.mark.asyncio
async def test_sync_endpoint_runs_scryfall_in_background(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = asyncio.Event()

    async def fake_sync(_pool: Any, *, progress: Any) -> dict[str, Any]:
        progress("publishing", 1, 1)
        done.set()
        return {"cards_processed": 1}

    monkeypatch.setattr("mtg_helper.routers.admin.scryfall.run_sync", fake_sync)
    response = await client.post("/api/v1/admin/sync-cards")
    assert response.status_code == 202
    await asyncio.wait_for(done.wait(), timeout=2)
    await asyncio.sleep(0)
    assert (await client.get("/api/v1/admin/status")).json()["sync"]["status"] == "ok"


@pytest.mark.asyncio
async def test_refresh_all_applies_schema_then_publishes_scryfall(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    phases: list[str] = []

    async def fake_schema(_pool: Any) -> None:
        phases.append("schema")

    async def fake_sync(_pool: Any, *, progress: Any) -> dict[str, Any]:
        progress("publishing", 1, 1)
        phases.append("scryfall")
        return {"cards_processed": 1}

    monkeypatch.setattr("mtg_helper.routers.admin.apply_schema", fake_schema)
    monkeypatch.setattr("mtg_helper.routers.admin.scryfall.run_sync", fake_sync)
    response = await client.post("/api/v1/admin/refresh-all")
    assert response.status_code == 202
    for _ in range(20):
        await asyncio.sleep(0.01)
        if (await client.get("/api/v1/admin/status")).json()["refresh_all"]["status"] != "running":
            break
    assert phases == ["schema", "scryfall"]
