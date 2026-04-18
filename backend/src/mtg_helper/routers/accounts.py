"""Account management endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from mtg_helper.models.accounts import AccountCreate, AccountResponse, AccountUpdate
from mtg_helper.models.common import DataResponse
from mtg_helper.services import account_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _not_found(account_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "ACCOUNT_NOT_FOUND", "message": f"Account {account_id} not found"},
    )


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
        raise _not_found(account_id)
    return DataResponse(data=result)


@router.patch("/{account_id}", response_model=DataResponse[AccountResponse])
async def update_account(
    account_id: UUID, body: AccountUpdate, request: Request
) -> DataResponse[AccountResponse]:
    """Update account fields. Only provided fields are changed."""
    result = await account_service.update_account(request.app.state.db_pool, account_id, body)
    if result is None:
        raise _not_found(account_id)
    return DataResponse(data=result)
