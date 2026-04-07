"""Admin management endpoints (local dev tools, no auth)."""

from typing import Any

from fastapi import APIRouter, Request

from mtg_helper.services import scryfall
from mtg_helper.services.embedding_service import run_batch_embed
from mtg_helper.services.tag_service import run_batch_tag

router = APIRouter(tags=["admin"])


@router.post("/admin/sync-cards")
async def sync_cards(request: Request) -> dict[str, Any]:
    """Download fresh Scryfall bulk data and upsert into the cards table.

    Returns:
        Summary with cards_processed and duration_seconds.
    """
    return await scryfall.run_sync(
        request.app.state.db_pool,
        request.app.state.ai_client,
        request.app.state.qdrant_client,
    )


@router.post("/admin/embed-cards")
async def embed_cards(request: Request) -> dict[str, Any]:
    """Generate embeddings for all un-embedded cards and upsert into Qdrant.

    Returns:
        Summary with cards_embedded and duration_seconds.
    """
    return await run_batch_embed(
        request.app.state.db_pool,
        request.app.state.ai_client,
        request.app.state.qdrant_client,
    )


@router.post("/admin/tag-cards")
async def tag_cards(request: Request) -> dict[str, Any]:
    """Classify all cards with rule-based tags and persist to the database.

    After tagging, refreshes Qdrant payloads so semantic search filters
    on up-to-date tags.

    Returns:
        Summary with cards_tagged and duration_seconds.
    """
    return await run_batch_tag(
        request.app.state.db_pool,
        request.app.state.qdrant_client,
    )
