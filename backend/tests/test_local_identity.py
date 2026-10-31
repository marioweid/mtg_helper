"""Opt-in local identity, isolated deployment guards and unchanged authorization."""

from uuid import UUID, uuid4

import asyncpg
import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from mtg_helper.auth import get_current_account, get_current_admin, require_admin_or_internal
from mtg_helper.config import Settings, settings
from mtg_helper.main import app
from tests.conftest import create_test_deck

LOCAL_DATABASE = "postgresql://mtg:local@postgres:5432/mtg_helper"
ACCOUNT = UUID("10000000-0000-0000-0000-000000000001")


@pytest.mark.no_db
def test_local_identity_requires_explicit_opt_in_and_account() -> None:
    normal = Settings(_env_file=None, database_url=LOCAL_DATABASE, openai_api_key="test")
    assert not normal.local_dev_auth
    local = Settings(
        _env_file=None,
        database_url=LOCAL_DATABASE,
        openai_api_key="test",
        app_env="local",
        local_dev_auth=True,
        local_dev_account_id=ACCOUNT,
    )
    assert local.local_dev_account_id == ACCOUNT


@pytest.mark.no_db
def test_settings_diagnostics_do_not_print_database_credentials_or_internal_token() -> None:
    configured = Settings(
        _env_file=None,
        database_url=LOCAL_DATABASE,
        openai_api_key="test",
        internal_api_token="sensitive-test-token",
    )
    assert "sensitive-test-token" not in repr(configured)
    assert "postgresql://" not in repr(configured)


@pytest.mark.no_db
@pytest.mark.parametrize("mode", ["live", "staging", "production"])
def test_local_identity_refuses_nonlocal_deployments(mode: str) -> None:
    with pytest.raises(ValidationError, match="isolated local Compose"):
        Settings(
            _env_file=None,
            database_url=LOCAL_DATABASE,
            openai_api_key="test",
            app_env=mode,
            local_dev_auth=True,
            local_dev_account_id=ACCOUNT,
        )


@pytest.mark.no_db
@pytest.mark.parametrize(
    "database",
    [
        "postgresql://mtg:local@remote.example:5432/mtg_helper",
        "postgresql://mtg:local@postgres:5432/mtg_app",
        "postgresql://mtg:local@postgres:5432/mtg_helper?host=remote.example",
        "postgresql://mtg:local@postgres:5433/mtg_helper",
        "postgresql://mtg:local@localhost:5432/mtg_helper",
    ],
)
def test_local_identity_refuses_noncompose_or_rerouted_database(database: str) -> None:
    with pytest.raises(ValidationError, match="isolated local Compose"):
        Settings(
            _env_file=None,
            database_url=database,
            openai_api_key="test",
            app_env="local",
            local_dev_auth=True,
            local_dev_account_id=ACCOUNT,
        )


@pytest.mark.no_db
def test_local_identity_rejects_missing_account_without_exposing_inputs() -> None:
    with pytest.raises(ValidationError, match="LOCAL_DEV_ACCOUNT_ID") as error:
        Settings(
            _env_file=None,
            database_url=LOCAL_DATABASE,
            openai_api_key="test",
            app_env="local",
            local_dev_auth=True,
            local_dev_account_id=None,
        )
    assert "postgresql://" not in str(error.value)


def enable_local(monkeypatch: pytest.MonkeyPatch, account: UUID) -> None:
    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(settings, "database_url", LOCAL_DATABASE)
    monkeypatch.setattr(settings, "local_dev_auth", True)
    monkeypatch.setattr(settings, "local_dev_account_id", account)
    for dependency in (get_current_account, get_current_admin, require_admin_or_internal):
        app.dependency_overrides.pop(dependency, None)


@pytest.mark.asyncio
async def test_local_identity_reads_existing_account_without_creating_or_remapping(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = await db_pool.fetchrow("SELECT * FROM accounts WHERE email='default@test.local'")
    before = await db_pool.fetchval("SELECT count(*) FROM accounts")
    enable_local(monkeypatch, account["id"])
    response = await client.get(
        "/api/v1/me",
        headers={
            "Authorization": "Bearer not-a-google-token",
            "X-Account-ID": str(uuid4()),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["id"] == str(account["id"])
    assert await db_pool.fetchval("SELECT count(*) FROM accounts") == before
    assert await db_pool.fetchrow("SELECT * FROM accounts WHERE id=$1", account["id"]) == account


@pytest.mark.asyncio
async def test_local_identity_preserves_ownership_and_admin_gates(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = await db_pool.fetchval("SELECT id FROM accounts WHERE email='default@test.local'")
    enable_local(monkeypatch, account)
    monkeypatch.setattr(settings, "admin_emails", [])
    monkeypatch.setattr(settings, "internal_api_token", "")
    deck = await create_test_deck(client)
    assert (await client.get(f"/api/v1/decks/{deck}")).status_code == 200
    assert (await client.post("/api/v1/admin/sync-cards")).status_code == 403
    other = await db_pool.fetchval(
        "INSERT INTO accounts(display_name,email) VALUES('Other','other@local.test') RETURNING id"
    )
    monkeypatch.setattr(settings, "local_dev_account_id", other)
    assert (await client.get(f"/api/v1/decks/{deck}")).status_code == 404


@pytest.mark.asyncio
async def test_local_identity_rejects_cross_site_mutation_and_missing_accounts(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = await db_pool.fetchval("SELECT id FROM accounts WHERE email='default@test.local'")
    enable_local(monkeypatch, account)
    response = await client.patch(
        "/api/v1/me",
        json={"display_name": "Bad"},
        headers={
            "Origin": "https://unrelated.example",
            "Sec-Fetch-Site": "cross-site",
        },
    )
    assert response.status_code == 403
    allowed = await client.patch(
        "/api/v1/me",
        json={"display_name": "Local edit"},
        headers={"Origin": "http://localhost:3000", "Sec-Fetch-Site": "same-origin"},
    )
    assert allowed.status_code == 200
    monkeypatch.setattr(settings, "local_dev_account_id", uuid4())
    assert (await client.get("/api/v1/me")).status_code == 503


@pytest.mark.asyncio
async def test_local_startup_checks_the_actual_connected_database(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mtg_helper.auth import validate_local_account

    account = await db_pool.fetchval("SELECT id FROM accounts WHERE email='default@test.local'")
    enable_local(monkeypatch, account)
    with pytest.raises(RuntimeError, match="connected database"):
        await validate_local_account(db_pool)
