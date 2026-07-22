"""Deck revision endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.common import DataResponse
from mtg_helper.models.revisions import DeckRevision, DeckRevisionCreate, DeckRevisionUpdate
from mtg_helper.services import revision_service
from mtg_helper.services.planned_change_service import (
    InsufficientQuantityError,
    InvalidPlanError,
    PlanNotFoundError,
    SelectedCollectionError,
)
from mtg_helper.services.revision_service import RevisionCommand, RevisionNotFoundError

router = APIRouter(tags=["revisions"])
CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]


def _email(account: AccountResponse) -> str:
    if not account.email:
        raise HTTPException(
            status_code=403,
            detail={"code": "EMAIL_REQUIRED", "message": "Account has no email"},
        )
    return account.email


def revision_error(exc: Exception) -> HTTPException:
    """Map revision domain errors to stable API error codes."""
    if isinstance(exc, PlanNotFoundError | RevisionNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "REVISION_RESOURCE_NOT_FOUND", "message": str(exc)},
        )
    if isinstance(exc, InsufficientQuantityError):
        return HTTPException(
            status_code=409,
            detail={"code": "INSUFFICIENT_QUANTITY", "message": str(exc)},
        )
    code = "INVALID_COLLECTION" if isinstance(exc, SelectedCollectionError) else "INVALID_PLAN"
    return HTTPException(status_code=422, detail={"code": code, "message": str(exc)})


@router.post(
    "/decks/{deck_id}/revisions",
    response_model=DataResponse[DeckRevision],
    status_code=201,
)
async def create_revision(
    deck_id: UUID,
    body: DeckRevisionCreate,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DeckRevision]:
    """Apply selected plans as one atomic, named revision."""
    command = RevisionCommand(plan_ids=body.plan_ids, title=body.title, note=body.note)
    try:
        revision = await revision_service.apply_revision(
            request.app.state.db_pool, deck_id, command, _email(account), account.id
        )
    except (
        PlanNotFoundError,
        InvalidPlanError,
        SelectedCollectionError,
        InsufficientQuantityError,
    ) as exc:
        raise revision_error(exc) from exc
    return DataResponse(data=revision)


@router.get(
    "/decks/{deck_id}/revisions",
    response_model=DataResponse[list[DeckRevision]],
)
async def list_revisions(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[list[DeckRevision]]:
    """List a deck's named revisions newest first."""
    try:
        revisions = await revision_service.list_revisions(
            request.app.state.db_pool, deck_id, _email(account)
        )
    except RevisionNotFoundError as exc:
        raise revision_error(exc) from exc
    return DataResponse(data=revisions)


@router.get("/revisions/{revision_id}", response_model=DataResponse[DeckRevision])
async def get_revision(
    revision_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DeckRevision]:
    """Get a revision and its immutable change records."""
    try:
        revision = await revision_service.get_revision(
            request.app.state.db_pool, revision_id, _email(account)
        )
    except RevisionNotFoundError as exc:
        raise revision_error(exc) from exc
    return DataResponse(data=revision)


@router.patch("/revisions/{revision_id}", response_model=DataResponse[DeckRevision])
async def update_revision(
    revision_id: UUID,
    body: DeckRevisionUpdate,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DeckRevision]:
    """Edit a revision title or note."""
    try:
        revision = await revision_service.update_revision(
            request.app.state.db_pool, revision_id, body, _email(account)
        )
    except RevisionNotFoundError as exc:
        raise revision_error(exc) from exc
    return DataResponse(data=revision)
