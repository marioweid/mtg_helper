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
from mtg_helper.observability import configure_assay, shutdown_assay
from mtg_helper.routers import (
    admin,
    ai,
    capabilities,
    cards,
    collections,
    decks,
    health,
    me,
    new_cards,
    onboarding,
    recommendations,
    revisions,
    snapshots,
    tags,
)
from mtg_helper.services import (
    oracle_duplicate_repair_service,
    scryfall,
)
from mtg_helper.services.admin_jobs import JobRegistry
from mtg_helper.services.new_cards.repository import NewCardsError
from mtg_helper.services.recommendations.repository import DiscoveryError

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Close tracing on normal shutdown and failed application startup alike."""
    try:
        async with _application_lifespan(app):
            yield
    finally:
        await shutdown_assay(app)


@asynccontextmanager
async def _application_lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage startup and shutdown of shared resources."""
    app.state.db_pool = await create_pool(settings.database_url)
    app.state.admin_jobs = JobRegistry()
    app.state.optimizer_jobs = {}
    app.state.coach_jobs = {}
    try:
        if settings.run_startup_maintenance:
            await _run_startup_maintenance(app)
        else:
            _log.warning("Startup maintenance disabled; normal application writes remain enabled")
        yield
    finally:
        await close_pool(app.state.db_pool)


async def _run_startup_maintenance(app: FastAPI) -> None:
    """Initialize isolated or production deployments, never shared live development."""
    await apply_schema(app.state.db_pool)

    card_count: int = await app.state.db_pool.fetchval("SELECT count(*) FROM cards")
    if card_count == 0:
        _log.info("Cards table is empty — running initial Scryfall sync")
        try:
            result = await scryfall.run_sync(app.state.db_pool)
            _log.info("Scryfall sync complete: %s", result)
        except Exception:
            _log.exception("Scryfall sync failed on startup; continuing without card data")

    try:
        await oracle_duplicate_repair_service.repair_active_decks(app.state.db_pool)
    except Exception:
        _log.exception("Oracle card identity repair failed; it will retry on next startup")


app = FastAPI(title="MTG Helper API", version="0.1.0", lifespan=lifespan)
configure_assay(app, settings)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NewCardsError)
async def new_cards_error_handler(_request: Request, exc: NewCardsError) -> JSONResponse:
    """Return actionable pilot failures without exposing private model/provider output."""
    return JSONResponse(
        status_code=exc.status, content={"error": {"code": "NEW_CARDS_ERROR", "message": str(exc)}}
    )


@app.exception_handler(DiscoveryError)
async def discovery_error_handler(_request: Request, exc: DiscoveryError) -> JSONResponse:
    """Return bounded actionable pilot errors without exposing private provider fragments."""
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": "DISCOVERY_ERROR", "message": str(exc)}},
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
app.include_router(revisions.router, prefix="/api/v1", dependencies=_authed)
app.include_router(decks.router, prefix="/api/v1", dependencies=_authed)
app.include_router(new_cards.router, prefix="/api/v1", dependencies=_authed)
app.include_router(recommendations.router, prefix="/api/v1", dependencies=_authed)
app.include_router(onboarding.router, prefix="/api/v1", dependencies=_authed)
app.include_router(ai.router, prefix="/api/v1", dependencies=_authed)
app.include_router(collections.router, prefix="/api/v1", dependencies=_authed)
app.include_router(tags.router, prefix="/api/v1", dependencies=_authed)
app.include_router(admin.router, prefix="/api/v1", dependencies=_admin)
