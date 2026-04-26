"""Google Sign-In dependency: verifies the bearer ID token and resolves the account."""

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from mtg_helper.config import settings
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.services import account_service

_log = logging.getLogger(__name__)
_google_request = google_requests.Request()


def _verify_id_token(token: str) -> dict[str, object]:
    """Verify a Google OIDC ID token and return its claims."""
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=500, detail="auth not configured")
    try:
        return id_token.verify_oauth2_token(token, _google_request, settings.google_oauth_client_id)
    except ValueError as exc:
        _log.info("rejected token: %s", exc)
        raise HTTPException(status_code=401, detail="invalid token") from exc


async def get_current_account(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AccountResponse:
    """Resolve the current account from the `Authorization: Bearer <id_token>` header.

    Verifies the Google ID token (signature, audience, expiry) and upserts the
    account by `google_sub`. The first request from a new identity creates the
    row; subsequent requests reuse it.

    Args:
        request: FastAPI Request, used to access the asyncpg pool from app state.
        authorization: Raw Authorization header.

    Returns:
        The authenticated account.

    Raises:
        HTTPException: 401 when the header is missing or the token is invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    claims = _verify_id_token(token)
    sub = claims.get("sub")
    email = claims.get("email")
    if not isinstance(sub, str) or not isinstance(email, str):
        raise HTTPException(status_code=401, detail="token missing sub/email")
    name = claims.get("name")
    display_name = name if isinstance(name, str) and name else email
    return await account_service.upsert_by_google_sub(
        request.app.state.db_pool,
        google_sub=sub,
        email=email,
        display_name=display_name,
    )


async def get_current_admin(
    account: Annotated[AccountResponse, Depends(get_current_account)],
) -> AccountResponse:
    """Require the current account's email to be in `settings.admin_emails`.

    Returns:
        The authenticated account when admin.

    Raises:
        HTTPException: 403 when the email is not in the admin list.
    """
    email = (account.email or "").lower()
    if email not in {e.lower() for e in settings.admin_emails}:
        raise HTTPException(status_code=403, detail="admin only")
    return account
