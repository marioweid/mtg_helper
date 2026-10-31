"""Shared card exports for planned additions and comparison results."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.card_exports import CardExportPreview, CardExportRequest
from mtg_helper.models.common import DataResponse
from mtg_helper.services import card_export_service

router = APIRouter(prefix="/card-exports", tags=["card-exports"])
CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]


@router.post("/preview")
async def preview(
    body: CardExportRequest, request: Request, account: CurrentAccount
) -> DataResponse[CardExportPreview]:
    """Preview an export without purchasing, reserving or moving any cards."""
    try:
        result = await card_export_service.preview(
            request.app.state.db_pool, body, account_id=account.id
        )
    except card_export_service.ExportNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "EXPORT_NOT_FOUND", "message": str(exc)}
        ) from exc
    return DataResponse(data=result)
