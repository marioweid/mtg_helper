"""Onboarding endpoints — one-click commander → sample deck."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.common import DataResponse
from mtg_helper.models.onboarding import (
    QuickstartRequest,
    QuickstartResponse,
    QuickstartStageResult,
)
from mtg_helper.services import onboarding_service, rate_limit_service
from mtg_helper.services.deck_service import CardNotFoundError
from mtg_helper.services.rate_limit_service import RateLimitExceeded

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]

# Quickstart is the single most expensive endpoint in the app — each call runs
# six LLM-backed retrieval rounds plus DB writes. Cap aggressively per account.
_QUICKSTART_LIMIT = (5, 300)  # 5 calls / 5 minutes


def _require_email(account: AccountResponse) -> str:
    if not account.email:
        raise HTTPException(
            status_code=403,
            detail={"code": "EMAIL_REQUIRED", "message": "Account has no email"},
        )
    return account.email


def _enforce_rate_limit(account: AccountResponse) -> None:
    count, window = _QUICKSTART_LIMIT
    key = f"onboarding-quickstart:acct:{account.id}"
    try:
        rate_limit_service.check(key, count, window)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": "RATE_LIMITED", "message": str(exc)},
        ) from exc


@router.post(
    "/quickstart",
    response_model=DataResponse[QuickstartResponse],
    status_code=201,
)
async def quickstart(
    body: QuickstartRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[QuickstartResponse]:
    """Create a deck and run the full staged build pipeline server-side.

    The deck is left at the first build stage so the user lands on the build
    wizard with a complete draft already populated.
    """
    email = _require_email(account)
    _enforce_rate_limit(account)
    try:
        deck, results = await onboarding_service.quickstart(
            request.app.state.db_pool,
            request.app.state.ai_client,
            request.app.state.qdrant_client,
            email=email,
            account_id=account.id,
            commander_scryfall_id=body.commander_scryfall_id,
            partner_scryfall_id=body.partner_scryfall_id,
            bracket=body.bracket,
            name=body.name,
        )
    except CardNotFoundError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "COMMANDER_NOT_FOUND", "message": str(e)},
        )
    response = QuickstartResponse(
        deck=deck,
        stages=[
            QuickstartStageResult(stage=r.stage, target=r.target, accepted=r.accepted)
            for r in results
        ],
    )
    return DataResponse(data=response)
