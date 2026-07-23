"""Collection CRUD, card list, CSV import/export endpoints."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, Response

from mtg_helper.models.collections import (
    CollectionCardAdd,
    CollectionCardItem,
    CollectionCardUpdate,
    CollectionImportRequest,
    CollectionImportResponse,
    CollectionResponse,
    CollectionUpdate,
)
from mtg_helper.models.common import DataResponse, PaginationMeta
from mtg_helper.services import collection_service
from mtg_helper.services.collection_service import (
    CardNotFoundError,
    CollectionNotFoundError,
    DuplicateCollectionNameError,
)

router = APIRouter(prefix="/collections", tags=["collections"])


def _not_found(collection_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "COLLECTION_NOT_FOUND",
            "message": f"Collection {collection_id} not found",
        },
    )


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
    *,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    type: str | None = Query(default=None, max_length=64),
    min_price_cents: int | None = Query(default=None, ge=0),
    max_price_cents: int | None = Query(default=None, ge=0),
    search: str | None = Query(default=None, max_length=200),
    sort: Literal["name", "price", "quantity"] = "name",
    direction: Literal["asc", "desc"] = "asc",
    group: Literal["none", "type", "set"] = "none",
) -> DataResponse[list[CollectionCardItem]]:
    """List collection cards with server-side filtering, grouping, and sorting."""
    try:
        items, total = await collection_service.list_cards(
            request.app.state.db_pool,
            collection_id,
            limit=limit,
            offset=offset,
            type_filter=type,
            min_price_cents=min_price_cents,
            max_price_cents=max_price_cents,
            search=search,
            sort=sort,
            direction=direction,
            group=group,
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
    """Import a supported CSV into a collection (merge or replace)."""
    try:
        result = await collection_service.import_csv(
            request.app.state.db_pool,
            collection_id,
            body.csv,
            body.mode,
            body.format,
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
