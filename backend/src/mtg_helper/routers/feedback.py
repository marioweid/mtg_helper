"""Deck feedback endpoints (thumbs up/down on card suggestions)."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from mtg_helper.models.common import DataResponse
from mtg_helper.models.feedback import FeedbackCreate, FeedbackResponse
from mtg_helper.services import feedback_service
from mtg_helper.services.feedback_service import CardNotFoundError, DeckNotFoundError

router = APIRouter(prefix="/decks", tags=["feedback"])


@router.post(
    "/{deck_id}/feedback",
    response_model=DataResponse[FeedbackResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_feedback(
    deck_id: UUID, body: FeedbackCreate, request: Request
) -> DataResponse[FeedbackResponse]:
    """Submit thumbs-up or thumbs-down feedback for a card suggestion."""
    try:
        result = await feedback_service.add_feedback(request.app.state.db_pool, deck_id, body)
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    except CardNotFoundError as e:
        raise HTTPException(status_code=422, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
    return DataResponse(data=result)


@router.get("/{deck_id}/feedback", response_model=DataResponse[list[FeedbackResponse]])
async def list_feedback(deck_id: UUID, request: Request) -> DataResponse[list[FeedbackResponse]]:
    """List all feedback for a deck."""
    results = await feedback_service.list_feedback(request.app.state.db_pool, deck_id)
    return DataResponse(data=results)


@router.delete("/{deck_id}/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feedback(deck_id: UUID, feedback_id: UUID, request: Request) -> None:
    """Remove a feedback record."""
    deleted = await feedback_service.delete_feedback(
        request.app.state.db_pool, deck_id, feedback_id
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "FEEDBACK_NOT_FOUND", "message": f"Feedback {feedback_id} not found"},
        )
