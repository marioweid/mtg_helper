"""Deck CRUD endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.brackets import BracketValidationResponse
from mtg_helper.models.combos import ComboListResponse
from mtg_helper.models.common import DataResponse, PaginationMeta
from mtg_helper.models.decks import (
    DeckCardAdd,
    DeckCardResponse,
    DeckCreate,
    DeckDetailResponse,
    DeckImportRequest,
    DeckImportResponse,
    DeckResponse,
    DeckSummary,
    DeckUpdate,
    DeckUrlImportRequest,
)
from mtg_helper.services import (
    bracket_service,
    combo_service,
    deck_service,
    deck_url_import_service,
    import_service,
)
from mtg_helper.services.combo_service import ComboFetchError
from mtg_helper.services.deck_service import (
    CardNotFoundError,
    ColorIdentityError,
    DeckNotFoundError,
)
from mtg_helper.services.deck_url_import_service import (
    DeckFetchError,
    UnsupportedDeckUrlError,
)

router = APIRouter(prefix="/decks", tags=["decks"])

CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]


def _not_found(deck_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "DECK_NOT_FOUND", "message": f"Deck {deck_id} not found"},
    )


def _require_email(account: AccountResponse) -> str:
    """Return the account's email or raise 403 if missing.

    Auth strips tokens without an ``email`` claim, so this is defensive only.
    """
    if not account.email:
        raise HTTPException(
            status_code=403,
            detail={"code": "EMAIL_REQUIRED", "message": "Account has no email"},
        )
    return account.email


@router.get("", response_model=DataResponse[list[DeckSummary]])
async def list_decks(
    request: Request,
    account: CurrentAccount,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DataResponse[list[DeckSummary]]:
    """List the authenticated account's decks with commander info and card count."""
    email = _require_email(account)
    decks, total = await deck_service.list_decks(request.app.state.db_pool, email, limit, offset)
    return DataResponse(data=decks, meta=PaginationMeta(total=total, limit=limit, offset=offset))


@router.post("", response_model=DataResponse[DeckResponse], status_code=201)
async def create_deck(
    body: DeckCreate,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DeckResponse]:
    """Create a new deck owned by the authenticated account."""
    email = _require_email(account)
    try:
        deck = await deck_service.create_deck(request.app.state.db_pool, body, email)
    except CardNotFoundError as e:
        raise HTTPException(status_code=422, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
    return DataResponse(data=deck)


@router.post("/import", response_model=DataResponse[DeckImportResponse], status_code=201)
async def import_deck(
    body: DeckImportRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DeckImportResponse]:
    """Import a deck from a pasted deck list.

    Accepts Moxfield, MTGO, TappedOut, and similar text formats.
    The deck is created with stage 'complete', skipping the build wizard.
    Mark the commander with *CMDR* at the end of its line.
    """
    email = _require_email(account)
    try:
        result = await import_service.import_deck(request.app.state.db_pool, body, email)
    except CardNotFoundError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "COMMANDER_NOT_FOUND", "message": str(e)},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "PARSE_ERROR", "message": str(e)},
        )
    return DataResponse(data=result)


@router.post(
    "/import-url",
    response_model=DataResponse[DeckImportResponse],
    status_code=201,
)
async def import_deck_from_url(
    body: DeckUrlImportRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DeckImportResponse]:
    """Import a deck from a Moxfield or Archidekt URL.

    Fetches the deck from the source's public API and persists it locally with
    stage 'complete'. The deck's name comes from the source unless overridden.
    """
    email = _require_email(account)
    try:
        result = await deck_url_import_service.import_from_url(
            request.app.state.db_pool,
            str(body.url),
            email,
            name_override=body.name,
            description_override=body.description,
            bracket=body.bracket,
        )
    except UnsupportedDeckUrlError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "UNSUPPORTED_URL", "message": str(e)},
        )
    except CardNotFoundError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "COMMANDER_NOT_FOUND", "message": str(e)},
        )
    except DeckFetchError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "UPSTREAM_FETCH_FAILED", "message": str(e)},
        )
    return DataResponse(data=result)


@router.get("/{deck_id}", response_model=DataResponse[DeckDetailResponse])
async def get_deck(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DeckDetailResponse]:
    """Get a deck with all its cards."""
    email = _require_email(account)
    deck = await deck_service.get_deck(request.app.state.db_pool, deck_id, email)
    if deck is None:
        raise _not_found(deck_id)
    return DataResponse(data=deck)


@router.get(
    "/{deck_id}/bracket-validation",
    response_model=DataResponse[BracketValidationResponse],
)
async def validate_deck_bracket(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[BracketValidationResponse]:
    """Validate a deck against the rules for its declared bracket.

    Pulls active combos from Commander Spellbook on a best-effort basis;
    a Spellbook failure degrades to combo-blind validation rather than 502.
    """
    email = _require_email(account)
    pool = request.app.state.db_pool
    deck = await deck_service.get_deck(pool, deck_id, email)
    if deck is None:
        raise _not_found(deck_id)
    try:
        combos = await combo_service.fetch_combos(pool, deck)
    except ComboFetchError:
        combos = None
    return DataResponse(data=bracket_service.validate_bracket(deck, combos))


@router.get("/{deck_id}/combos", response_model=DataResponse[ComboListResponse])
async def get_deck_combos(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[ComboListResponse]:
    """Active and almost-there (one card missing) combos for the deck."""
    email = _require_email(account)
    pool = request.app.state.db_pool
    deck = await deck_service.get_deck(pool, deck_id, email)
    if deck is None:
        raise _not_found(deck_id)
    try:
        combos = await combo_service.fetch_combos(pool, deck)
    except ComboFetchError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "UPSTREAM_FETCH_FAILED", "message": str(e)},
        )
    return DataResponse(data=combos)


@router.patch("/{deck_id}", response_model=DataResponse[DeckResponse])
async def update_deck(
    deck_id: UUID,
    body: DeckUpdate,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DeckResponse]:
    """Update deck metadata."""
    email = _require_email(account)
    deck = await deck_service.update_deck(request.app.state.db_pool, deck_id, body, email)
    if deck is None:
        raise _not_found(deck_id)
    return DataResponse(data=deck)


@router.delete("/{deck_id}", status_code=204)
async def delete_deck(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> Response:
    """Delete a deck and all its cards."""
    email = _require_email(account)
    deleted = await deck_service.delete_deck(request.app.state.db_pool, deck_id, email)
    if not deleted:
        raise _not_found(deck_id)
    return Response(status_code=204)


@router.post("/{deck_id}/cards", response_model=DataResponse[DeckCardResponse], status_code=201)
async def add_card(
    deck_id: UUID,
    body: DeckCardAdd,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DeckCardResponse]:
    """Add a card to a deck, enforcing color identity rules."""
    email = _require_email(account)
    try:
        card = await deck_service.add_card_to_deck(request.app.state.db_pool, deck_id, body, email)
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    except CardNotFoundError as e:
        raise HTTPException(status_code=422, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
    except ColorIdentityError as e:
        raise HTTPException(
            status_code=422, detail={"code": "COLOR_IDENTITY_VIOLATION", "message": str(e)}
        )
    return DataResponse(data=card)


class DeckCardCategoryUpdate(BaseModel):
    """Request body for changing a card's category tags."""

    categories: list[str] = Field(default_factory=list, max_length=10)


@router.patch("/{deck_id}/cards/{scryfall_id}", status_code=204)
async def update_card_categories(
    deck_id: UUID,
    scryfall_id: UUID,
    body: DeckCardCategoryUpdate,
    request: Request,
    account: CurrentAccount,
) -> Response:
    """Replace a card's category tag set within the deck.

    A card may belong to multiple categories (e.g. ramp + draw). An empty list
    clears all manual categories — auto-bucketing via qualifying_stages still
    applies in the wizard view.
    """
    email = _require_email(account)
    updated = await deck_service.update_deck_card_categories(
        request.app.state.db_pool, deck_id, scryfall_id, body.categories, email
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail={"code": "CARD_NOT_IN_DECK", "message": f"Card {scryfall_id} not in deck"},
        )
    return Response(status_code=204)


@router.delete("/{deck_id}/cards/{scryfall_id}", status_code=204)
async def remove_card(
    deck_id: UUID,
    scryfall_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> Response:
    """Remove a card from a deck by its Scryfall ID."""
    email = _require_email(account)
    removed = await deck_service.remove_card_from_deck(
        request.app.state.db_pool, deck_id, scryfall_id, email
    )
    if not removed:
        raise HTTPException(
            status_code=404,
            detail={"code": "CARD_NOT_IN_DECK", "message": f"Card {scryfall_id} not in deck"},
        )
    return Response(status_code=204)
