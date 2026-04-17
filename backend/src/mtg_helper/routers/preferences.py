"""Account preference endpoints (pet cards, avoid lists, archetypes, ranking weights)."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from mtg_helper.models.common import DataResponse
from mtg_helper.models.preferences import PreferenceCreate, PreferenceResponse
from mtg_helper.models.ranking_weights import RankingWeightsResponse, RankingWeightsUpdate
from mtg_helper.services import preference_service, ranking_weight_service
from mtg_helper.services.preference_service import AccountNotFoundError, CardNotFoundError

router = APIRouter(prefix="/accounts", tags=["preferences"])


@router.post(
    "/{account_id}/preferences",
    response_model=DataResponse[PreferenceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_preference(
    account_id: UUID, body: PreferenceCreate, request: Request
) -> DataResponse[PreferenceResponse]:
    """Create a new preference for an account."""
    try:
        result = await preference_service.create_preference(
            request.app.state.db_pool, account_id, body
        )
    except AccountNotFoundError as e:
        raise HTTPException(
            status_code=404, detail={"code": "ACCOUNT_NOT_FOUND", "message": str(e)}
        )
    except CardNotFoundError as e:
        raise HTTPException(status_code=422, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
    return DataResponse(data=result)


@router.get(
    "/{account_id}/preferences",
    response_model=DataResponse[list[PreferenceResponse]],
)
async def list_preferences(
    account_id: UUID, request: Request
) -> DataResponse[list[PreferenceResponse]]:
    """List all preferences for an account."""
    results = await preference_service.list_preferences(request.app.state.db_pool, account_id)
    return DataResponse(data=results)


@router.delete(
    "/{account_id}/preferences/{preference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_preference(account_id: UUID, preference_id: UUID, request: Request) -> None:
    """Delete a preference."""
    deleted = await preference_service.delete_preference(
        request.app.state.db_pool, account_id, preference_id
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PREFERENCE_NOT_FOUND",
                "message": f"Preference {preference_id} not found",
            },
        )


@router.get(
    "/{account_id}/ranking-weights",
    response_model=DataResponse[RankingWeightsResponse],
)
async def get_ranking_weights(
    account_id: UUID, request: Request
) -> DataResponse[RankingWeightsResponse]:
    """Get ranking weights for an account, seeding defaults on first access."""
    try:
        result = await ranking_weight_service.get_weights(request.app.state.db_pool, account_id)
    except ranking_weight_service.AccountNotFoundError as e:
        raise HTTPException(
            status_code=404, detail={"code": "ACCOUNT_NOT_FOUND", "message": str(e)}
        )
    return DataResponse(data=result)


@router.put(
    "/{account_id}/ranking-weights",
    response_model=DataResponse[RankingWeightsResponse],
)
async def update_ranking_weights(
    account_id: UUID, body: RankingWeightsUpdate, request: Request
) -> DataResponse[RankingWeightsResponse]:
    """Update ranking weights for an account."""
    try:
        result = await ranking_weight_service.update_weights(
            request.app.state.db_pool, account_id, body
        )
    except ranking_weight_service.AccountNotFoundError as e:
        raise HTTPException(
            status_code=404, detail={"code": "ACCOUNT_NOT_FOUND", "message": str(e)}
        )
    return DataResponse(data=result)
