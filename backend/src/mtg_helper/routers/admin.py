"""Admin management endpoints (local dev tools, no auth)."""

from typing import Any

from fastapi import APIRouter, Request

from mtg_helper.services import scryfall

router = APIRouter(tags=["admin"])


@router.post("/admin/sync-cards")
async def sync_cards(request: Request) -> dict[str, Any]:
    """Download fresh Scryfall bulk data and upsert into the cards table.

    Returns:
        Summary with cards_processed and duration_seconds.
    """
    return await scryfall.run_sync(request.app.state.db_pool)
