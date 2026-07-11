"""FastAPI application factory and lifespan management."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mtg_helper.auth import get_current_account, require_admin_or_internal
from mtg_helper.config import settings
from mtg_helper.db import apply_schema, close_pool, create_pool
from mtg_helper.observability import configure_logfire
from mtg_helper.routers import (
    admin,
    ai,
    capabilities,
    cards,
    collections,
    decks,
    feedback,
    health,
    me,
    onboarding,
    snapshots,
    tags,
)
from mtg_helper.services import (
    archidekt_tag_service,
    moxfield_hub_service,
    mtgjson,
    scryfall,
    theme_service,
)
from mtg_helper.services.admin_jobs import JobRegistry

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage startup and shutdown of shared resources."""
    app.state.db_pool = await create_pool(settings.database_url)
    await apply_schema(app.state.db_pool)
    app.state.admin_jobs = JobRegistry()
    app.state.optimizer_jobs = {}
    app.state.coach_jobs = {}

    card_count: int = await app.state.db_pool.fetchval("SELECT count(*) FROM cards")
    if card_count == 0:
        _log.info("Cards table is empty — running initial Scryfall sync")
        try:
            result = await scryfall.run_sync(app.state.db_pool)
            _log.info("Scryfall sync complete: %s", result)
        except Exception:
            _log.exception("Scryfall sync failed on startup; continuing without card data")

    keyword_count: int = await app.state.db_pool.fetchval("SELECT count(*) FROM mtgjson_keywords")
    if keyword_count == 0:
        _log.info("MTGJSON keyword catalog is empty - running initial keyword sync")
        try:
            result = await mtgjson.sync_keywords(app.state.db_pool)
            _log.info("MTGJSON keyword sync complete: %s", result)
        except Exception:
            _log.exception("MTGJSON keyword sync failed on startup; continuing with fallback data")

    await _ensure_theme_catalogs(app)

    yield
    await close_pool(app.state.db_pool)


async def _ensure_theme_catalogs(app: FastAPI) -> None:
    """Populate empty source catalogs and seed conservative shared groups."""
    hub_count: int = await app.state.db_pool.fetchval("SELECT count(*) FROM moxfield_hubs")
    if hub_count == 0:
        _log.info("Moxfield hub catalog is empty - running initial hub sync")
        try:
            await moxfield_hub_service.sync_hubs(app.state.db_pool)
        except Exception:
            _log.exception("Moxfield hub sync failed on startup; continuing without hub data")

    archidekt_count: int = await app.state.db_pool.fetchval("SELECT count(*) FROM archidekt_tags")
    if archidekt_count == 0:
        _log.info("Archidekt tag catalog is empty - running initial catalog sync")
        try:
            await archidekt_tag_service.sync_tags(app.state.db_pool)
        except Exception:
            _log.exception("Archidekt tag sync failed on startup; continuing without tag data")
    await theme_service.seed_groups(app.state.db_pool)


app = FastAPI(title="MTG Helper API", version="0.1.0", lifespan=lifespan)
configure_logfire(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Return a consistent error envelope for unhandled exceptions."""
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": str(exc)}},
    )


_authed = [Depends(get_current_account)]
_admin = [Depends(require_admin_or_internal)]

app.include_router(health.router)
app.include_router(me.router, prefix="/api/v1")
app.include_router(capabilities.router, prefix="/api/v1", dependencies=_authed)
app.include_router(cards.router, prefix="/api/v1", dependencies=_authed)
app.include_router(snapshots.router, prefix="/api/v1", dependencies=_authed)
app.include_router(decks.router, prefix="/api/v1", dependencies=_authed)
app.include_router(onboarding.router, prefix="/api/v1", dependencies=_authed)
app.include_router(ai.router, prefix="/api/v1", dependencies=_authed)
app.include_router(feedback.router, prefix="/api/v1", dependencies=_authed)
app.include_router(collections.router, prefix="/api/v1", dependencies=_authed)
app.include_router(tags.router, prefix="/api/v1", dependencies=_authed)
app.include_router(admin.router, prefix="/api/v1", dependencies=_admin)
