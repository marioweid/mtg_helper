"""AI deck building endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from mtg_helper.models.ai import (
    BuildRequest,
    BuildResponse,
    ChatRequest,
    ChatResponse,
    DescribeRequest,
    DescribeResponse,
    SuggestRequest,
    SuggestResponse,
)
from mtg_helper.models.common import DataResponse
from mtg_helper.services import ai_service, deck_service, rate_limit_service
from mtg_helper.services.ai_service import DeckNotFoundError, LLMEmptyResponseError
from mtg_helper.services.rate_limit_service import RateLimitExceeded

# Per-key rate limits for LLM-backed endpoints. Both window and count are tuned
# for interactive use; drop the limit when deploying to a multi-replica setup.
_DESCRIBE_LIMIT = (30, 60)  # 30 calls / 60 seconds
_CHAT_LIMIT = (20, 60)  # 20 calls / 60 seconds


def _llm_unavailable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={"code": "LLM_EMPTY_RESPONSE", "message": detail},
    )


def _rate_key(request: Request, endpoint: str) -> str:
    """Derive a rate-limit key from account header or client IP."""
    account = request.headers.get("x-account-id")
    if account:
        return f"{endpoint}:acct:{account}"
    ip = request.client.host if request.client else "unknown"
    return f"{endpoint}:ip:{ip}"


def _enforce_rate_limit(request: Request, endpoint: str, limit: tuple[int, int]) -> None:
    """Raise 429 if the caller has exceeded the per-key rate limit."""
    count, window = limit
    try:
        rate_limit_service.check(_rate_key(request, endpoint), count, window)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": "RATE_LIMITED", "message": str(exc)},
        ) from exc


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
            collection_ids=body.collection_ids,
            max_price_cents=body.max_price_cents,
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
            collection_ids=body.collection_ids,
            max_price_cents=body.max_price_cents,
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
    _enforce_rate_limit(request, "chat", _CHAT_LIMIT)
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


@router.post("/describe", response_model=DataResponse[DescribeResponse])
async def describe_deck(
    body: DescribeRequest,
    request: Request,
) -> DataResponse[DescribeResponse]:
    """Run one turn of the deck description agent to build a structured deck strategy."""
    _enforce_rate_limit(request, "describe", _DESCRIBE_LIMIT)
    try:
        result = await ai_service.describe_deck(
            request.app.state.db_pool,
            request.app.state.ai_client,
            body.commander_scryfall_id,
            body.partner_scryfall_id,
            body.bracket,
            [{"role": m.role, "content": m.content} for m in body.history],
            body.message,
        )
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
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
