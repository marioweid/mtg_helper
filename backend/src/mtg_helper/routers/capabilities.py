"""Per-account feature capabilities for the frontend to gate optional UI."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from mtg_helper.auth import get_current_account
from mtg_helper.config import settings
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.common import DataResponse
from mtg_helper.services import feature_flag_service
from mtg_helper.services.feature_flag_service import FLAG_OPTIMIZER

router = APIRouter(tags=["capabilities"])

CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]


@router.get("/capabilities", response_model=DataResponse[dict[str, bool]])
async def get_capabilities(
    request: Request,
    account: CurrentAccount,
) -> DataResponse[dict[str, bool]]:
    """Return which optional features are enabled for the calling account."""
    optimizer = await feature_flag_service.is_enabled(
        request.app.state.db_pool, FLAG_OPTIMIZER, account.id, settings.enable_optimizer
    )
    return DataResponse(data={"optimizer": optimizer})
