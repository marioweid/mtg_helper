"""Owner-scoped Deck Tutor guide endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.common import DataResponse
from mtg_helper.models.tutor import TutorGenerateRequest, TutorSetupUpdate, TutorStateResponse
from mtg_helper.services.tutor.repository import TutorError
from mtg_helper.services.tutor.service import TutorService, owner

router = APIRouter(prefix="/decks/{deck_id}/tutor", tags=["tutor"])
CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]


def _owner(account: AccountResponse):
    if not account.email:
        raise HTTPException(
            status_code=403, detail={"code": "EMAIL_REQUIRED", "message": "Account has no email"}
        )
    return owner(account.id, account.email)


def _service(request: Request) -> TutorService:
    return TutorService(request.app.state.db_pool)


def _error(exc: TutorError) -> HTTPException:
    code = "DECK_NOT_FOUND" if exc.status == 404 else "TUTOR_REQUEST_INVALID"
    return HTTPException(status_code=exc.status, detail={"code": code, "message": str(exc)})


@router.get("", response_model=DataResponse[TutorStateResponse])
async def get_tutor(
    deck_id: UUID, request: Request, account: CurrentAccount
) -> DataResponse[TutorStateResponse]:
    """Read the saved Tutor state without starting or retrying model work."""
    try:
        state = await _service(request).state(_owner(account), deck_id)
    except TutorError as exc:
        raise _error(exc) from exc
    return DataResponse(data=state)


@router.put("/setup", response_model=DataResponse[TutorStateResponse])
async def save_tutor_setup(
    deck_id: UUID, body: TutorSetupUpdate, request: Request, account: CurrentAccount
) -> DataResponse[TutorStateResponse]:
    """Save mode selection without modifying the deck or initiating a guide."""
    try:
        state = await _service(request).save_mode(_owner(account), deck_id, body.mode)
    except TutorError as exc:
        raise _error(exc) from exc
    return DataResponse(data=state)


@router.post("/guides", response_model=DataResponse[TutorStateResponse])
async def generate_guide(
    deck_id: UUID, body: TutorGenerateRequest, request: Request, account: CurrentAccount
) -> DataResponse[TutorStateResponse]:
    """Persist and start one explicit idempotent guide request."""
    try:
        state = await _service(request).start(_owner(account), deck_id, body.request_key)
    except TutorError as exc:
        raise _error(exc) from exc
    return DataResponse(data=state)
