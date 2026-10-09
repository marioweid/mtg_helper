"""Default-off, owner-scoped Discover endpoints; only POST /runs starts paid work."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from mtg_helper.auth import get_current_account
from mtg_helper.config import settings
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.common import DataResponse
from mtg_helper.models.recommendations import (
    DiscoveryStatus,
    GenerateRequest,
    PilotFeedback,
    QueryPage,
    QueryPreview,
    RunView,
)
from mtg_helper.services import feature_flag_service
from mtg_helper.services.recommendations.provider import Provider
from mtg_helper.services.recommendations.repository import DiscoveryError, Owner
from mtg_helper.services.recommendations.service import DiscoveryService
from mtg_helper.services.recommendations.source import Card
from mtg_helper.services.recommendations.source_repository import SourceRepository

Account = Annotated[AccountResponse, Depends(get_current_account)]


async def enabled(request: Request, account: Account) -> None:
    if not await feature_flag_service.is_enabled(
        request.app.state.db_pool,
        "recommendations",
        account.id,
        False,
    ):
        raise DiscoveryError("Discover experiment is disabled for this account", 404)


class PilotRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def bounded_validation(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": {
                            "code": "INVALID_DISCOVERY_REQUEST",
                            "message": "Malformed or unsupported Discover request; use literal "
                            "filters, a nonblank goal of at most 1000 chars and valid IDs.",
                        }
                    },
                )

        return bounded_validation


router = APIRouter(
    route_class=PilotRoute,
    prefix="/decks/{deck_id}/recommendations",
    tags=["recommendations"],
    dependencies=[Depends(enabled)],
)


def owner(account: AccountResponse) -> Owner:
    if not account.email:
        raise DiscoveryError("Account email required", 403)
    return Owner(account.id, account.email)


def service(request: Request) -> DiscoveryService:
    pool = request.app.state.db_pool
    sources = getattr(request.app.state, "recommendation_sources", None)
    if sources is None or sources.pool is not pool:
        sources = SourceRepository(pool)
        request.app.state.recommendation_sources = sources
    return DiscoveryService(pool, sources, Provider(settings.openai_api_key.get_secret_value()))


@router.get("/status")
async def status(
    deck_id: UUID, request: Request, account: Account
) -> DataResponse[DiscoveryStatus]:
    return DataResponse(data=await service(request).status(owner(account), deck_id))


@router.post("/preview-query")
async def preview(
    deck_id: UUID, body: QueryPreview, request: Request, account: Account
) -> DataResponse[QueryPage]:
    return DataResponse(data=await service(request).preview(owner(account), deck_id, body))


@router.post("/runs", status_code=202)
async def generate(
    deck_id: UUID,
    body: GenerateRequest,
    request: Request,
    account: Account,
    background: BackgroundTasks,
) -> DataResponse[RunView]:
    engine = service(request)
    run_id, work = await engine.generate(owner(account), deck_id, body)
    if work:
        background.add_task(engine.run, work)
    return DataResponse(data=await engine.view(owner(account), deck_id, run_id))


@router.get("/runs/{run_id}")
async def view(
    deck_id: UUID, run_id: UUID, request: Request, account: Account
) -> DataResponse[RunView]:
    return DataResponse(data=await service(request).view(owner(account), deck_id, run_id))


@router.get("/runs/{run_id}/trace")
async def trace(
    deck_id: UUID, run_id: UUID, request: Request, account: Account
) -> DataResponse[Card]:
    return DataResponse(data=await service(request).trace(owner(account), deck_id, run_id))


@router.post("/runs/{run_id}/candidates/{oracle_id}/plan")
async def plan(
    deck_id: UUID, run_id: UUID, oracle_id: UUID, request: Request, account: Account
) -> DataResponse[bool]:
    await service(request).planner.plan(owner(account), deck_id, oracle_id, run_id=run_id)
    return DataResponse(data=True)


@router.post("/candidates/{oracle_id}/plan")
async def manual_plan(
    deck_id: UUID, oracle_id: UUID, request: Request, account: Account
) -> DataResponse[bool]:
    await service(request).planner.plan(owner(account), deck_id, oracle_id)
    return DataResponse(data=True)


@router.post("/runs/{run_id}/feedback")
async def feedback(
    deck_id: UUID, run_id: UUID, body: PilotFeedback, request: Request, account: Account
) -> DataResponse[bool]:
    await service(request).feedback(owner(account), deck_id, run_id, body)
    return DataResponse(data=True)
