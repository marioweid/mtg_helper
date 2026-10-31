"""Owner-scoped Discover; setup POSTs start work while reads restore saved state."""

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
    DiscoverMatches,
    DiscoverSetup,
    DiscoverStrategy,
    DiscoverStrategySave,
    DiscoverTerms,
    GenerateRequest,
    PilotFeedback,
    QueryPage,
    QueryPreview,
    RunView,
    StrategyDraftRequest,
    TermSuggestionRequest,
    TermSuggestionRun,
)
from mtg_helper.services import feature_flag_service
from mtg_helper.services.recommendations.provider import Provider
from mtg_helper.services.recommendations.repository import (
    DiscoveryError,
    Owner,
    owned_deck,
    owned_run,
)
from mtg_helper.services.recommendations.service import DiscoveryService
from mtg_helper.services.recommendations.source import Card
from mtg_helper.services.recommendations.source_repository import SourceRepository
from mtg_helper.services.recommendations.strategy_discover import StrategyDiscover

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
                            "message": "Check your Discover input: use valid card/search IDs, "
                            "a nonblank strategy of at most 2000 characters, "
                            "and a request key for AI setup.",
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


def strategy_service(request: Request) -> StrategyDiscover:
    return StrategyDiscover(request.app.state.db_pool)


@router.get("/status")
async def status(
    deck_id: UUID, request: Request, account: Account
) -> DataResponse[DiscoverMatches]:
    return DataResponse(data=await strategy_service(request).status(owner(account), deck_id))


@router.get("/source-terms")
async def source_terms(
    deck_id: UUID, request: Request, account: Account
) -> DataResponse[DiscoverTerms]:
    return DataResponse(data=await strategy_service(request).terms(owner(account), deck_id))


@router.get("/setup")
async def setup(deck_id: UUID, request: Request, account: Account) -> DataResponse[DiscoverSetup]:
    return DataResponse(data=await service(request).setup(owner(account), deck_id))


@router.get("/strategy")
async def saved_strategy(
    deck_id: UUID, request: Request, account: Account
) -> DataResponse[DiscoverMatches]:
    return DataResponse(data=await strategy_service(request).status(owner(account), deck_id))


@router.put("/strategy")
async def save_strategy(
    deck_id: UUID, body: DiscoverStrategySave, request: Request, account: Account
) -> DataResponse[DiscoverStrategy]:
    return DataResponse(data=await strategy_service(request).save(owner(account), deck_id, body))


@router.get("/matches")
async def matches(
    deck_id: UUID, request: Request, account: Account, cursor: str | None = None
) -> DataResponse[DiscoverMatches]:
    return DataResponse(
        data=await strategy_service(request).matches(owner(account), deck_id, cursor)
    )


@router.post("/matches/{oracle_id}/plan")
async def plan_match(
    deck_id: UUID, oracle_id: UUID, request: Request, account: Account
) -> DataResponse[bool]:
    await strategy_service(request).plan(owner(account), deck_id, oracle_id)
    return DataResponse(data=True)


@router.post("/matches/{oracle_id}/dismiss")
async def dismiss_match(
    deck_id: UUID, oracle_id: UUID, request: Request, account: Account
) -> DataResponse[bool]:
    await strategy_service(request).dismiss(owner(account), deck_id, oracle_id, undo=False)
    return DataResponse(data=True)


@router.delete("/matches/{oracle_id}/dismiss")
async def undo_dismiss_match(
    deck_id: UUID, oracle_id: UUID, request: Request, account: Account
) -> DataResponse[bool]:
    await strategy_service(request).dismiss(owner(account), deck_id, oracle_id, undo=True)
    return DataResponse(data=True)


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
    del body, background
    async with request.app.state.db_pool.acquire() as conn:
        await owned_deck(conn, owner(account), deck_id)
    # Keep historical runs readable, but never resume the retired card-generation engine.
    raise DiscoveryError(
        "Card generation was retired; save a strategy and browse local matches", 410
    )


@router.post("/strategy-drafts", status_code=202)
async def draft_strategy(
    deck_id: UUID,
    body: StrategyDraftRequest,
    request: Request,
    account: Account,
    background: BackgroundTasks,
) -> DataResponse[RunView]:
    engine = service(request)
    run_id, work = await engine.draft_strategy(owner(account), deck_id, body)
    if work:
        background.add_task(engine.run, work)
    return DataResponse(data=await engine.view(owner(account), deck_id, run_id))


@router.post("/term-suggestions", status_code=202)
async def suggest_terms(
    deck_id: UUID,
    body: TermSuggestionRequest,
    request: Request,
    account: Account,
    background: BackgroundTasks,
) -> DataResponse[TermSuggestionRun]:
    engine = service(request)
    run_id, work = await engine.suggest_terms(owner(account), deck_id, body)
    if work:
        background.add_task(engine.run, work)
    return DataResponse(data=await engine.terms_view(owner(account), deck_id, run_id))


@router.get("/term-suggestions/{run_id}")
async def term_suggestions(
    deck_id: UUID, run_id: UUID, request: Request, account: Account
) -> DataResponse[TermSuggestionRun]:
    return DataResponse(data=await service(request).terms_view(owner(account), deck_id, run_id))


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
    async with request.app.state.db_pool.acquire() as conn:
        await owned_run(conn, owner(account), deck_id, run_id)
    raise DiscoveryError("Historical AI advice is retired; use current source matches", 410)


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
