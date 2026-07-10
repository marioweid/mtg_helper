"""Tests for runtime feature flags, the optimizer guard, and /capabilities.

Client-based tests clean ``feature_flags`` via ``app.state.db_pool`` rather
than requesting the ``db_pool`` fixture: under ``asyncio_mode=auto`` pulling
both ``client`` and ``db_pool`` into one test binds them to different event
loops, which breaks asyncpg inside the ASGI handler.
"""

from __future__ import annotations

from uuid import uuid4

import asyncpg
import pytest
from httpx import AsyncClient

from mtg_helper.main import app
from mtg_helper.models.optimizer import OptimizeRequest
from mtg_helper.routers.ai import _OPTIMIZE_SEMAPHORE, _run_optimize_job
from mtg_helper.services import feature_flag_service, optimizer_jobs
from mtg_helper.services.feature_flag_service import FLAG_OPTIMIZER

pytestmark = pytest.mark.asyncio

_HAZEL = "4d7b8d2c-36f5-40e7-91de-9c8c1b44da67"


async def _clear_flags(pool: asyncpg.Pool) -> None:
    """Feature-flag rows persist across a session; reset at the start of a test."""
    await pool.execute("DELETE FROM feature_flags")


async def _make_deck(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/decks", json={"commander_scryfall_id": _HAZEL, "name": "Flag Test"}
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


# ── service-level resolution ──────────────────────────────────────────────


async def test_is_enabled_falls_back_to_default(db_pool: asyncpg.Pool) -> None:
    await _clear_flags(db_pool)
    assert await feature_flag_service.is_enabled(db_pool, FLAG_OPTIMIZER, None, False) is False
    assert await feature_flag_service.is_enabled(db_pool, FLAG_OPTIMIZER, None, True) is True


async def test_global_override_beats_default_and_clear_reverts(db_pool: asyncpg.Pool) -> None:
    await _clear_flags(db_pool)
    await feature_flag_service.set_flag(db_pool, FLAG_OPTIMIZER, True)
    assert await feature_flag_service.is_enabled(db_pool, FLAG_OPTIMIZER, None, False) is True

    await feature_flag_service.set_flag(db_pool, FLAG_OPTIMIZER, False)  # upsert, not duplicate
    assert await feature_flag_service.is_enabled(db_pool, FLAG_OPTIMIZER, None, True) is False

    await feature_flag_service.clear_flag(db_pool, FLAG_OPTIMIZER)
    assert await feature_flag_service.is_enabled(db_pool, FLAG_OPTIMIZER, None, True) is True


async def test_account_override_beats_global(db_pool: asyncpg.Pool) -> None:
    await _clear_flags(db_pool)
    enabled_acct = uuid4()
    other_acct = uuid4()
    await db_pool.execute(
        "INSERT INTO accounts (id, display_name) VALUES ($1, $2), ($3, $4)",
        enabled_acct,
        "Enabled Account",
        other_acct,
        "Other Account",
    )
    await feature_flag_service.set_flag(db_pool, FLAG_OPTIMIZER, False)
    await feature_flag_service.set_flag(db_pool, FLAG_OPTIMIZER, True, enabled_acct)

    enabled_on = await feature_flag_service.is_enabled(db_pool, FLAG_OPTIMIZER, enabled_acct, False)
    other_off = await feature_flag_service.is_enabled(db_pool, FLAG_OPTIMIZER, other_acct, False)
    assert enabled_on is True
    assert other_off is False

    await feature_flag_service.clear_flag(db_pool, FLAG_OPTIMIZER, enabled_acct)
    reverted = await feature_flag_service.is_enabled(db_pool, FLAG_OPTIMIZER, enabled_acct, False)
    assert reverted is False


# ── /capabilities ─────────────────────────────────────────────────────────


async def test_capabilities_optimizer_off_by_default(client: AsyncClient) -> None:
    await _clear_flags(app.state.db_pool)
    resp = await client.get("/api/v1/capabilities")
    assert resp.status_code == 200
    assert resp.json()["data"]["optimizer"] is False


async def test_capabilities_reflects_global_enable(client: AsyncClient) -> None:
    await _clear_flags(app.state.db_pool)
    put = await client.put("/api/v1/admin/feature-flags/optimizer", json={"enabled": True})
    assert put.status_code == 200
    resp = await client.get("/api/v1/capabilities")
    assert resp.json()["data"]["optimizer"] is True


async def test_admin_rejects_unknown_feature_flag(client: AsyncClient) -> None:
    """Unknown feature flags should fail validation."""
    resp = await client.put("/api/v1/admin/feature-flags/typo", json={"enabled": True})
    assert resp.status_code == 422


async def test_admin_rejects_malformed_account_override(client: AsyncClient) -> None:
    """Account overrides should require a UUID account identifier."""
    resp = await client.put(
        "/api/v1/admin/feature-flags/optimizer",
        json={"enabled": True, "account_id": "not-a-uuid"},
    )
    assert resp.status_code == 422


async def test_capabilities_reflects_account_override(client: AsyncClient) -> None:
    """The authenticated account override should beat a global disable."""
    global_put = await client.put("/api/v1/admin/feature-flags/optimizer", json={"enabled": False})
    assert global_put.status_code == 200
    account_id = await app.state.db_pool.fetchval(
        "SELECT id FROM accounts WHERE email = $1", "default@test.local"
    )
    put = await client.put(
        "/api/v1/admin/feature-flags/optimizer",
        json={"enabled": True, "account_id": str(account_id)},
    )
    assert put.status_code == 200
    resp = await client.get("/api/v1/capabilities")
    assert resp.json()["data"]["optimizer"] is True


async def test_admin_rejects_unknown_account_override(client: AsyncClient) -> None:
    """Account overrides should fail clearly when the UUID is not an account."""
    resp = await client.put(
        "/api/v1/admin/feature-flags/optimizer",
        json={"enabled": True, "account_id": str(uuid4())},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ACCOUNT_NOT_FOUND"


# ── optimizer endpoint guard ──────────────────────────────────────────────


async def test_optimize_blocked_when_disabled(client: AsyncClient) -> None:
    await _clear_flags(app.state.db_pool)
    deck_id = await _make_deck(client)
    resp = await client.post(f"/api/v1/decks/{deck_id}/playtest/optimize", json={})
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "FEATURE_DISABLED"


async def test_optimize_starts_when_enabled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _clear_flags(app.state.db_pool)
    deck_id = await _make_deck(client)
    await client.put("/api/v1/admin/feature-flags/optimizer", json={"enabled": True})

    app.state.optimizer_jobs = {}

    async def _fake_run_search(*_args: object, **_kwargs: object) -> object:
        return object()

    monkeypatch.setattr("mtg_helper.routers.ai.deck_optimizer_service.run_search", _fake_run_search)

    resp = await client.post(f"/api/v1/decks/{deck_id}/playtest/optimize", json={})
    assert resp.status_code == 202
    assert "job_id" in resp.json()["data"]


async def test_single_flight_rejects_overlapping_run() -> None:
    """A second job started while one holds the semaphore is errored, not run."""
    async with _OPTIMIZE_SEMAPHORE:
        job = optimizer_jobs.OptimizerJob(job_id=uuid4(), account_id=uuid4(), deck_id=uuid4())
        await _run_optimize_job(job, None, None, None, None, OptimizeRequest(), uuid4())

    assert job.status == "error"
    assert job.error is not None
    assert "Another optimization" in job.error
