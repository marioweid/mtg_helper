"""Deck CRUD endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from mtg_helper.models.common import DataResponse, PaginationMeta
from mtg_helper.models.decks import (
    DeckCardAdd,
    DeckCardResponse,
    DeckCreate,
    DeckDetailResponse,
    DeckResponse,
    DeckSummary,
    DeckUpdate,
)
from mtg_helper.services import deck_service
from mtg_helper.services.deck_service import (
    CardNotFoundError,
    ColorIdentityError,
    DeckNotFoundError,
)

router = APIRouter(prefix="/decks", tags=["decks"])


def _not_found(deck_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "DECK_NOT_FOUND", "message": f"Deck {deck_id} not found"},
    )


@router.get("", response_model=DataResponse[list[DeckSummary]])
async def list_decks(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DataResponse[list[DeckSummary]]:
    """List all decks with commander info and card count."""
    decks, total = await deck_service.list_decks(request.app.state.db_pool, limit, offset)
    return DataResponse(data=decks, meta=PaginationMeta(total=total, limit=limit, offset=offset))


@router.post("", response_model=DataResponse[DeckResponse], status_code=201)
async def create_deck(
    body: DeckCreate,
    request: Request,
) -> DataResponse[DeckResponse]:
    """Create a new deck."""
    try:
        deck = await deck_service.create_deck(request.app.state.db_pool, body)
    except CardNotFoundError as e:
        raise HTTPException(status_code=422, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
    return DataResponse(data=deck)


@router.get("/{deck_id}", response_model=DataResponse[DeckDetailResponse])
async def get_deck(
    deck_id: UUID,
    request: Request,
) -> DataResponse[DeckDetailResponse]:
    """Get a deck with all its cards."""
    deck = await deck_service.get_deck(request.app.state.db_pool, deck_id)
    if deck is None:
        raise _not_found(deck_id)
    return DataResponse(data=deck)


@router.patch("/{deck_id}", response_model=DataResponse[DeckResponse])
async def update_deck(
    deck_id: UUID,
    body: DeckUpdate,
    request: Request,
) -> DataResponse[DeckResponse]:
    """Update deck metadata."""
    deck = await deck_service.update_deck(request.app.state.db_pool, deck_id, body)
    if deck is None:
        raise _not_found(deck_id)
    return DataResponse(data=deck)


@router.delete("/{deck_id}", status_code=204)
async def delete_deck(
    deck_id: UUID,
    request: Request,
) -> Response:
    """Delete a deck and all its cards."""
    deleted = await deck_service.delete_deck(request.app.state.db_pool, deck_id)
    if not deleted:
        raise _not_found(deck_id)
    return Response(status_code=204)


@router.post("/{deck_id}/cards", response_model=DataResponse[DeckCardResponse], status_code=201)
async def add_card(
    deck_id: UUID,
    body: DeckCardAdd,
    request: Request,
) -> DataResponse[DeckCardResponse]:
    """Add a card to a deck, enforcing color identity rules."""
    try:
        card = await deck_service.add_card_to_deck(request.app.state.db_pool, deck_id, body)
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    except CardNotFoundError as e:
        raise HTTPException(status_code=422, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
    except ColorIdentityError as e:
        raise HTTPException(
            status_code=422, detail={"code": "COLOR_IDENTITY_VIOLATION", "message": str(e)}
        )
    return DataResponse(data=card)


@router.delete("/{deck_id}/cards/{scryfall_id}", status_code=204)
async def remove_card(
    deck_id: UUID,
    scryfall_id: UUID,
    request: Request,
) -> Response:
    """Remove a card from a deck by its Scryfall ID."""
    removed = await deck_service.remove_card_from_deck(
        request.app.state.db_pool, deck_id, scryfall_id
    )
    if not removed:
        raise HTTPException(
            status_code=404,
            detail={"code": "CARD_NOT_IN_DECK", "message": f"Card {scryfall_id} not in deck"},
        )
    return Response(status_code=204)
