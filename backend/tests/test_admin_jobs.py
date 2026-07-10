"""Tests for the admin job registry and the admin router's background-task flow."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient

from mtg_helper.main import app
from mtg_helper.services.admin_jobs import (
    JobRegistry,
    JobState,
    finish_error,
    finish_ok,
    make_progress_cb,
    start,
)

# ── registry primitives ──────────────────────────────────────────────────────


def test_registry_initial_state() -> None:
    reg = JobRegistry()
    for job in (reg.sync, reg.mtgjson, reg.tag, reg.refresh_all):
        assert job.status == "idle"
        assert job.current == 0
        assert job.total == 0
        assert job.started_at is None
        assert job.finished_at is None
        assert job.error is None


def test_start_marks_running_and_stamps_time() -> None:
    job = JobState(key="sync")
    start(job)
    assert job.status == "running"
    assert job.started_at is not None
    assert job.finished_at is None


def test_progress_cb_updates_job_in_place() -> None:
    job = JobState(key="sync")
    cb = make_progress_cb(job)
    cb("upserting", 250, 1000)
    assert job.phase == "upserting"
    assert job.current == 250
    assert job.total == 1000


def test_finish_ok_stamps_result() -> None:
    job = JobState(key="sync")
    start(job)
    finish_ok(job, {"cards_processed": 42})
    assert job.status == "ok"
    assert job.finished_at is not None
    assert job.result == {"cards_processed": 42}


def test_finish_error_records_message() -> None:
    job = JobState(key="sync")
    start(job)
    finish_error(job, "boom")
    assert job.status == "error"
    assert job.error == "boom"
    assert job.finished_at is not None


# ── router behaviour ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_endpoint_returns_all_job_slots(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/admin/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"sync", "mtgjson", "tag", "refresh_all"}
    for key, slot in body.items():
        assert slot["status"] == "idle"
        assert slot["key"] in {"sync", "mtgjson", "tag", "refresh-all"}
        del key  # keys checked above; loop var quietens linters


@pytest.mark.asyncio
async def test_sync_endpoint_returns_202_and_runs_in_background(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST returns 202 immediately; the background task drives state to ok."""
    done = asyncio.Event()

    async def _fake_run_sync(_pool: Any, *, progress: Any) -> dict[str, Any]:
        progress("upserting", 10, 100)
        await asyncio.sleep(0)
        done.set()
        return {"cards_processed": 100, "duration_seconds": 0.01}

    monkeypatch.setattr("mtg_helper.routers.admin.scryfall.run_sync", _fake_run_sync)

    resp = await client.post("/api/v1/admin/sync-cards")
    assert resp.status_code == 202
    body = resp.json()
    assert body["job"] == "sync"

    await asyncio.wait_for(done.wait(), timeout=2.0)
    await asyncio.sleep(0)  # let _wrap finalize

    status = (await client.get("/api/v1/admin/status")).json()["sync"]
    assert status["status"] == "ok"
    assert status["result"]["cards_processed"] == 100


@pytest.mark.asyncio
async def test_mtgjson_endpoint_returns_202_and_runs_in_background(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = asyncio.Event()

    async def _fake_run_sync(_pool: Any, *, progress: Any) -> dict[str, Any]:
        progress("comparing", 1, 1)
        await asyncio.sleep(0)
        done.set()
        return {"mtgjson_cards_processed": 5, "keyword_differences": 1}

    monkeypatch.setattr("mtg_helper.routers.admin.mtgjson.run_sync", _fake_run_sync)

    resp = await client.post("/api/v1/admin/sync-mtgjson")
    assert resp.status_code == 202
    body = resp.json()
    assert body["job"] == "mtgjson"

    await asyncio.wait_for(done.wait(), timeout=2.0)
    await asyncio.sleep(0)

    status = (await client.get("/api/v1/admin/status")).json()["mtgjson"]
    assert status["status"] == "ok"
    assert status["result"]["keyword_differences"] == 1


@pytest.mark.asyncio
async def test_sync_endpoint_rejects_concurrent_runs(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second POST while the first is running returns 409."""
    block = asyncio.Event()

    async def _slow_run_sync(_pool: Any, *, progress: Any) -> dict[str, Any]:
        del progress
        await block.wait()
        return {"cards_processed": 0, "duration_seconds": 0.0}

    monkeypatch.setattr("mtg_helper.routers.admin.scryfall.run_sync", _slow_run_sync)

    first = await client.post("/api/v1/admin/sync-cards")
    assert first.status_code == 202

    second = await client.post("/api/v1/admin/sync-cards")
    assert second.status_code == 409

    block.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_sync_endpoint_records_error_on_failure(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(_pool: Any, *, progress: Any) -> dict[str, Any]:
        del progress
        raise RuntimeError("scryfall unreachable")

    monkeypatch.setattr("mtg_helper.routers.admin.scryfall.run_sync", _boom)

    resp = await client.post("/api/v1/admin/sync-cards")
    assert resp.status_code == 202

    # Let the background task run.
    for _ in range(20):
        await asyncio.sleep(0.01)
        status = (await client.get("/api/v1/admin/status")).json()["sync"]
        if status["status"] != "running":
            break

    assert status["status"] == "error"
    assert "scryfall unreachable" in status["error"]


@pytest.mark.asyncio
async def test_refresh_all_chains_sync_tag(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """refresh-all runs schema, source syncs, then tags in order."""
    phases_seen: list[str] = []

    async def _fake_apply_schema(_pool: Any) -> None:
        phases_seen.append("schema")

    async def _fake_sync(_pool: Any, *, progress: Any) -> dict[str, Any]:
        progress("upserting", 5, 5)
        phases_seen.append("scryfall")
        return {"cards_processed": 5}

    async def _fake_mtgjson(_pool: Any, *, progress: Any) -> dict[str, Any]:
        progress("mtgjson", 3, 3)
        phases_seen.append("mtgjson")
        return {"mtgjson_cards_processed": 3, "mtgjson_keywords_processed": 2}

    async def _fake_hubs(_pool: Any, *, progress: Any) -> dict[str, Any]:
        progress("hubs", 7, 7)
        phases_seen.append("hubs")
        return {"moxfield_hubs_processed": 7, "moxfield_hub_cards_matched": 42}

    async def _fake_tag(_pool: Any, *, progress: Any) -> dict[str, Any]:
        progress("tagging", 5, 5)
        phases_seen.append("tag")
        return {"cards_tagged": 5}

    monkeypatch.setattr("mtg_helper.routers.admin.apply_schema", _fake_apply_schema)
    monkeypatch.setattr("mtg_helper.routers.admin.scryfall.run_sync", _fake_sync)
    monkeypatch.setattr("mtg_helper.routers.admin.mtgjson.run_sync", _fake_mtgjson)
    monkeypatch.setattr(
        "mtg_helper.routers.admin.moxfield_hub_service.sync_hub_card_stats", _fake_hubs
    )
    monkeypatch.setattr("mtg_helper.routers.admin.run_batch_tag", _fake_tag)

    resp = await client.post("/api/v1/admin/refresh-all")
    assert resp.status_code == 202

    for _ in range(50):
        await asyncio.sleep(0.01)
        status = (await client.get("/api/v1/admin/status")).json()["refresh_all"]
        if status["status"] != "running":
            break

    assert status["status"] == "ok"
    assert phases_seen == ["schema", "scryfall", "mtgjson", "hubs", "tag"]
    assert status["result"] == {
        "cards_processed": 5,
        "mtgjson_cards_processed": 3,
        "mtgjson_keywords_processed": 2,
        "moxfield_hubs_processed": 7,
        "moxfield_hub_cards_matched": 42,
        "cards_tagged": 5,
    }
