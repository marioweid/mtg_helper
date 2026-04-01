"""FastAPI application factory and lifespan management."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import openai
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mtg_helper.config import settings
from mtg_helper.db import close_pool, create_pool
from mtg_helper.routers import accounts, admin, ai, cards, decks, feedback, health, preferences
from mtg_helper.services import scryfall

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage startup and shutdown of shared resources."""
    app.state.db_pool = await create_pool(settings.database_url)
    app.state.ai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    card_count: int = await app.state.db_pool.fetchval("SELECT count(*) FROM cards")
    if card_count == 0:
        _log.info("Cards table is empty — running initial Scryfall sync")
        try:
            result = await scryfall.run_sync(app.state.db_pool)
            _log.info("Scryfall sync complete: %s", result)
        except Exception:
            _log.exception("Scryfall sync failed on startup; continuing without card data")

    yield
    await close_pool(app.state.db_pool)


app = FastAPI(title="MTG Helper API", version="0.1.0", lifespan=lifespan)

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


app.include_router(health.router)
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(cards.router, prefix="/api/v1")
app.include_router(decks.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(preferences.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
