"""FastAPI application factory and lifespan management."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from qdrant_client import AsyncQdrantClient

from mtg_helper.auth import get_current_account, get_current_admin
from mtg_helper.config import settings
from mtg_helper.db import apply_schema, close_pool, create_pool
from mtg_helper.routers import (
    admin,
    ai,
    cards,
    collections,
    decks,
    feedback,
    health,
    me,
)
from mtg_helper.services import scryfall
from mtg_helper.services.embedding_service import ensure_collection
from mtg_helper.services.llm_client import LLMClient

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage startup and shutdown of shared resources."""
    app.state.db_pool = await create_pool(settings.database_url)
    await apply_schema(app.state.db_pool)
    app.state.ai_client = LLMClient(
        api_key=settings.gemini_api_key,
        chat_model=settings.chat_model,
        embed_model=settings.embedding_model,
        embed_dim=settings.embedding_dimensions,
    )
    app.state.qdrant_client = AsyncQdrantClient(url=settings.qdrant_url)
    await ensure_collection(app.state.qdrant_client)

    card_count: int = await app.state.db_pool.fetchval("SELECT count(*) FROM cards")
    if card_count == 0:
        _log.info("Cards table is empty — running initial Scryfall sync")
        try:
            result = await scryfall.run_sync(
                app.state.db_pool,
                app.state.ai_client,
                app.state.qdrant_client,
            )
            _log.info("Scryfall sync complete: %s", result)
        except Exception:
            _log.exception("Scryfall sync failed on startup; continuing without card data")

    yield
    await app.state.qdrant_client.close()
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


_authed = [Depends(get_current_account)]
_admin = [Depends(get_current_admin)]

app.include_router(health.router)
app.include_router(me.router, prefix="/api/v1")
app.include_router(cards.router, prefix="/api/v1", dependencies=_authed)
app.include_router(decks.router, prefix="/api/v1", dependencies=_authed)
app.include_router(ai.router, prefix="/api/v1", dependencies=_authed)
app.include_router(feedback.router, prefix="/api/v1", dependencies=_authed)
app.include_router(collections.router, prefix="/api/v1", dependencies=_authed)
app.include_router(admin.router, prefix="/api/v1", dependencies=_admin)
