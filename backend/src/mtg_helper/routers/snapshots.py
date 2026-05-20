"""Deck snapshot + comparison endpoints."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.common import DataResponse
from mtg_helper.models.snapshots import (
    DeckCompareResponse,
    SnapshotCreate,
    SnapshotDetailResponse,
    SnapshotResponse,
    SnapshotSummary,
)
from mtg_helper.services import snapshot_service
from mtg_helper.services.snapshot_service import SnapshotNotFoundError

router = APIRouter(tags=["snapshots"])

CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]


def _require_email(account: AccountResponse) -> str:
    if not account.email:
        raise HTTPException(
            status_code=403,
            detail={"code": "EMAIL_REQUIRED", "message": "Account has no email"},
        )
    return account.email


def _not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": message},
    )


@router.get(
    "/decks/{deck_id}/snapshots",
    response_model=DataResponse[list[SnapshotSummary]],
)
async def list_snapshots(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[list[SnapshotSummary]]:
    """List snapshots for a deck, newest first."""
    email = _require_email(account)
    try:
        snapshots = await snapshot_service.list_snapshots(
            request.app.state.db_pool, deck_id, email=email
        )
    except SnapshotNotFoundError as e:
        raise _not_found(str(e))
    return DataResponse(data=snapshots)


@router.post(
    "/decks/{deck_id}/snapshots",
    response_model=DataResponse[SnapshotResponse],
    status_code=201,
)
async def create_snapshot(
    deck_id: UUID,
    body: SnapshotCreate,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[SnapshotResponse]:
    """Create a manual snapshot of the deck's current state."""
    email = _require_email(account)
    try:
        snapshot = await snapshot_service.create_snapshot(
            request.app.state.db_pool,
            deck_id,
            label=body.label,
            source="manual",
            email=email,
        )
    except SnapshotNotFoundError as e:
        raise _not_found(str(e))
    return DataResponse(data=snapshot)


@router.get(
    "/snapshots/{snapshot_id}",
    response_model=DataResponse[SnapshotDetailResponse],
)
async def get_snapshot(
    snapshot_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[SnapshotDetailResponse]:
    """Fetch a snapshot with its full card list."""
    email = _require_email(account)
    try:
        snapshot = await snapshot_service.get_snapshot(
            request.app.state.db_pool, snapshot_id, email=email
        )
    except SnapshotNotFoundError as e:
        raise _not_found(str(e))
    return DataResponse(data=snapshot)


@router.delete("/snapshots/{snapshot_id}", status_code=204)
async def delete_snapshot(
    snapshot_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> Response:
    """Delete a snapshot."""
    email = _require_email(account)
    try:
        await snapshot_service.delete_snapshot(request.app.state.db_pool, snapshot_id, email=email)
    except SnapshotNotFoundError as e:
        raise _not_found(str(e))
    return Response(status_code=204)


@router.get("/decks/compare", response_model=DataResponse[DeckCompareResponse])
async def compare(
    request: Request,
    account: CurrentAccount,
    left: UUID = Query(...),
    left_kind: Literal["deck", "snapshot"] = Query(default="deck"),
    right: UUID = Query(...),
    right_kind: Literal["deck", "snapshot"] = Query(default="deck"),
) -> DataResponse[DeckCompareResponse]:
    """Diff two compositions. Either side may be a live deck or a snapshot."""
    email = _require_email(account)
    try:
        result = await snapshot_service.compare(
            request.app.state.db_pool,
            left_kind=left_kind,
            left_id=left,
            right_kind=right_kind,
            right_id=right,
            email=email,
        )
    except SnapshotNotFoundError as e:
        raise _not_found(str(e))
    return DataResponse(data=result)
