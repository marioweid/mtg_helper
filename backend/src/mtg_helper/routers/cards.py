"""Card search and retrieval endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from mtg_helper.models.cards import CardResponse, CardSearchParams
from mtg_helper.models.common import DataResponse, PaginationMeta
from mtg_helper.services import card_service, scryfall

router = APIRouter(prefix="/cards", tags=["cards"])


def _search_params(
    q: str | None = Query(default=None),
    color_identity: str | None = Query(default=None),
    type: str | None = Query(default=None),
    cmc_min: float | None = Query(default=None),
    cmc_max: float | None = Query(default=None),
    keywords: str | None = Query(default=None),
    commander_legal: bool = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CardSearchParams:
    """Parse card search query parameters."""
    return CardSearchParams(
        q=q,
        color_identity=color_identity,
        type=type,
        cmc_min=cmc_min,
        cmc_max=cmc_max,
        keywords=keywords,
        commander_legal=commander_legal,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=DataResponse[list[CardResponse]])
async def search_cards(
    request: Request,
    params: CardSearchParams = Depends(_search_params),
) -> DataResponse[list[CardResponse]]:
    """Search cards with optional filters."""
    cards, total = await card_service.search_cards(request.app.state.db_pool, params)
    return DataResponse(
        data=cards,
        meta=PaginationMeta(total=total, limit=params.limit, offset=params.offset),
    )


@router.get("/{scryfall_id}", response_model=DataResponse[CardResponse])
async def get_card(
    scryfall_id: UUID,
    request: Request,
) -> DataResponse[CardResponse]:
    """Get a card by its Scryfall ID."""
    card = await card_service.get_card_by_scryfall_id(request.app.state.db_pool, scryfall_id)
    if card is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CARD_NOT_FOUND", "message": f"Card {scryfall_id} not found"},
        )
    return DataResponse(data=card)


@router.post("/sync")
async def sync_cards(request: Request) -> JSONResponse:
    """Trigger a Scryfall bulk data sync. Downloads and upserts all Commander-legal cards."""
    result = await scryfall.run_sync(request.app.state.db_pool)
    return JSONResponse(status_code=202, content={"data": result})
