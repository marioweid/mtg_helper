"""Admin maintenance endpoints (sync / tag / embed) with progress tracking.

Each ``POST`` returns ``202 Accepted`` immediately and runs the underlying
service in a background task that updates a shared :class:`JobRegistry` on
``app.state.admin_jobs``. The Admin UI polls ``GET /admin/status`` to render
a progress bar per job.
"""

import asyncio
import logging
from dataclasses import asdict
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel

from mtg_helper.services import edhrec_tag_catalog_service, feature_flag_service, mtgjson, scryfall
from mtg_helper.services.admin_jobs import (
    JobRegistry,
    JobState,
    finish_error,
    finish_ok,
    make_progress_cb,
    start,
)
from mtg_helper.services.embedding_service import run_batch_embed
from mtg_helper.services.tag_service import run_batch_tag

router = APIRouter(tags=["admin"])

_log = logging.getLogger(__name__)


def _registry(request: Request) -> JobRegistry:
    """Return the app-wide job registry."""
    return request.app.state.admin_jobs


def _ensure_idle(job: JobState) -> None:
    """Reject the request if this job slot is already busy."""
    if job.status == "running":
        raise HTTPException(409, f"{job.key} is already running")


def _response(job: JobState) -> dict[str, Any]:
    """Standard 202 body for a kicked-off job."""
    return {"job": job.key, "started_at": job.started_at.isoformat() if job.started_at else None}


async def _wrap(job: JobState, coro: Any) -> None:
    """Run ``coro`` and translate the outcome into the job's status fields."""
    try:
        result = await coro
        finish_ok(job, result if isinstance(result, dict) else None)
    except Exception as exc:
        _log.exception("Admin job %s failed", job.key)
        finish_error(job, str(exc))


@router.post("/admin/sync-cards", status_code=202)
async def sync_cards(request: Request) -> dict[str, Any]:
    """Kick off a Scryfall bulk-data sync as a background task."""
    job = _registry(request).sync
    _ensure_idle(job)
    start(job)
    asyncio.create_task(
        _wrap(job, scryfall.run_sync(request.app.state.db_pool, progress=make_progress_cb(job)))
    )
    return _response(job)


@router.post("/admin/sync-mtgjson", status_code=202)
async def sync_mtgjson(request: Request) -> dict[str, Any]:
    """Kick off MTGJSON sidecar metadata sync + diff as a background task."""
    job = _registry(request).mtgjson
    _ensure_idle(job)
    start(job)
    asyncio.create_task(
        _wrap(job, mtgjson.run_sync(request.app.state.db_pool, progress=make_progress_cb(job)))
    )
    return _response(job)


@router.post("/admin/sync-edhrec-tags", status_code=202)
async def sync_edhrec_tags(request: Request) -> dict[str, Any]:
    """Refresh the local EDHREC tag catalog as a background task."""
    job = _registry(request).tag
    _ensure_idle(job)
    start(job)
    asyncio.create_task(
        _wrap(job, edhrec_tag_catalog_service.sync_edhrec_tags(request.app.state.db_pool))
    )
    return _response(job)


@router.post("/admin/tag-cards", status_code=202)
async def tag_cards(request: Request) -> dict[str, Any]:
    """Kick off a rule-based tagging pass as a background task."""
    job = _registry(request).tag
    _ensure_idle(job)
    start(job)
    asyncio.create_task(
        _wrap(
            job,
            run_batch_tag(
                request.app.state.db_pool,
                request.app.state.qdrant_client,
                progress=make_progress_cb(job),
            ),
        )
    )
    return _response(job)


@router.post("/admin/embed-cards", status_code=202)
async def embed_cards(request: Request) -> dict[str, Any]:
    """Kick off Gemini embedding generation as a background task."""
    job = _registry(request).embed
    _ensure_idle(job)
    start(job)
    asyncio.create_task(
        _wrap(
            job,
            run_batch_embed(
                request.app.state.db_pool,
                request.app.state.ai_client,
                request.app.state.qdrant_client,
                progress=make_progress_cb(job),
            ),
        )
    )
    return _response(job)


@router.post("/admin/refresh-all", status_code=202)
async def refresh_all(request: Request) -> dict[str, Any]:
    """Run sync → tag → embed sequentially under one job slot."""
    job = _registry(request).refresh_all
    _ensure_idle(job)
    start(job)
    asyncio.create_task(_wrap(job, _run_refresh_all(request.app, job)))
    return _response(job)


async def _run_refresh_all(app: FastAPI, job: JobState) -> dict[str, Any]:
    """Chain sync, tag, and embed under the single refresh-all job state."""
    cb = make_progress_cb(job)
    sync_result = await scryfall.run_sync(app.state.db_pool, progress=cb)
    tag_result = await run_batch_tag(app.state.db_pool, app.state.qdrant_client, progress=cb)
    embed_result = await run_batch_embed(
        app.state.db_pool, app.state.ai_client, app.state.qdrant_client, progress=cb
    )
    return {
        "cards_processed": sync_result.get("cards_processed"),
        "cards_tagged": tag_result.get("cards_tagged"),
        "cards_embedded": embed_result.get("cards_embedded"),
    }


@router.get("/admin/status")
async def status(request: Request) -> dict[str, Any]:
    """Return the live state of every admin job slot."""
    registry = _registry(request)
    return {
        "sync": asdict(registry.sync),
        "mtgjson": asdict(registry.mtgjson),
        "tag": asdict(registry.tag),
        "embed": asdict(registry.embed),
        "refresh_all": asdict(registry.refresh_all),
    }


class FeatureFlagUpdate(BaseModel):
    """Body for setting a feature flag. Omit ``account_id`` for the global scope."""

    enabled: bool
    account_id: UUID | None = None


@router.get("/admin/feature-flags")
async def list_feature_flags(request: Request) -> dict[str, Any]:
    """List all feature-flag override rows (global rows first)."""
    return {"flags": await feature_flag_service.list_flags(request.app.state.db_pool)}


@router.put("/admin/feature-flags/{flag}")
async def set_feature_flag(
    flag: feature_flag_service.FeatureFlag, body: FeatureFlagUpdate, request: Request
) -> dict[str, Any]:
    """Set a global or per-account override for ``flag``."""
    try:
        await feature_flag_service.set_flag(
            request.app.state.db_pool, flag, body.enabled, body.account_id
        )
    except asyncpg.ForeignKeyViolationError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ACCOUNT_NOT_FOUND",
                "message": f"Account {body.account_id} does not exist",
            },
        ) from exc
    return {"flag": flag, "enabled": body.enabled, "account_id": body.account_id}


@router.delete("/admin/feature-flags/{flag}")
async def clear_feature_flag(
    flag: feature_flag_service.FeatureFlag, request: Request, account_id: UUID | None = None
) -> dict[str, Any]:
    """Clear a global (default) or per-account override, reverting to env default."""
    await feature_flag_service.clear_flag(request.app.state.db_pool, flag, account_id)
    return {"flag": flag, "cleared": True, "account_id": account_id}
