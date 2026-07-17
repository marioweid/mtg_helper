"""AI deck building endpoints."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from mtg_helper.auth import get_current_account
from mtg_helper.config import settings
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.ai import (
    BuildRequest,
    BuildResponse,
    CoachMemoryResponse,
    CoachMemoryUpdate,
    CommanderCoachRequest,
    CommanderCoachResponse,
    CommanderCoachStartResponse,
    CommanderSuggestRequest,
    CommanderSuggestResponse,
    DeckDoctorResponse,
    DescribeRequest,
    DescribeResponse,
    KeywordExtractRequest,
    KeywordExtractResponse,
    ManaFixResponse,
    SimulationAnalysisResponse,
    SuggestRequest,
    SuggestResponse,
)
from mtg_helper.models.common import DataResponse
from mtg_helper.models.decks import DeckDetailResponse
from mtg_helper.models.optimizer import (
    OptimizeJobStatus,
    OptimizeRequest,
    OptimizeStartResponse,
)
from mtg_helper.models.playtest import PlaytestSimulateRequest, PlaytestStats
from mtg_helper.models.swaps import SwapRequest, SwapResponse
from mtg_helper.services import (
    agents,
    ai_service,
    coach_memory_service,
    commander_coach,
    commander_suggestor_service,
    deck_optimizer_service,
    deck_service,
    feature_flag_service,
    mana_base_service,
    optimizer_jobs,
    playtest_service,
    rate_limit_service,
    simulation_analysis_service,
    swap_service,
)
from mtg_helper.services.agents.describe_agent import CommanderNotFoundError
from mtg_helper.services.ai_service import DeckNotFoundError
from mtg_helper.services.commander_coach import jobs as coach_jobs
from mtg_helper.services.feature_flag_service import FLAG_OPTIMIZER
from mtg_helper.services.rate_limit_service import RateLimitExceeded
from mtg_helper.services.swap_service import SwapError

CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]
ProgressCb = Callable[[str, str], Awaitable[None]]

_log = logging.getLogger(__name__)

# Per-key rate limits for LLM-backed endpoints. Both window and count are tuned
# for interactive use; drop the limit when deploying to a multi-replica setup.
_DESCRIBE_LIMIT = (30, 60)  # 30 calls / 60 seconds
_PLAYTEST_LIMIT = (20, 60)  # 20 sim runs / 60 seconds — CPU-bound, cap abuse
_ANALYZE_LIMIT = (5, 60)  # 5 analyses / 60 seconds — LLM + multiple tool calls

# Process-wide cap: only one optimization search runs at a time. Each search is
# hundreds of CPU-bound simulations; a second concurrent run would saturate the
# small prod VM and lag every request. A queued caller is rejected, not stacked.
_OPTIMIZE_SEMAPHORE = asyncio.Semaphore(1)


def _require_email(account: AccountResponse) -> str:
    """Return the account's email or raise 403 if missing.

    Auth strips tokens without an ``email`` claim, so this is defensive only.
    """
    if not account.email:
        raise HTTPException(
            status_code=403,
            detail={"code": "EMAIL_REQUIRED", "message": "Account has no email"},
        )
    return account.email


def _enforce_rate_limit(account: AccountResponse, endpoint: str, limit: tuple[int, int]) -> None:
    """Raise 429 if the caller has exceeded the per-account rate limit."""
    count, window = limit
    key = f"{endpoint}:acct:{account.id}"
    try:
        rate_limit_service.check(key, count, window)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": "RATE_LIMITED", "message": str(exc)},
        ) from exc


router = APIRouter(prefix="/decks", tags=["ai"])


def _deck_not_found(deck_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "DECK_NOT_FOUND", "message": f"Deck {deck_id} not found"},
    )


async def _require_deck(
    request: Request,
    deck_id: UUID,
    account: AccountResponse,
) -> DeckDetailResponse:
    email = _require_email(account)
    deck = await deck_service.get_deck(
        request.app.state.db_pool,
        deck_id,
        email,
        account_id=account.id,
    )
    if deck is None:
        raise _deck_not_found(deck_id)
    return deck


async def _request_with_memory(
    pool: Any,
    deck_id: UUID,
    account_id: UUID,
    body: CommanderCoachRequest,
) -> CommanderCoachRequest:
    memory = await coach_memory_service.get_memory(pool, deck_id, account_id)
    notes = memory.notes.strip() or None
    return body.model_copy(update={"coach_memory_notes": notes})


async def _handle_assistant_memory(
    pool: Any,
    deck: DeckDetailResponse,
    account_id: UUID,
    body: CommanderCoachRequest,
) -> CommanderCoachResponse | None:
    """Handle explicit memory commands without spending an LLM request."""
    return await coach_memory_service.handle_memory_message(pool, deck.id, account_id, body)


@router.post("/{deck_id}/build", response_model=DataResponse[BuildResponse])
async def build_stage(
    deck_id: UUID,
    body: BuildRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[BuildResponse]:
    """Advance the deck to the next build stage and return card suggestions."""
    email = _require_email(account)
    try:
        result = await ai_service.build_stage(
            request.app.state.db_pool,
            deck_id,
            account.id,
            email,
            stage=body.stage,
            target=body.target,
            offset=body.offset,
            exclude=body.exclude,
            collection_ids=body.collection_ids,
            max_price_cents=body.max_price_cents,
            min_price_cents=body.min_price_cents,
            card_types=body.card_types,
            subtypes=body.subtypes,
            theme_tag=body.theme_tag,
        )
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"code": "INVALID_STAGE", "message": str(e)})
    return DataResponse(data=result)


@router.post("/{deck_id}/suggest", response_model=DataResponse[SuggestResponse])
async def suggest_cards(
    deck_id: UUID,
    body: SuggestRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[SuggestResponse]:
    """Get card suggestions for a deck based on a free-form prompt."""
    email = _require_email(account)
    try:
        result = await ai_service.suggest_cards(
            request.app.state.db_pool,
            deck_id,
            account.id,
            email,
            body.prompt,
            body.count,
            collection_ids=body.collection_ids,
            max_price_cents=body.max_price_cents,
            min_price_cents=body.min_price_cents,
            card_types=body.card_types,
            subtypes=body.subtypes,
        )
    except DeckNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "DECK_NOT_FOUND", "message": str(e)})
    return DataResponse(data=result)


@router.post("/suggest-commanders", response_model=DataResponse[CommanderSuggestResponse])
async def suggest_commanders(
    body: CommanderSuggestRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[CommanderSuggestResponse]:
    """Run one pre-commander suggestion turn and return live ranked commanders."""
    _enforce_rate_limit(account, "suggest_commanders", _DESCRIBE_LIMIT)
    pool = request.app.state.db_pool
    if body.intent_override is not None and not body.message.strip():
        result = await commander_suggestor_service.build_response(
            pool,
            reply="I updated the commander board with your current filters.",
            done=False,
            intent=body.intent_override,
            limit=body.limit,
        )
    else:
        result = await agents.suggest_turn(
            pool,
            [{"role": m.role, "content": m.content} for m in body.history],
            body.message,
            body.intent_override,
            limit=body.limit,
        )
    return DataResponse(data=result)


@router.post("/{deck_id}/playtest/simulate", response_model=DataResponse[PlaytestStats])
async def playtest_simulate(
    deck_id: UUID,
    body: PlaytestSimulateRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[PlaytestStats]:
    """Run N goldfish trials and return per-turn aggregate stats."""
    email = _require_email(account)
    _enforce_rate_limit(account, "playtest_simulate", _PLAYTEST_LIMIT)
    deck = await deck_service.get_deck(request.app.state.db_pool, deck_id, email)
    if deck is None:
        raise _deck_not_found(deck_id)
    stats = playtest_service.simulate(deck, body)
    return DataResponse(data=stats)


@router.post("/{deck_id}/coach", response_model=DataResponse[CommanderCoachResponse])
async def coach_deck(
    deck_id: UUID,
    body: CommanderCoachRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[CommanderCoachResponse]:
    """Run MTG Assistant for an existing deck."""
    _enforce_rate_limit(account, "coach_deck", _ANALYZE_LIMIT)
    deck = await _require_deck(request, deck_id, account)
    body = await _request_with_memory(request.app.state.db_pool, deck_id, account.id, body)
    routed_response = await _handle_assistant_memory(
        request.app.state.db_pool,
        deck,
        account.id,
        body,
    )
    if routed_response is not None:
        return DataResponse(data=routed_response)

    result = await commander_coach.run_coach(
        request.app.state.db_pool,
        deck,
        body,
    )
    return DataResponse(data=result)


async def _run_coach_job(
    job: coach_jobs.CoachJob,
    pool: Any,
    deck: DeckDetailResponse,
    body: CommanderCoachRequest,
) -> None:
    """Run a Coach request in the background and publish progress events."""

    async def progress(event: str, message: str) -> None:
        await coach_jobs.emit(job, event, message)

    try:
        result = await commander_coach.run_coach(
            pool,
            deck,
            body,
            progress=progress,
        )
        await coach_jobs.finish_ok(job, result)
    except Exception as exc:  # noqa: BLE001 - surface job failures to stream clients
        _log.exception("Coach job %s failed", job.job_id)
        await coach_jobs.finish_error(job, str(exc))


async def _finish_routed_job(
    job: coach_jobs.CoachJob,
    result: CommanderCoachResponse,
) -> None:
    """Publish routed non-specialist progress events and complete the stream."""
    if result.mode == "memory" and result.memory_updated:
        await coach_jobs.emit(job, "memory_writing", "Writing updated Assistant memory")
        await coach_jobs.emit(job, "memory_written", "Assistant memory updated")
    elif result.mode == "memory":
        await coach_jobs.emit(job, "memory_read", "Reading Assistant memory")
    else:
        await coach_jobs.emit(job, "chat_reply", "MTG Assistant answered without deck tools")
    await coach_jobs.finish_ok(job, result)


@router.post("/{deck_id}/coach/start", response_model=DataResponse[CommanderCoachStartResponse])
async def coach_deck_start(
    deck_id: UUID,
    body: CommanderCoachRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[CommanderCoachStartResponse]:
    """Start a streaming MTG Assistant job."""
    _enforce_rate_limit(account, "coach_deck", _ANALYZE_LIMIT)
    deck = await _require_deck(request, deck_id, account)
    registry = request.app.state.coach_jobs
    job = coach_jobs.create(registry, account.id, deck_id)
    await coach_jobs.emit(job, "memory_check", "Checking Assistant memory")
    body = await _request_with_memory(request.app.state.db_pool, deck_id, account.id, body)
    await coach_jobs.emit(job, "memory_loaded", "Loaded deck memory into Assistant context")
    await coach_jobs.emit(job, "assistant_routing", "MTG Assistant is reading the request")
    memory_response = await _handle_assistant_memory(
        request.app.state.db_pool, deck, account.id, body
    )
    if memory_response is not None:
        await coach_jobs.emit(job, "assistant_routed", "Handled by deterministic memory tools")
        asyncio.create_task(_finish_routed_job(job, memory_response))
        return DataResponse(data=CommanderCoachStartResponse(job_id=job.job_id))
    await coach_jobs.emit(job, "assistant_routed", "MTG Assistant is selecting deck tools")
    asyncio.create_task(_run_coach_job(job, request.app.state.db_pool, deck, body))
    return DataResponse(data=CommanderCoachStartResponse(job_id=job.job_id))


@router.get("/{deck_id}/coach/memory", response_model=DataResponse[CoachMemoryResponse])
async def get_coach_memory(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[CoachMemoryResponse]:
    """Return editable persistent memory notes for this deck's Assistant."""
    await _require_deck(request, deck_id, account)
    memory = await coach_memory_service.get_memory(request.app.state.db_pool, deck_id, account.id)
    return DataResponse(data=memory)


@router.put("/{deck_id}/coach/memory", response_model=DataResponse[CoachMemoryResponse])
async def update_coach_memory(
    deck_id: UUID,
    body: CoachMemoryUpdate,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[CoachMemoryResponse]:
    """Replace editable persistent memory notes for this deck's Assistant."""
    await _require_deck(request, deck_id, account)
    memory = await coach_memory_service.upsert_memory(
        request.app.state.db_pool,
        deck_id,
        account.id,
        body.notes,
    )
    return DataResponse(data=memory)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def _coach_event_stream(job: coach_jobs.CoachJob) -> AsyncGenerator[str]:
    """Yield Server-Sent Events for one Coach job until it finishes."""
    yield _sse("status", {"event": "connected", "message": "Connected"})
    while True:
        item = await job.queue.get()
        if item.event == "done" and job.result is not None:
            yield _sse("progress", {"event": item.event, "message": item.message})
            yield _sse("done", job.result.model_dump(mode="json"))
            break
        if item.event == "error":
            yield _sse("failed", {"message": item.message})
            break
        yield _sse("progress", {"event": item.event, "message": item.message})


@router.get("/{deck_id}/coach/{job_id}/stream")
async def coach_deck_stream(
    deck_id: UUID,
    job_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> StreamingResponse:
    """Stream progress and final result for an MTG Assistant job."""
    registry = request.app.state.coach_jobs
    job = registry.get(job_id)
    if job is None or job.account_id != account.id or job.deck_id != deck_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "JOB_NOT_FOUND", "message": f"Coach job {job_id} not found"},
        )
    return StreamingResponse(_coach_event_stream(job), media_type="text/event-stream")


@router.post("/{deck_id}/doctor", response_model=DataResponse[DeckDoctorResponse])
async def doctor_deck(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DeckDoctorResponse]:
    """Run the Commander deck doctor agent for an existing deck."""
    _enforce_rate_limit(account, "doctor_deck", _ANALYZE_LIMIT)
    deck = await _require_deck(request, deck_id, account)
    memory = await coach_memory_service.get_memory(request.app.state.db_pool, deck_id, account.id)
    result = await agents.doctor_deck(
        request.app.state.db_pool,
        deck,
        coach_memory_notes=memory.notes.strip() or None,
    )
    return DataResponse(data=result)


@router.post(
    "/{deck_id}/playtest/analyze",
    response_model=DataResponse[SimulationAnalysisResponse],
)
async def playtest_analyze(
    deck_id: UUID,
    body: PlaytestSimulateRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[SimulationAnalysisResponse]:
    """Run a sim then drive the analysis agent for swap recommendations."""
    email = _require_email(account)
    _enforce_rate_limit(account, "playtest_analyze", _ANALYZE_LIMIT)
    deck = await deck_service.get_deck(request.app.state.db_pool, deck_id, email)
    if deck is None:
        raise _deck_not_found(deck_id)
    stats = playtest_service.simulate(deck, body)
    result = await simulation_analysis_service.analyze_simulation(
        request.app.state.db_pool,
        deck,
        stats,
    )
    return DataResponse(data=result)


async def _run_optimize_job(
    job: optimizer_jobs.OptimizerJob,
    pool: Any,
    deck: Any,
    body: OptimizeRequest,
    account_id: UUID,
) -> None:
    """Drive a long-running optimization search and record its outcome on the job."""
    if _OPTIMIZE_SEMAPHORE.locked():
        optimizer_jobs.finish_error(
            job, "Another optimization is already running; try again shortly."
        )
        return
    async with _OPTIMIZE_SEMAPHORE:
        try:
            result = await deck_optimizer_service.run_search(
                pool,
                deck,
                body.sim,
                search_depth=body.search_depth,
                max_price_cents=body.max_price_cents,
                max_swaps=body.max_swaps,
                account_id=account_id,
                progress_cb=optimizer_jobs.progress_cb(job),
            )
            optimizer_jobs.finish_ok(job, result)
        except Exception as exc:  # noqa: BLE001 — surface any failure on the job
            _log.exception("Optimize job %s failed", job.job_id)
            optimizer_jobs.finish_error(job, str(exc))


@router.post(
    "/{deck_id}/playtest/optimize",
    response_model=DataResponse[OptimizeStartResponse],
    status_code=202,
)
async def playtest_optimize(
    deck_id: UUID,
    body: OptimizeRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[OptimizeStartResponse]:
    """Start a long-running optimization search; poll the status endpoint."""
    email = _require_email(account)
    if not await feature_flag_service.is_enabled(
        request.app.state.db_pool, FLAG_OPTIMIZER, account.id, settings.enable_optimizer
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "FEATURE_DISABLED",
                "message": "Deck optimization is currently disabled",
            },
        )
    _enforce_rate_limit(account, "playtest_optimize", _ANALYZE_LIMIT)
    deck = await deck_service.get_deck(request.app.state.db_pool, deck_id, email)
    if deck is None:
        raise _deck_not_found(deck_id)
    registry = request.app.state.optimizer_jobs
    job = optimizer_jobs.create(registry, account.id, deck_id)
    asyncio.create_task(
        _run_optimize_job(
            job,
            request.app.state.db_pool,
            deck,
            body,
            account.id,
        )
    )
    return DataResponse(data=OptimizeStartResponse(job_id=job.job_id))


@router.get(
    "/{deck_id}/playtest/optimize/{job_id}",
    response_model=DataResponse[OptimizeJobStatus],
)
async def playtest_optimize_status(
    deck_id: UUID,
    job_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[OptimizeJobStatus]:
    """Return progress + result for a running optimization job."""
    _require_email(account)
    registry = request.app.state.optimizer_jobs
    job = registry.get(job_id)
    if job is None or job.account_id != account.id or job.deck_id != deck_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "JOB_NOT_FOUND", "message": f"Optimize job {job_id} not found"},
        )
    return DataResponse(
        data=OptimizeJobStatus(
            status=job.status,
            phase=job.phase,
            current=job.current,
            total=job.total,
            proposal=job.result,
            error=job.error,
        )
    )


@router.post("/{deck_id}/mana-fix", response_model=DataResponse[ManaFixResponse])
async def mana_fix(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[ManaFixResponse]:
    """Analyze the deck's mana base and suggest lands fixing deficient colors."""
    email = _require_email(account)
    deck = await deck_service.get_deck(request.app.state.db_pool, deck_id, email)
    if deck is None:
        raise _deck_not_found(deck_id)
    result = await mana_base_service.suggest_mana_fix(
        request.app.state.db_pool,
        deck,
        account.id,
    )
    return DataResponse(data=result)


@router.post("/{deck_id}/cards/{card_id}/swap", response_model=DataResponse[SwapResponse])
async def find_swaps(
    deck_id: UUID,
    card_id: UUID,
    body: SwapRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[SwapResponse]:
    """Return cheaper alternatives to a deck card, ranked by function similarity."""
    email = _require_email(account)
    deck = await deck_service.get_deck(request.app.state.db_pool, deck_id, email)
    if deck is None:
        raise _deck_not_found(deck_id)
    try:
        result = await swap_service.find_budget_swaps(
            request.app.state.db_pool,
            deck,
            card_id,
            max_price_cents=body.max_price_cents,
            account_id=account.id,
            limit=body.limit,
        )
    except SwapError as e:
        raise HTTPException(
            status_code=400, detail={"code": "SWAP_UNAVAILABLE", "message": str(e)}
        ) from e
    return DataResponse(data=result)


@router.post("/describe", response_model=DataResponse[DescribeResponse])
async def describe_deck(
    body: DescribeRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[DescribeResponse]:
    """Run one turn of the deck description agent to build a structured deck strategy."""
    _enforce_rate_limit(account, "describe", _DESCRIBE_LIMIT)
    try:
        result = await agents.describe_turn(
            request.app.state.db_pool,
            body.commander_scryfall_id,
            body.partner_scryfall_id,
            body.bracket,
            [{"role": m.role, "content": m.content} for m in body.history],
            body.message,
        )
    except CommanderNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
    return DataResponse(data=result)


@router.post("/extract-keywords", response_model=DataResponse[KeywordExtractResponse])
async def extract_keywords(
    body: KeywordExtractRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[KeywordExtractResponse]:
    """Run one turn of the keyword-extracting deck agent.

    The agent converges on structured Moxfield hub theme tags instead of writing
    prose. Used by the ``/decks/new/agent`` flow.
    """
    _enforce_rate_limit(account, "extract_keywords", _DESCRIBE_LIMIT)
    try:
        result = await agents.extract_turn(
            request.app.state.db_pool,
            body.commander_scryfall_id,
            body.partner_scryfall_id,
            body.bracket,
            [{"role": m.role, "content": m.content} for m in body.history],
            body.message,
        )
    except CommanderNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "CARD_NOT_FOUND", "message": str(e)})
    return DataResponse(data=result)


@router.get("/{deck_id}/export/buylist")
async def export_buylist(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> Response:
    """Export Cardmarket-compatible wants list: deck cards the user doesn't own yet."""
    email = _require_email(account)
    result = await deck_service.export_buylist(
        request.app.state.db_pool, deck_id, email, account_id=account.id
    )
    if result is None:
        raise _deck_not_found(deck_id)
    _deck_name, export_text = result
    return Response(content=export_text, media_type="text/plain")


@router.get("/{deck_id}/export/moxfield")
async def export_moxfield(
    deck_id: UUID,
    request: Request,
    account: CurrentAccount,
) -> Response:
    """Export the deck in Moxfield-compatible plain text format."""
    email = _require_email(account)
    result = await deck_service.export_moxfield(request.app.state.db_pool, deck_id, email)
    if result is None:
        raise _deck_not_found(deck_id)
    _deck_name, export_text = result
    return Response(content=export_text, media_type="text/plain")
