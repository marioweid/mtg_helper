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
    PlannedDeckChange,
    PlannedDeckChangeComplete,
    PlannedDeckChangeCreate,
    PlannedDeckChangeUpdate,
    PlannedShoppingListRequest,
)
from mtg_helper.services import (
    bracket_service,
    combo_service,
    deck_service,
    deck_url_import_service,
    import_service,
    planned_change_service,
    revision_service,
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
from mtg_helper.services.planned_change_service import (
    InsufficientQuantityError,
    InvalidPlanError,
    PlanNotFoundError,
    SelectedCollectionError,
)
from mtg_helper.services.revision_service import RevisionCommand

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


def _planned_change_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PlanNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "PLANNED_CHANGE_NOT_FOUND", "message": str(exc)},
        )
    if isinstance(exc, InsufficientQuantityError):
        return HTTPException(
            status_code=409,
            detail={"code": "INSUFFICIENT_QUANTITY", "message": str(exc)},
        )
    code = "INVALID_COLLECTION" if isinstance(exc, SelectedCollectionError) else "INVALID_PLAN"
    return HTTPException(status_code=422, detail={"code": code, "message": str(exc)})


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
    deck = await deck_service.get_deck(
        request.app.state.db_pool, deck_id, email, account_id=account.id
    )
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


@router.get(
    "/{deck_id}/planned-changes",
    response_model=DataResponse[list[PlannedDeckChange]],
)
async def list_planned_changes(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[list[PlannedDeckChange]]:
    """List pending main-deck changes without altering physical composition."""
    try:
        plans = await planned_change_service.list_plans(
            request.app.state.db_pool,
            deck_id,
            _require_email(account),
            account.id,
        )
    except PlanNotFoundError as exc:
        raise _planned_change_error(exc) from exc
    return DataResponse(data=plans)


@router.post(
    "/{deck_id}/planned-changes",
    response_model=DataResponse[PlannedDeckChange | None],
    status_code=201,
)
async def create_planned_change(
    deck_id: UUID,
    body: PlannedDeckChangeCreate,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[PlannedDeckChange | None]:
    """Create, increment, or offset a pending main-deck change."""
    try:
        plan = await planned_change_service.create_plan(
            request.app.state.db_pool,
            deck_id,
            body,
            _require_email(account),
            account.id,
        )
    except (PlanNotFoundError, InvalidPlanError) as exc:
        raise _planned_change_error(exc) from exc
    return DataResponse(data=plan)


@router.post("/{deck_id}/planned-changes/shopping-list")
async def export_planned_shopping_list(
    deck_id: UUID,
    body: PlannedShoppingListRequest,
    request: Request,
    account: CurrentAccount,
) -> Response:
    """Export planned-addition deficits using only selected collection inventory."""
    try:
        text = await planned_change_service.export_shopping_list(
            request.app.state.db_pool,
            deck_id,
            _require_email(account),
            account.id,
            body.collection_ids,
        )
    except (PlanNotFoundError, SelectedCollectionError) as exc:
        raise _planned_change_error(exc) from exc
    return Response(content=text, media_type="text/plain")


@router.patch(
    "/{deck_id}/planned-changes/{plan_id}",
    response_model=DataResponse[PlannedDeckChange],
)
async def update_planned_change(
    deck_id: UUID,
    plan_id: UUID,
    body: PlannedDeckChangeUpdate,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[PlannedDeckChange]:
    """Update pending quantity or its optional inline collection selection."""
    try:
        plan = await planned_change_service.update_plan(
            request.app.state.db_pool,
            deck_id,
            plan_id,
            _require_email(account),
            account.id,
            quantity=body.quantity,
            collection_id=body.collection_id,
            set_collection="collection_id" in body.model_fields_set,
        )
    except (PlanNotFoundError, InvalidPlanError, SelectedCollectionError) as exc:
        raise _planned_change_error(exc) from exc
    return DataResponse(data=plan)


@router.delete("/{deck_id}/planned-changes/{plan_id}", status_code=204)
async def cancel_planned_change(
    deck_id: UUID,
    plan_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> Response:
    """Cancel a plan without changing physical deck or inventory state."""
    try:
        await planned_change_service.cancel_plan(
            request.app.state.db_pool,
            deck_id,
            plan_id,
            _require_email(account),
        )
    except PlanNotFoundError as exc:
        raise _planned_change_error(exc) from exc
    return Response(status_code=204)


@router.post(
    "/{deck_id}/planned-changes/{plan_id}/complete",
    response_model=DataResponse[PlannedDeckChange | None],
)
async def complete_planned_change(
    deck_id: UUID,
    plan_id: UUID,
    body: PlannedDeckChangeComplete,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[PlannedDeckChange | None]:
    """Complete physical copies atomically with an optional collection move."""
    try:
        command = RevisionCommand(
            plan_ids=[plan_id],
            title=None,
            source="single_plan",
            quantities={plan_id: body.quantity},
        )
        await revision_service.apply_revision(
            request.app.state.db_pool,
            deck_id,
            command,
            _require_email(account),
            account.id,
        )
        try:
            plan = await planned_change_service.get_plan(
                request.app.state.db_pool,
                deck_id,
                plan_id,
                _require_email(account),
                account.id,
            )
        except PlanNotFoundError:
            plan = None
    except (
        PlanNotFoundError,
        InvalidPlanError,
        SelectedCollectionError,
        InsufficientQuantityError,
    ) as exc:
        raise _planned_change_error(exc) from exc
    return DataResponse(data=plan)


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


class DeckCardQuantityUpdate(BaseModel):
    """Request body for changing a card's quantity within a deck."""

    quantity: int = Field(ge=1, le=99)


@router.patch("/{deck_id}/cards/{scryfall_id}/quantity", status_code=204)
async def update_card_quantity(
    deck_id: UUID,
    scryfall_id: UUID,
    body: DeckCardQuantityUpdate,
    request: Request,
    account: CurrentAccount,
) -> Response:
    """Set the quantity of a card in the deck.

    Primary use case is basic-land tuning where the same card legitimately
    appears many times. Returns 404 when the card isn't in the deck.
    """
    email = _require_email(account)
    updated = await deck_service.update_deck_card_quantity(
        request.app.state.db_pool, deck_id, scryfall_id, body.quantity, email
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail={"code": "CARD_NOT_IN_DECK", "message": f"Card {scryfall_id} not in deck"},
        )
    return Response(status_code=204)


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
