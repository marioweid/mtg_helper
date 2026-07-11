"""Admin maintenance endpoints (sync / tag) with progress tracking.

Each ``POST`` returns ``202 Accepted`` immediately and runs the underlying
service in a background task that updates a shared :class:`JobRegistry` on
``app.state.admin_jobs``. The Admin UI polls ``GET /admin/status`` to render
a progress bar per job.
"""

import asyncio
import logging
from dataclasses import asdict
from typing import Any, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from mtg_helper.db import apply_schema
from mtg_helper.services import (
    archidekt_tag_service,
    feature_flag_service,
    moxfield_hub_service,
    mtgjson,
    scryfall,
    theme_service,
)
from mtg_helper.services.admin_jobs import (
    JobRegistry,
    JobState,
    finish_error,
    finish_ok,
    make_progress_cb,
    start,
)
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


@router.post("/admin/sync-moxfield-hubs", status_code=202)
async def sync_moxfield_hubs(request: Request) -> dict[str, Any]:
    """Refresh Moxfield hub catalog and card membership as a background task."""
    job = _registry(request).tag
    _ensure_idle(job)
    start(job)
    asyncio.create_task(
        _wrap(
            job,
            moxfield_hub_service.sync_hub_card_stats(
                request.app.state.db_pool,
                progress=make_progress_cb(job),
            ),
        )
    )
    return _response(job)


@router.post("/admin/sync-archidekt-tags", status_code=202)
async def sync_archidekt_tags(request: Request) -> dict[str, Any]:
    """Refresh Archidekt tag catalog and card membership in the background."""
    job = _registry(request).tag
    _ensure_idle(job)
    start(job)
    asyncio.create_task(
        _wrap(
            job,
            archidekt_tag_service.sync_tag_card_stats(
                request.app.state.db_pool, progress=make_progress_cb(job)
            ),
        )
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
                progress=make_progress_cb(job),
            ),
        )
    )
    return _response(job)


@router.post("/admin/refresh-all", status_code=202)
async def refresh_all(request: Request) -> dict[str, Any]:
    """Run the complete source refresh and card tagging pipeline."""
    job = _registry(request).refresh_all
    _ensure_idle(job)
    start(job)
    asyncio.create_task(_wrap(job, _run_refresh_all(request.app, job)))
    return _response(job)


async def _run_refresh_all(app: FastAPI, job: JobState) -> dict[str, Any]:
    """Chain schema, source syncs, and tagging under one refresh-all job state."""
    cb = make_progress_cb(job)
    cb("applying schema", 0, 1)
    await apply_schema(app.state.db_pool)
    cb("applying schema", 1, 1)
    scryfall_result = await scryfall.run_sync(app.state.db_pool, progress=cb)
    mtgjson_result = await mtgjson.run_sync(app.state.db_pool, progress=cb)
    moxfield_hub_result = await moxfield_hub_service.sync_hub_card_stats(
        app.state.db_pool, progress=cb
    )
    archidekt_result = await archidekt_tag_service.sync_tag_card_stats(
        app.state.db_pool, progress=cb
    )
    await theme_service.seed_groups(app.state.db_pool)
    tag_result = await run_batch_tag(app.state.db_pool, progress=cb)
    return {
        "cards_processed": scryfall_result.get("cards_processed"),
        "mtgjson_cards_processed": mtgjson_result.get("mtgjson_cards_processed"),
        "mtgjson_keywords_processed": mtgjson_result.get("mtgjson_keywords_processed"),
        "moxfield_hubs_processed": moxfield_hub_result.get("moxfield_hubs_processed"),
        "moxfield_hub_cards_matched": moxfield_hub_result.get("moxfield_hub_cards_matched"),
        "archidekt_tags_processed": archidekt_result.get("archidekt_tags_processed"),
        "archidekt_tag_cards_matched": archidekt_result.get("archidekt_tag_cards_matched"),
        "cards_tagged": tag_result.get("cards_tagged"),
    }


@router.get("/admin/status")
async def status(request: Request) -> dict[str, Any]:
    """Return the live state of every admin job slot."""
    registry = _registry(request)
    return {
        "sync": asdict(registry.sync),
        "mtgjson": asdict(registry.mtgjson),
        "tag": asdict(registry.tag),
        "refresh_all": asdict(registry.refresh_all),
    }


class FeatureFlagUpdate(BaseModel):
    """Body for setting a feature flag. Omit ``account_id`` for the global scope."""

    enabled: bool
    account_id: UUID | None = None


class MoxfieldHubManualSync(BaseModel):
    """Manual one-hub Moxfield sync controls."""

    hub_ref: str
    hub_sample_size: int = 10
    baseline_sample_size: int = 80
    deck_ids: list[str] | None = None
    baseline_deck_ids: list[str] | None = None


class ThemeGroupCreate(BaseModel):
    """Fields for creating an editable shared theme group."""

    label: str = Field(min_length=1, max_length=80)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None
    sort_order: int = 0


class ThemeGroupUpdate(BaseModel):
    """Editable shared theme group fields."""

    label: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None
    sort_order: int | None = None
    enabled: bool | None = None
    delete: bool = False


class ThemeMemberUpdate(BaseModel):
    """Assign or unassign one source tag."""

    source: Literal["moxfield", "archidekt"]
    source_id: int
    group_id: int | None = None


class SourceTagUpdate(BaseModel):
    """Administrator availability choice for one upstream tag."""

    enabled: bool


class ArchidektTagManualSync(BaseModel):
    """Manual one-tag Archidekt sync controls."""

    tag_ref: str
    tag_sample_size: int = 10
    baseline_sample_size: int = 80


@router.get("/admin/moxfield-hubs")
async def list_moxfield_hubs(request: Request) -> dict[str, Any]:
    """List active Moxfield hubs for manual admin controls."""
    return {"hubs": await moxfield_hub_service.list_hubs(request.app.state.db_pool)}


@router.post("/admin/sync-moxfield-hub", status_code=202)
async def sync_moxfield_hub_manual(
    body: MoxfieldHubManualSync,
    request: Request,
) -> dict[str, Any]:
    """Refresh one Moxfield hub with optional manual deck samples."""
    job = _registry(request).tag
    _ensure_idle(job)
    start(job)
    asyncio.create_task(
        _wrap(
            job,
            moxfield_hub_service.sync_one_hub_card_stats(
                request.app.state.db_pool,
                hub_ref=body.hub_ref,
                hub_sample_size=body.hub_sample_size,
                baseline_sample_size=body.baseline_sample_size,
                deck_ids=body.deck_ids,
                baseline_deck_ids=body.baseline_deck_ids,
            ),
        )
    )
    return _response(job)


@router.get("/admin/themes")
async def list_themes_admin(request: Request) -> dict[str, Any]:
    """List shared groups and raw source tags."""
    return await theme_service.list_admin_state(request.app.state.db_pool)


@router.post("/admin/theme-groups", status_code=201)
async def create_theme_group(body: ThemeGroupCreate, request: Request) -> dict[str, Any]:
    """Create a shared theme group."""
    try:
        return await theme_service.create_group(request.app.state.db_pool, body.model_dump())
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, "A theme group with that slug already exists") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/admin/theme-groups/{group_id}")
async def update_theme_group(
    group_id: int, body: ThemeGroupUpdate, request: Request
) -> dict[str, Any]:
    """Edit, disable, or soft-delete a shared theme group."""
    await theme_service.update_group(
        request.app.state.db_pool, group_id, body.model_dump(exclude_unset=True)
    )
    return {"id": group_id, "updated": True}


@router.post("/admin/theme-groups/{group_id}/restore")
async def restore_theme_group(group_id: int, request: Request) -> dict[str, Any]:
    """Restore a soft-deleted shared group."""
    await theme_service.restore_group(request.app.state.db_pool, group_id)
    return {"id": group_id, "restored": True}


@router.put("/admin/theme-membership")
async def set_theme_membership(body: ThemeMemberUpdate, request: Request) -> dict[str, Any]:
    """Assign, move, or unassign one source tag."""
    try:
        await theme_service.assign_member(
            request.app.state.db_pool, body.group_id, body.source, body.source_id
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"updated": True}


@router.patch("/admin/theme-sources/{source}/{source_id}")
async def update_theme_source(
    source: str, source_id: int, body: SourceTagUpdate, request: Request
) -> dict[str, Any]:
    """Enable or disable one Moxfield hub or Archidekt tag."""
    try:
        await theme_service.set_source_enabled(
            request.app.state.db_pool, source, source_id, body.enabled
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"source": source, "source_id": source_id, "enabled": body.enabled}


@router.post("/admin/sync-archidekt-tag", status_code=202)
async def sync_archidekt_tag_manual(
    body: ArchidektTagManualSync, request: Request
) -> dict[str, Any]:
    """Refresh one Archidekt tag using configurable sample sizes."""
    job = _registry(request).tag
    _ensure_idle(job)
    start(job)
    asyncio.create_task(
        _wrap(
            job,
            archidekt_tag_service.sync_one_tag_card_stats(
                request.app.state.db_pool,
                tag_ref=body.tag_ref,
                tag_sample_size=body.tag_sample_size,
                baseline_sample_size=body.baseline_sample_size,
            ),
        )
    )
    return _response(job)


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
