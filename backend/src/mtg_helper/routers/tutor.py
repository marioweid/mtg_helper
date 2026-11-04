"""Owner-scoped Deck Tutor guide endpoints."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from mtg_helper.auth import get_current_account
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.models.common import DataResponse, ErrorDetail, ErrorResponse
from mtg_helper.models.tutor import TutorGenerateRequest, TutorSetupUpdate, TutorStateResponse
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
            except HTTPException as exc:
                return _authentication_error(exc)

        return bounded_validation


def _authentication_error(exc: HTTPException) -> JSONResponse:
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


@router.post("/guides", response_model=DataResponse[TutorStateResponse])
async def generate_guide(
    deck_id: UUID, body: TutorGenerateRequest, request: Request, account: CurrentAccount
) -> DataResponse[TutorStateResponse]:
    """Persist and start one explicit idempotent guide request."""
    state = await _service(request).start(_owner(account), deck_id, body.request_key)
    return DataResponse(data=state)
