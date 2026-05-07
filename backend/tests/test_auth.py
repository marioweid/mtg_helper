"""Tests for the Google ID-token auth dependency and admin gate."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from mtg_helper import auth as auth_mod
from mtg_helper.auth import (
    get_current_account,
    get_current_admin,
    require_admin_or_internal,
)
from mtg_helper.config import settings
from mtg_helper.main import app

pytestmark = pytest.mark.asyncio


def _fake_request(db_pool: object) -> object:
    """Build a minimal Request stand-in with `app.state.db_pool`."""

    class _State:
        pass

    class _App:
        state = _State()

    class _Req:
        app = _App()

    req = _Req()
    req.app.state.db_pool = db_pool
    return req


async def test_get_current_account_creates_row_on_first_login(client: AsyncClient) -> None:
    """Valid token with new `sub` upserts a fresh account."""
    settings.google_oauth_client_id = "test-client-id"
    app.dependency_overrides.pop(get_current_account, None)
    app.dependency_overrides.pop(get_current_admin, None)
    claims = {"sub": "google-sub-new", "email": "new@test.local", "name": "New User"}

    with patch.object(auth_mod, "_verify_id_token", return_value=claims):
        account = await get_current_account(
            _fake_request(app.state.db_pool), authorization="Bearer faketoken"
        )

    assert account.email == "new@test.local"
    assert account.display_name == "New User"


async def test_get_current_account_missing_header_raises_401(client: AsyncClient) -> None:
    """No Authorization header → 401."""
    app.dependency_overrides.pop(get_current_account, None)
    with pytest.raises(HTTPException) as exc:
        await get_current_account(_fake_request(app.state.db_pool), authorization=None)
    assert exc.value.status_code == 401


async def test_get_current_account_non_bearer_raises_401(client: AsyncClient) -> None:
    """Non-Bearer Authorization header → 401."""
    app.dependency_overrides.pop(get_current_account, None)
    with pytest.raises(HTTPException) as exc:
        await get_current_account(_fake_request(app.state.db_pool), authorization="Basic abc")
    assert exc.value.status_code == 401


async def test_get_current_account_invalid_token_raises_401(client: AsyncClient) -> None:
    """`verify_oauth2_token` ValueError → 401."""
    settings.google_oauth_client_id = "test-client-id"
    app.dependency_overrides.pop(get_current_account, None)
    with patch(
        "mtg_helper.auth.id_token.verify_oauth2_token",
        side_effect=ValueError("bad sig"),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_account(
                _fake_request(app.state.db_pool), authorization="Bearer bogus"
            )
    assert exc.value.status_code == 401


async def test_get_current_account_missing_claims_raises_401(client: AsyncClient) -> None:
    """Token without `sub`/`email` claims → 401."""
    settings.google_oauth_client_id = "test-client-id"
    app.dependency_overrides.pop(get_current_account, None)
    with patch.object(auth_mod, "_verify_id_token", return_value={"sub": "x"}):
        with pytest.raises(HTTPException) as exc:
            await get_current_account(_fake_request(app.state.db_pool), authorization="Bearer t")
    assert exc.value.status_code == 401


async def test_get_current_admin_allows_listed_email(client: AsyncClient) -> None:
    """Account whose email is in `admin_emails` passes the admin gate."""
    from mtg_helper.models.accounts import AccountResponse

    settings.admin_emails = ["admin@test.local"]
    pool = app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO accounts (display_name, email) VALUES ($1, $2) RETURNING *",
            "Admin",
            "admin@test.local",
        )
    account = AccountResponse(
        id=row["id"],
        display_name=row["display_name"],
        email=row["email"],
        created_at=row["created_at"],
    )

    result = await get_current_admin(account=account)
    assert result.id == account.id


async def test_get_current_admin_rejects_non_admin(client: AsyncClient) -> None:
    """Non-admin email → 403."""
    from mtg_helper.models.accounts import AccountResponse

    settings.admin_emails = ["admin@test.local"]
    pool = app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO accounts (display_name, email) VALUES ($1, $2) RETURNING *",
            "Nobody",
            "nobody@test.local",
        )
    account = AccountResponse(
        id=row["id"],
        display_name=row["display_name"],
        email=row["email"],
        created_at=row["created_at"],
    )

    with pytest.raises(HTTPException) as exc:
        await get_current_admin(account=account)
    assert exc.value.status_code == 403


async def test_admin_router_returns_403_via_http(client: AsyncClient) -> None:
    """End-to-end: admin endpoint with non-admin override returns 403."""
    from mtg_helper.models.accounts import AccountResponse

    settings.admin_emails = ["admin@test.local"]

    pool = app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO accounts (display_name, email) VALUES ($1, $2) RETURNING *",
            "User",
            "user@test.local",
        )
    user = AccountResponse(
        id=row["id"],
        display_name=row["display_name"],
        email=row["email"],
        created_at=row["created_at"],
    )

    async def _real_admin() -> None:
        await get_current_admin(account=user)

    app.dependency_overrides[require_admin_or_internal] = _real_admin

    resp = await client.post("/api/v1/admin/sync-cards")
    assert resp.status_code == 403


async def test_internal_token_bypasses_admin_gate(client: AsyncClient) -> None:
    """Valid `X-Internal-Token` header skips Google auth on admin endpoints."""
    settings.internal_api_token = "secret-token-xyz"
    app.dependency_overrides.pop(require_admin_or_internal, None)

    req = _fake_request(app.state.db_pool)
    await auth_mod.require_admin_or_internal(
        request=req,  # type: ignore[arg-type]
        x_internal_token="secret-token-xyz",
        authorization=None,
    )


async def test_internal_token_mismatch_falls_through_to_admin(client: AsyncClient) -> None:
    """Wrong `X-Internal-Token` falls through and 401s without a Bearer token."""
    settings.internal_api_token = "secret-token-xyz"
    app.dependency_overrides.pop(require_admin_or_internal, None)

    with pytest.raises(HTTPException) as exc:
        await auth_mod.require_admin_or_internal(
            request=_fake_request(app.state.db_pool),  # type: ignore[arg-type]
            x_internal_token="wrong",
            authorization=None,
        )
    assert exc.value.status_code == 401


async def test_internal_token_disabled_when_unset(client: AsyncClient) -> None:
    """Empty `internal_api_token` disables internal auth even if header sent."""
    settings.internal_api_token = ""
    app.dependency_overrides.pop(require_admin_or_internal, None)

    with pytest.raises(HTTPException) as exc:
        await auth_mod.require_admin_or_internal(
            request=_fake_request(app.state.db_pool),  # type: ignore[arg-type]
            x_internal_token="",
            authorization=None,
        )
    assert exc.value.status_code == 401
