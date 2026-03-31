"""Account management endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from mtg_helper.models.accounts import AccountCreate, AccountResponse
from mtg_helper.models.common import DataResponse
from mtg_helper.services import account_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=DataResponse[AccountResponse], status_code=status.HTTP_201_CREATED)
async def create_account(body: AccountCreate, request: Request) -> DataResponse[AccountResponse]:
    """Create a new account."""
    result = await account_service.create_account(request.app.state.db_pool, body.display_name)
    return DataResponse(data=result)


@router.get("/{account_id}", response_model=DataResponse[AccountResponse])
async def get_account(account_id: UUID, request: Request) -> DataResponse[AccountResponse]:
    """Get an account by ID."""
    result = await account_service.get_account(request.app.state.db_pool, account_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "ACCOUNT_NOT_FOUND", "message": f"Account {account_id} not found"},
        )
    return DataResponse(data=result)
