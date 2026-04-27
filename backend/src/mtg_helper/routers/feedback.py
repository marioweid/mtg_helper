"""Deck feedback endpoints (thumbs up/down on card suggestions)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.common import DataResponse
from mtg_helper.models.feedback import FeedbackCreate, FeedbackResponse
from mtg_helper.services import deck_service, feedback_service
from mtg_helper.services.feedback_service import CardNotFoundError, DeckNotFoundError

router = APIRouter(prefix="/decks", tags=["feedback"])

CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]


def _require_email(account: AccountResponse) -> str:
    if not account.email:
        raise HTTPException(
            status_code=403,
            detail={"code": "EMAIL_REQUIRED", "message": "Account has no email"},
        )
    return account.email


async def _assert_deck_owner(request: Request, deck_id: UUID, email: str) -> None:
    """Raise 404 if the deck doesn't exist or isn't owned by the email."""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        try:
            await deck_service._assert_owner(conn, deck_id, email)
        except deck_service.DeckNotFoundError as e:
            raise HTTPException(
                status_code=404,
                detail={"code": "DECK_NOT_FOUND", "message": str(e)},
            ) from e


@router.post(
    "/{deck_id}/feedback",
    response_model=DataResponse[FeedbackResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_feedback(
    deck_id: UUID, body: FeedbackCreate, request: Request, account: CurrentAccount
) -> DataResponse[FeedbackResponse]:
    """Submit thumbs-up or thumbs-down feedback for a card suggestion."""
    await _assert_deck_owner(request, deck_id, _require_email(account))
    try:
        result = await feedback_service.add_feedback(request.app.state.db_pool, deck_id, body)
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    except CardNotFoundError as e:
        raise HTTPException(status_code=422, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
    return DataResponse(data=result)


@router.get("/{deck_id}/feedback", response_model=DataResponse[list[FeedbackResponse]])
async def list_feedback(
    deck_id: UUID, request: Request, account: CurrentAccount
) -> DataResponse[list[FeedbackResponse]]:
    """List all feedback for a deck."""
    await _assert_deck_owner(request, deck_id, _require_email(account))
    results = await feedback_service.list_feedback(request.app.state.db_pool, deck_id)
    return DataResponse(data=results)


@router.delete("/{deck_id}/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feedback(
    deck_id: UUID, feedback_id: UUID, request: Request, account: CurrentAccount
) -> None:
    """Remove a feedback record."""
    await _assert_deck_owner(request, deck_id, _require_email(account))
    deleted = await feedback_service.delete_feedback(
        request.app.state.db_pool, deck_id, feedback_id
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "FEEDBACK_NOT_FOUND", "message": f"Feedback {feedback_id} not found"},
        )
