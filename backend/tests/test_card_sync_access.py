"""Only the admin API may expose global card synchronization."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from mtg_helper import auth
from mtg_helper.auth import get_current_account
from mtg_helper.config import settings
from mtg_helper.main import app
from mtg_helper.models.accounts import AccountResponse
from mtg_helper.services import account_service, scryfall

pytestmark = pytest.mark.no_db


def _account() -> AccountResponse:
    return AccountResponse(
        id=uuid4(),
        display_name="Ordinary user",
        email="user@example.test",
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize("authenticated", [False, True])
async def test_legacy_card_sync_cannot_start_work(
    monkeypatch: pytest.MonkeyPatch, authenticated: bool
) -> None:
    sync = AsyncMock(return_value={"cards_processed": 0})
    overrides = {get_current_account: _account} if authenticated else {}
    monkeypatch.setattr(app, "dependency_overrides", overrides)
    monkeypatch.setattr(app.state, "db_pool", None, raising=False)
    monkeypatch.setattr(scryfall, "run_sync", sync)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/cards/sync")

    assert response.status_code == 405
    sync.assert_not_awaited()


def test_openapi_advertises_only_admin_card_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "openapi_schema", None)

    paths = app.openapi()["paths"]

    assert "/api/v1/cards/sync" not in paths
    assert "post" in paths["/api/v1/admin/sync-cards"]


@pytest.mark.parametrize("authenticated,expected_status", [(False, 401), (True, 403)])
async def test_admin_card_sync_still_rejects_unauthorized_users(
    monkeypatch: pytest.MonkeyPatch, authenticated: bool, expected_status: int
) -> None:
    sync = AsyncMock()
    monkeypatch.setattr(app, "dependency_overrides", {})
    monkeypatch.setattr(app.state, "db_pool", None, raising=False)
    monkeypatch.setattr(settings, "admin_emails", [])
    monkeypatch.setattr(scryfall, "run_sync", sync)
    monkeypatch.setattr(
        auth, "_verify_id_token", lambda _token: {"sub": "test-sub", "email": "user@example.test"}
    )
    monkeypatch.setattr(account_service, "upsert_by_google_sub", AsyncMock(return_value=_account()))
    headers = {"Authorization": "Bearer test-token"} if authenticated else {}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/admin/sync-cards", headers=headers)

    assert response.status_code == expected_status
    sync.assert_not_awaited()
