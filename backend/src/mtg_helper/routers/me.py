"""Authenticated `/me` endpoints for account and collection operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse, AccountUpdate
from mtg_helper.models.collections import (
    CollectionCreate,
    CollectionFromUrlRequest,
    CollectionFromUrlResponse,
    CollectionResponse,
)
from mtg_helper.models.common import DataResponse
from mtg_helper.services import (
    account_service,
    collection_service,
    collection_url_import_service,
)
from mtg_helper.services.collection_service import (
    AccountNotFoundError as CollectionAccountNotFoundError,
)
from mtg_helper.services.collection_service import DuplicateCollectionNameError
from mtg_helper.services.collection_url_import_service import (
    BinderFetchError,
    UnsupportedBinderUrlError,
)

router = APIRouter(prefix="/me", tags=["me"])

CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]


@router.get("", response_model=DataResponse[AccountResponse])
async def get_me(account: CurrentAccount) -> DataResponse[AccountResponse]:
    """Return the authenticated account."""
    return DataResponse(data=account)


@router.patch("", response_model=DataResponse[AccountResponse])
async def update_me(
    body: AccountUpdate, account: CurrentAccount, request: Request
) -> DataResponse[AccountResponse]:
    """Update the authenticated account's mutable fields."""
    result = await account_service.update_account(request.app.state.db_pool, account.id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="account not found")
    return DataResponse(data=result)


@router.get("/collections", response_model=DataResponse[list[CollectionResponse]])
async def list_collections(
    account: CurrentAccount, request: Request
) -> DataResponse[list[CollectionResponse]]:
    """List the authenticated account's collections."""
    try:
        items = await collection_service.list_collections(request.app.state.db_pool, account.id)
    except CollectionAccountNotFoundError as e:
        raise HTTPException(
            status_code=404, detail={"code": "ACCOUNT_NOT_FOUND", "message": str(e)}
        ) from e
    return DataResponse(data=items)


@router.post(
    "/collections",
    response_model=DataResponse[CollectionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_collection(
    body: CollectionCreate, account: CurrentAccount, request: Request
) -> DataResponse[CollectionResponse]:
    """Create a new collection for the authenticated account."""
    try:
        item = await collection_service.create_collection(
            request.app.state.db_pool, account.id, body.name
        )
    except DuplicateCollectionNameError as e:
        raise HTTPException(
            status_code=409, detail={"code": "DUPLICATE_COLLECTION", "message": str(e)}
        ) from e
    return DataResponse(data=item)


@router.post(
    "/collections/import-url",
    response_model=DataResponse[CollectionFromUrlResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_collection_from_url(
    body: CollectionFromUrlRequest,
    account: CurrentAccount,
    request: Request,
) -> DataResponse[CollectionFromUrlResponse]:
    """Create a collection from a public Moxfield binder URL and import its cards.

    The collection is named after the binder unless ``name`` is given. The
    link is not stored; re-importing later is a manual, one-shot operation.
    """
    try:
        collection, result = await collection_url_import_service.import_new_from_url(
            request.app.state.db_pool,
            body.url,
            account.id,
            name=body.name,
        )
    except DuplicateCollectionNameError as e:
        raise HTTPException(
            status_code=409, detail={"code": "DUPLICATE_COLLECTION", "message": str(e)}
        ) from e
    except UnsupportedBinderUrlError as e:
        raise HTTPException(
            status_code=422, detail={"code": "UNSUPPORTED_URL", "message": str(e)}
        ) from e
    except BinderFetchError as e:
        raise HTTPException(
            status_code=502, detail={"code": "UPSTREAM_FETCH_FAILED", "message": str(e)}
        ) from e
    return DataResponse(data=CollectionFromUrlResponse(collection=collection, import_=result))
