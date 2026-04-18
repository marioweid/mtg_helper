"""Collection CRUD, card list, CSV import/export endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, Response

from mtg_helper.models.collections import (
    CollectionCardAdd,
    CollectionCardItem,
    CollectionCardUpdate,
    CollectionCreate,
    CollectionImportRequest,
    CollectionImportResponse,
    CollectionResponse,
    CollectionUpdate,
)
from mtg_helper.models.common import DataResponse, PaginationMeta
from mtg_helper.services import collection_service
from mtg_helper.services.collection_service import (
    AccountNotFoundError,
    CardNotFoundError,
    CollectionNotFoundError,
    DuplicateCollectionNameError,
)

account_router = APIRouter(prefix="/accounts", tags=["collections"])
router = APIRouter(prefix="/collections", tags=["collections"])


def _not_found(collection_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "COLLECTION_NOT_FOUND",
            "message": f"Collection {collection_id} not found",
        },
    )


@account_router.get(
    "/{account_id}/collections",
    response_model=DataResponse[list[CollectionResponse]],
)
async def list_collections(
    account_id: UUID, request: Request
) -> DataResponse[list[CollectionResponse]]:
    """List all collections for an account."""
    try:
        items = await collection_service.list_collections(request.app.state.db_pool, account_id)
    except AccountNotFoundError as e:
        raise HTTPException(
            status_code=404, detail={"code": "ACCOUNT_NOT_FOUND", "message": str(e)}
        )
    return DataResponse(data=items)


@account_router.post(
    "/{account_id}/collections",
    response_model=DataResponse[CollectionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_collection(
    account_id: UUID, body: CollectionCreate, request: Request
) -> DataResponse[CollectionResponse]:
    """Create a new collection for an account."""
    try:
        item = await collection_service.create_collection(
            request.app.state.db_pool, account_id, body.name
        )
    except AccountNotFoundError as e:
        raise HTTPException(
            status_code=404, detail={"code": "ACCOUNT_NOT_FOUND", "message": str(e)}
        )
    except DuplicateCollectionNameError as e:
        raise HTTPException(
            status_code=409, detail={"code": "DUPLICATE_COLLECTION", "message": str(e)}
        )
    return DataResponse(data=item)


@router.get("/{collection_id}", response_model=DataResponse[CollectionResponse])
async def get_collection(collection_id: UUID, request: Request) -> DataResponse[CollectionResponse]:
    """Fetch a single collection's metadata."""
    try:
        item = await collection_service.get_collection(request.app.state.db_pool, collection_id)
    except CollectionNotFoundError:
        raise _not_found(collection_id)
    return DataResponse(data=item)


@router.patch("/{collection_id}", response_model=DataResponse[CollectionResponse])
async def rename_collection(
    collection_id: UUID, body: CollectionUpdate, request: Request
) -> DataResponse[CollectionResponse]:
    """Rename a collection."""
    try:
        item = await collection_service.rename_collection(
            request.app.state.db_pool, collection_id, body.name
        )
    except CollectionNotFoundError:
        raise _not_found(collection_id)
    except DuplicateCollectionNameError as e:
        raise HTTPException(
            status_code=409, detail={"code": "DUPLICATE_COLLECTION", "message": str(e)}
        )
    return DataResponse(data=item)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(collection_id: UUID, request: Request) -> Response:
    """Delete a collection and all of its cards."""
    deleted = await collection_service.delete_collection(request.app.state.db_pool, collection_id)
    if not deleted:
        raise _not_found(collection_id)
    return Response(status_code=204)


@router.get(
    "/{collection_id}/cards",
    response_model=DataResponse[list[CollectionCardItem]],
)
async def list_cards(
    collection_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DataResponse[list[CollectionCardItem]]:
    """List cards in a collection with pagination."""
    try:
        items, total = await collection_service.list_cards(
            request.app.state.db_pool, collection_id, limit, offset
        )
    except CollectionNotFoundError:
        raise _not_found(collection_id)
    return DataResponse(data=items, meta=PaginationMeta(total=total, limit=limit, offset=offset))


@router.post(
    "/{collection_id}/cards",
    response_model=DataResponse[CollectionCardItem],
    status_code=status.HTTP_201_CREATED,
)
async def add_card(
    collection_id: UUID, body: CollectionCardAdd, request: Request
) -> DataResponse[CollectionCardItem]:
    """Add (or increment) a single printing in a collection."""
    try:
        item = await collection_service.add_card(request.app.state.db_pool, collection_id, body)
    except CollectionNotFoundError:
        raise _not_found(collection_id)
    except CardNotFoundError as e:
        raise HTTPException(status_code=422, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
    return DataResponse(data=item)


@router.patch(
    "/{collection_id}/cards/{card_id}",
    response_model=DataResponse[CollectionCardItem],
)
async def update_card(
    collection_id: UUID,
    card_id: UUID,
    body: CollectionCardUpdate,
    request: Request,
) -> DataResponse[CollectionCardItem]:
    """Patch a card's quantity / condition / language / tags / price."""
    item = await collection_service.update_card(
        request.app.state.db_pool, collection_id, card_id, body
    )
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CARD_NOT_IN_COLLECTION",
                "message": f"Card {card_id} not in collection {collection_id}",
            },
        )
    return DataResponse(data=item)


@router.delete(
    "/{collection_id}/cards/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_card(collection_id: UUID, card_id: UUID, request: Request) -> Response:
    """Remove all printings of a card from a collection."""
    removed = await collection_service.remove_card(
        request.app.state.db_pool, collection_id, card_id
    )
    if not removed:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CARD_NOT_IN_COLLECTION",
                "message": f"Card {card_id} not in collection {collection_id}",
            },
        )
    return Response(status_code=204)


@router.post(
    "/{collection_id}/import",
    response_model=DataResponse[CollectionImportResponse],
)
async def import_csv(
    collection_id: UUID,
    body: CollectionImportRequest,
    request: Request,
) -> DataResponse[CollectionImportResponse]:
    """Import a Moxfield CSV into a collection (merge or replace)."""
    try:
        result = await collection_service.import_csv(
            request.app.state.db_pool, collection_id, body.csv, body.mode
        )
    except CollectionNotFoundError:
        raise _not_found(collection_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"code": "PARSE_ERROR", "message": str(e)})
    return DataResponse(data=result)


@router.get("/{collection_id}/export", response_class=PlainTextResponse)
async def export_csv(collection_id: UUID, request: Request) -> PlainTextResponse:
    """Export a collection as a Moxfield-compatible CSV."""
    try:
        csv_text = await collection_service.export_csv(request.app.state.db_pool, collection_id)
    except CollectionNotFoundError:
        raise _not_found(collection_id)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="collection-{collection_id}.csv"'},
    )
