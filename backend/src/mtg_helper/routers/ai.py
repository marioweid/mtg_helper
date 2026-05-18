"""AI deck building endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.ai import (
    BuildRequest,
    BuildResponse,
    CutsRequest,
    CutsResponse,
    DescribeRequest,
    DescribeResponse,
    KeywordExtractRequest,
    KeywordExtractResponse,
    SuggestRequest,
    SuggestResponse,
)
from mtg_helper.models.common import DataResponse
from mtg_helper.services import ai_service, cuts_service, deck_service, rate_limit_service
from mtg_helper.services.ai_service import DeckNotFoundError, LLMEmptyResponseError
from mtg_helper.services.cuts_service import DeckNotFoundError as CutsDeckNotFoundError
from mtg_helper.services.rate_limit_service import RateLimitExceeded

CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]

# Per-key rate limits for LLM-backed endpoints. Both window and count are tuned
# for interactive use; drop the limit when deploying to a multi-replica setup.
_DESCRIBE_LIMIT = (30, 60)  # 30 calls / 60 seconds


def _llm_unavailable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={"code": "LLM_EMPTY_RESPONSE", "message": detail},
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


def _enforce_rate_limit(account: AccountResponse, endpoint: str, limit: tuple[int, int]) -> None:
    """Raise 429 if the caller has exceeded the per-account rate limit."""
    count, window = limit
    key = f"{endpoint}:acct:{account.id}"
    try:
        rate_limit_service.check(key, count, window)
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
    account: CurrentAccount,
) -> DataResponse[BuildResponse]:
    """Advance the deck to the next build stage and return card suggestions."""
    email = _require_email(account)
    try:
        result = await ai_service.build_stage(
            request.app.state.db_pool,
            request.app.state.ai_client,
            request.app.state.qdrant_client,
            deck_id,
            account.id,
            email,
            stage=body.stage,
            target=body.target,
            offset=body.offset,
            exclude=body.exclude,
            collection_ids=body.collection_ids,
            max_price_cents=body.max_price_cents,
            min_price_cents=body.min_price_cents,
            card_types=body.card_types,
            subtypes=body.subtypes,
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
    account: CurrentAccount,
) -> DataResponse[SuggestResponse]:
    """Get card suggestions for a deck based on a free-form prompt."""
    email = _require_email(account)
    try:
        result = await ai_service.suggest_cards(
            request.app.state.db_pool,
            request.app.state.ai_client,
            request.app.state.qdrant_client,
            deck_id,
            account.id,
            email,
            body.prompt,
            body.count,
            collection_ids=body.collection_ids,
            max_price_cents=body.max_price_cents,
            min_price_cents=body.min_price_cents,
            card_types=body.card_types,
            subtypes=body.subtypes,
        )
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    return DataResponse(data=result)


@router.post("/{deck_id}/suggest-cuts", response_model=DataResponse[CutsResponse])
async def suggest_cuts(
    deck_id: UUID,
    body: CutsRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[CutsResponse]:
    """Suggest cards to cut from a deck, protecting combo pieces."""
    email = _require_email(account)
    try:
        result = await cuts_service.suggest_cuts(
            request.app.state.db_pool,
            request.app.state.ai_client,
            deck_id,
            email,
            body.count,
        )
    except CutsDeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    return DataResponse(data=result)


@router.post("/describe", response_model=DataResponse[DescribeResponse])
async def describe_deck(
    body: DescribeRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DescribeResponse]:
    """Run one turn of the deck description agent to build a structured deck strategy."""
    _enforce_rate_limit(account, "describe", _DESCRIBE_LIMIT)
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


@router.post("/extract-keywords", response_model=DataResponse[KeywordExtractResponse])
async def extract_keywords(
    body: KeywordExtractRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[KeywordExtractResponse]:
    """Run one turn of the keyword-extracting deck agent.

    The agent converges on a structured set of archetype keywords (Moxfield-
    style) instead of writing prose. Used by the new ``/decks/new/agent`` flow.
    """
    _enforce_rate_limit(account, "extract_keywords", _DESCRIBE_LIMIT)
    try:
        result = await ai_service.extract_keywords(
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
    account: CurrentAccount,
) -> Response:
    """Export the deck in Moxfield-compatible plain text format."""
    email = _require_email(account)
    result = await deck_service.export_moxfield(request.app.state.db_pool, deck_id, email)
    if result is None:
        raise _deck_not_found(deck_id)
    _deck_name, export_text = result
    return Response(content=export_text, media_type="text/plain")
