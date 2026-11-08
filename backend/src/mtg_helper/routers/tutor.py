"""Owner-scoped Deck Tutor guide endpoints."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.common import DataResponse, ErrorDetail, ErrorResponse
from mtg_helper.models.tutor import (
    TutorConversationResponse,
    TutorGenerateRequest,
    TutorQuestionRequest,
    TutorReferenceConfirm,
    TutorReferencePreviewResponse,
    TutorReferenceRequest,
    TutorSetupUpdate,
    TutorStateResponse,
)
from mtg_helper.services.tutor.repository import TutorError
from mtg_helper.services.tutor.service import TutorService, owner


def _error_response(status: int, code: str, message: str) -> JSONResponse:
    error = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status, content=error.model_dump())


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    locations = {str(error["loc"][-1]) for error in errors if error.get("loc")}
    if "deck_id" in locations:
        return "The deck ID must be a valid UUID. Choose an existing deck and try again."
    if "mode" in locations:
        return "Choose Commander or cEDH as the Tutor mode, then try again."
    if "request_key" in locations:
        return "Provide a valid Tutor request key, then try again."
    if any(error.get("type") == "json_invalid" for error in errors):
        return "Send a valid JSON Tutor request body, then try again."
    return "Provide the required Tutor request body, then try again."


class TutorRoute(APIRoute):
    """Keep Tutor input and authentication failures in the standard error envelope."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def bounded_validation(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return _error_response(422, "TUTOR_REQUEST_INVALID", _validation_message(exc))
            except StarletteHTTPException as exc:
                response = _http_error(exc)
                response.headers.update(exc.headers or {})
                return response

        return bounded_validation


def _http_error(exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 400:
        return _error_response(
            400,
            "TUTOR_REQUEST_INVALID",
            "Send a valid UTF-8 JSON Tutor request body, then try again.",
        )
    if exc.status_code == 401:
        return _error_response(401, "UNAUTHORIZED", "Sign in to access this Tutor guide.")
    if exc.status_code == 403:
        return _error_response(403, "FORBIDDEN", "You cannot access this Tutor guide.")
    return _error_response(
        exc.status_code,
        "AUTHENTICATION_UNAVAILABLE",
        "Tutor authentication is temporarily unavailable. Try again later.",
    )


router = APIRouter(route_class=TutorRoute, prefix="/decks/{deck_id}/tutor", tags=["tutor"])
CurrentAccount = Annotated[AccountResponse, Depends(get_current_account)]


def _owner(account: AccountResponse):
    if not account.email:
        raise TutorError(
            "Account has no email",
            status=403,
            code="EMAIL_REQUIRED",
        )
    return owner(account.id, account.email)


def _service(request: Request) -> TutorService:
    return TutorService(request.app.state.db_pool)


@router.get("", response_model=DataResponse[TutorStateResponse])
async def get_tutor(
    deck_id: UUID, request: Request, account: CurrentAccount
) -> DataResponse[TutorStateResponse]:
    """Read the saved Tutor state without starting or retrying model work."""
    state = await _service(request).state(_owner(account), deck_id)
    return DataResponse(data=state)


@router.put("/setup", response_model=DataResponse[TutorStateResponse])
async def save_tutor_setup(
    deck_id: UUID, body: TutorSetupUpdate, request: Request, account: CurrentAccount
) -> DataResponse[TutorStateResponse]:
    """Save mode selection without modifying the deck or initiating a guide."""
    state = await _service(request).save_mode(_owner(account), deck_id, body.mode)
    return DataResponse(data=state)


@router.post("/reference/preview", response_model=DataResponse[TutorReferencePreviewResponse])
async def preview_reference(
    deck_id: UUID,
    body: TutorReferenceRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[TutorReferencePreviewResponse]:
    """Resolve and freeze a candidate without replacing the saved reference."""
    preview = await _service(request).preview_reference(_owner(account), deck_id, body)
    return DataResponse(data=preview)


@router.put("/reference", response_model=DataResponse[TutorStateResponse])
async def confirm_reference(
    deck_id: UUID,
    body: TutorReferenceConfirm,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[TutorStateResponse]:
    """Replace the optional reference only after explicit preview confirmation."""
    state = await _service(request).confirm_reference(_owner(account), deck_id, body.preview_id)
    return DataResponse(data=state)


@router.delete("/reference", response_model=DataResponse[TutorStateResponse])
async def remove_reference(
    deck_id: UUID, request: Request, account: CurrentAccount
) -> DataResponse[TutorStateResponse]:
    """Remove the reference without altering the physical deck or generating advice."""
    state = await _service(request).remove_reference(_owner(account), deck_id)
    return DataResponse(data=state)


@router.get("/conversation", response_model=DataResponse[TutorConversationResponse])
async def get_conversation(
    deck_id: UUID, request: Request, account: CurrentAccount
) -> DataResponse[TutorConversationResponse]:
    """Read all current and archived owner turns without triggering compaction."""
    conversation = await _service(request).conversation(_owner(account), deck_id)
    return DataResponse(data=conversation)


@router.delete("/conversation", response_model=DataResponse[TutorConversationResponse])
async def clear_conversation(
    deck_id: UUID, request: Request, account: CurrentAccount
) -> DataResponse[TutorConversationResponse]:
    """Delete all saved Tutor chapters and turns while preserving guides and references."""
    conversation = await _service(request).clear_conversation(_owner(account), deck_id)
    return DataResponse(data=conversation)


@router.post("/questions", response_model=DataResponse[TutorConversationResponse])
async def ask_question(
    deck_id: UUID,
    body: TutorQuestionRequest,
    request: Request,
    account: CurrentAccount,
) -> DataResponse[TutorConversationResponse]:
    """Persist a question and start at most one answer for its request key."""
    conversation = await _service(request).ask(
        _owner(account), deck_id, body.request_key, body.question, body.card_name
    )
    return DataResponse(data=conversation)


@router.post("/guides", response_model=DataResponse[TutorStateResponse])
async def generate_guide(
    deck_id: UUID, body: TutorGenerateRequest, request: Request, account: CurrentAccount
) -> DataResponse[TutorStateResponse]:
    """Persist and start one explicit idempotent guide request."""
    state = await _service(request).start(_owner(account), deck_id, body.request_key)
    return DataResponse(data=state)
