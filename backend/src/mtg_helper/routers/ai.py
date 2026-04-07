"""AI deck building endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from mtg_helper.models.ai import (
    BuildRequest,
    BuildResponse,
    ChatRequest,
    ChatResponse,
    SuggestRequest,
    SuggestResponse,
)
from mtg_helper.models.common import DataResponse
from mtg_helper.services import ai_service, deck_service
from mtg_helper.services.ai_service import DeckNotFoundError, LLMEmptyResponseError


def _llm_unavailable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={"code": "LLM_EMPTY_RESPONSE", "message": detail},
    )


router = APIRouter(prefix="/decks", tags=["ai"])


def _deck_not_found(deck_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "DECK_NOT_FOUND", "message": f"Deck {deck_id} not found"},
    )


@router.post("/{deck_id}/build", response_model=DataResponse[BuildResponse])
async def build_stage(
    deck_id: UUID,
    body: BuildRequest,
    request: Request,
) -> DataResponse[BuildResponse]:
    """Advance the deck to the next build stage and return card suggestions."""
    try:
        result = await ai_service.build_stage(
            request.app.state.db_pool,
            request.app.state.ai_client,
            request.app.state.qdrant_client,
            deck_id,
            stage=body.stage,
            target=body.target,
            exclude=body.exclude,
        )
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"code": "INVALID_STAGE", "message": str(e)})
    return DataResponse(data=result)


@router.post("/{deck_id}/suggest", response_model=DataResponse[SuggestResponse])
async def suggest_cards(
    deck_id: UUID,
    body: SuggestRequest,
    request: Request,
) -> DataResponse[SuggestResponse]:
    """Get card suggestions for a deck based on a free-form prompt."""
    try:
        result = await ai_service.suggest_cards(
            request.app.state.db_pool,
            request.app.state.ai_client,
            request.app.state.qdrant_client,
            deck_id,
            body.prompt,
            body.count,
        )
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    return DataResponse(data=result)


@router.post("/{deck_id}/chat", response_model=DataResponse[ChatResponse])
async def chat_about_deck(
    deck_id: UUID,
    body: ChatRequest,
    request: Request,
) -> DataResponse[ChatResponse]:
    """Send a free-form chat message about the deck."""
    try:
        result = await ai_service.chat_about_deck(
            request.app.state.db_pool,
            request.app.state.ai_client,
            deck_id,
            body.message,
        )
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    except LLMEmptyResponseError as e:
        raise _llm_unavailable(str(e))
    return DataResponse(data=result)


@router.get("/{deck_id}/export/moxfield")
async def export_moxfield(
    deck_id: UUID,
    request: Request,
) -> Response:
    """Export the deck in Moxfield-compatible plain text format."""
    result = await deck_service.export_moxfield(request.app.state.db_pool, deck_id)
    if result is None:
        raise _deck_not_found(deck_id)
    _deck_name, export_text = result
    return Response(content=export_text, media_type="text/plain")
